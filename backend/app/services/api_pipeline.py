"""
Resumable processing pipeline for jobs created through POST /api/v1/jobs.

Execution model
---------------
* Each Cloud Tasks delivery calls ApiJobRunner.run(job_id, seq) inside the
  POST /internal/run/{job_id} request, so Cloud Run keeps CPU allocated for
  the whole time the work runs.
* The worker takes a lease on the job record (CAS on the GCS generation) and
  renews it with a heartbeat. A duplicate delivery waits: if the holder is
  alive it returns 200 without doing anything; if the holder died, the lease
  expires and the duplicate takes over.
* Work is split into steps with durable checkpoints: audio extraction ->
  per-chunk transcription -> slide rendering -> chapters/result. A retry
  skips whatever is already checkpointed.
* Cloud Tasks gives an HTTP task at most 30 minutes. A task stops starting
  new units after TASK_SOFT_BUDGET_SECONDS, enqueues a continuation task
  (seq + 1, with a deterministic name so it is created once) and returns.
* Failure handling: a PermanentJobError (bad input) fails the job at once.
  Other errors are retried by the queue until the attempt count reaches
  TASK_MAX_ATTEMPTS, when the job is marked failed and 200 is returned so the
  queue stops. A job whose heartbeat stops for JOB_STALE_SECONDS (e.g. the
  final attempt was killed) is reported failed on the next status read.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.api_job_store import (
    COMPLETED,
    FAILED,
    PROCESSING,
    QUEUED,
    TERMINAL,
    ApiJobStore,
    JobNotFound,
    iso,
    parse_iso,
    transition,
    utcnow,
)
from app.services.gcs_io import GcsIO, ObjectNotReadable, parse_gs_uri
from app.services.task_dispatcher import Dispatcher

logger = logging.getLogger(__name__)

QA_IMAGE_CANDIDATES = [
    Path("/app/qa.jpg"),
    Path(__file__).resolve().parents[3] / "qa.jpg",
]


class PermanentJobError(Exception):
    """Input problem; retrying cannot help."""


class LeaseLost(Exception):
    """Another worker owns the job now (or it reached a terminal state)."""


class Handoff(Exception):
    """This task used its time budget; continue in a new task."""


@dataclass
class RunOutcome:
    action: str  # completed | failed | continued | noop | retry
    detail: str = ""
    http_status: int = 200


@dataclass
class AudioChunk:
    index: int
    path: str
    start: float
    end: float


def format_srt(segments: List[Dict[str, Any]]) -> str:
    def ts(seconds: float) -> str:
        ms = int(round(max(seconds, 0.0) * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(segments, 1):
        lines += [str(i), f"{ts(seg['start'])} --> {ts(seg['end'])}", seg["text"], ""]
    return "\n".join(lines)


def _summarize(exc: BaseException) -> str:
    text = str(exc).strip().replace("\n", " ")
    return f"{type(exc).__name__}: {text[:500]}" if text else type(exc).__name__


# ---------------------------------------------------------------------------
# Heavy work (ffmpeg, OpenAI, slide rendering). Replaced by fakes in tests.
# ---------------------------------------------------------------------------


class PipelineSteps:
    _PERMANENT_FFMPEG_MARKERS = (
        "matches no streams",
        "does not contain any stream",
        "Invalid data found when processing input",
        "Server returned 404",
        "moov atom not found",
    )

    def __init__(self, gcs: GcsIO, cfg):
        self.gcs = gcs
        self.cfg = cfg
        self._openai = None
        self._chapters = None
        self._presentations = None

    async def make_audio_chunks(
        self, video_uri: str, workdir: str, chunk_seconds: int
    ) -> Tuple[List[AudioChunk], float]:
        """Extract mono 16 kHz MP3 audio in fixed-length chunks with one ffmpeg pass."""
        try:
            info = await asyncio.to_thread(self.gcs.stat, video_uri)
        except ObjectNotReadable:
            raise PermanentJobError(f"video_uri is not readable by the service account: {video_uri}")
        if info is None:
            raise PermanentJobError(f"video_uri not found: {video_uri}")

        out_dir = Path(workdir) / "audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        list_path = out_dir / "segments.csv"
        input_args: List[str]
        local_input: Optional[Path] = None
        if info.size <= self.cfg.STREAM_INPUT_THRESHOLD_MB * 1024 * 1024:
            suffix = Path(parse_gs_uri(video_uri).name).suffix[:10]
            local_input = Path(workdir) / f"input{suffix}"
            await asyncio.to_thread(self.gcs.download_to_file, video_uri, str(local_input))
            input_args = ["-i", str(local_input)]
        else:
            # Large file: let ffmpeg read it with HTTP range requests instead of
            # copying it into /tmp (in-memory on Cloud Run).
            token = await asyncio.to_thread(self.gcs.access_token)
            input_args = [
                "-headers", f"Authorization: Bearer {token}\r\n",
                "-reconnect", "1",
                "-reconnect_on_network_error", "1",
                "-reconnect_delay_max", "10",
                "-i", parse_gs_uri(video_uri).https_url,
            ]
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            *input_args,
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "libmp3lame", "-b:a", "64k",
            "-f", "segment", "-segment_time", str(chunk_seconds),
            "-reset_timestamps", "1",
            "-segment_list", str(list_path), "-segment_list_type", "csv",
            str(out_dir / "chunk_%03d.mp3"),
        ]
        try:
            # The command line may contain a bearer token: never log `cmd`.
            proc = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True,
                timeout=self.cfg.FFMPEG_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Audio extraction timed out")
        finally:
            if local_input is not None and local_input.exists():
                local_input.unlink()
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[-600:]
            if any(m in tail for m in self._PERMANENT_FFMPEG_MARKERS):
                raise PermanentJobError(f"Could not read an audio track from the video: {tail}")
            raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {tail}")

        chunks: List[AudioChunk] = []
        if list_path.exists():
            with open(list_path, newline="") as fh:
                for i, row in enumerate(csv.reader(fh)):
                    if len(row) < 3:
                        continue
                    path = out_dir / row[0]
                    if path.exists() and path.stat().st_size > 0:
                        chunks.append(AudioChunk(i, str(path), float(row[1]), float(row[2])))
        if not chunks:
            raise PermanentJobError("The video has no audio to transcribe")
        return chunks, chunks[-1].end

    async def transcribe_chunk(self, path: str, language: Optional[str]) -> Dict[str, Any]:
        import openai

        if self._openai is None:
            from app.core.config import settings

            self._openai = openai.OpenAI(
                api_key=settings.OPENAI_API_KEY, timeout=600.0, max_retries=3
            )
        kwargs: Dict[str, Any] = {
            "model": self.cfg.TRANSCRIPTION_MODEL,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment"],
            "prompt": (
                "This is a professional presentation or lecture. The audio contains "
                "technical terms, proper nouns, and company names."
            ),
        }
        if language:
            kwargs["language"] = language
        try:
            with open(path, "rb") as fh:
                result = await asyncio.to_thread(
                    self._openai.audio.transcriptions.create, file=fh, **kwargs
                )
        except openai.BadRequestError as e:
            raise PermanentJobError(f"Transcription rejected the input: {e}")
        segments = [
            {"start": float(s.start), "end": float(s.end), "text": s.text}
            for s in (getattr(result, "segments", None) or [])
        ]
        return {"segments": segments, "language": getattr(result, "language", None)}

    async def render_slides(self, deck_path: str, out_dir: str) -> List[str]:
        from app.services.presentation import PresentationService

        if self._presentations is None:
            self._presentations = PresentationService()
        try:
            slides = await self._presentations.extract_slides_from_local(deck_path, "jpg")
        except ValueError as e:
            raise PermanentJobError(str(e))
        return [s["local_path"] for s in slides]

    async def generate_chapters(
        self, transcription: Dict[str, Any], slide_count: int, title: Optional[str]
    ) -> List[Dict[str, Any]]:
        from app.services.chapter_generation import ChapterGenerationService

        if self._chapters is None:
            self._chapters = ChapterGenerationService()
        return await self._chapters.generate_chapters(
            transcription=transcription, slide_count=slide_count, title=title
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class _Ctx:
    job_id: str
    owner: str
    doc: Dict[str, Any]
    seq: int
    started: float
    budget: Optional[float]
    workdir: str
    lost: bool = False
    local_chunks: Dict[int, str] = field(default_factory=dict)


class ApiJobRunner:
    def __init__(
        self,
        store: ApiJobStore,
        gcs: GcsIO,
        steps: PipelineSteps,
        dispatcher: Dispatcher,
        cfg,
        *,
        output_bucket: str,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utcnow,
        sleep=asyncio.sleep,
        poll_seconds: float = 5.0,
    ):
        self.store = store
        self.gcs = gcs
        self.steps = steps
        self.dispatcher = dispatcher
        self.cfg = cfg
        self.output_bucket = output_bucket
        self.monotonic = monotonic
        self.now = now
        self.sleep = sleep
        self.poll_seconds = poll_seconds

    # -- paths ---------------------------------------------------------------

    def out_uri(self, job_id: str, rel: str) -> str:
        return f"gs://{self.output_bucket}/outputs/{job_id}/{rel}"

    def work_uri(self, job_id: str, rel: str) -> str:
        return f"gs://{self.output_bucket}/work/{job_id}/{rel}"

    # -- entry point ---------------------------------------------------------

    async def run(self, job_id: str, seq: int = 0) -> RunOutcome:
        inline = self.dispatcher.inline
        try:
            claimed = await self._claim(job_id, seq)
        except JobNotFound:
            return RunOutcome("noop", "unknown job")
        if isinstance(claimed, RunOutcome):
            return claimed
        doc, owner = claimed
        attempts = doc["task"]["attempts"]
        max_attempts = 1 if inline else max(1, int(self.cfg.TASK_MAX_ATTEMPTS))

        ctx = _Ctx(
            job_id=job_id,
            owner=owner,
            doc=doc,
            seq=doc["task"]["seq"],
            started=self.monotonic(),
            budget=None if inline else float(self.cfg.TASK_SOFT_BUDGET_SECONDS),
            workdir=tempfile.mkdtemp(prefix=f"{job_id}-"),
        )
        if attempts > max_attempts:
            # Earlier deliveries of this task died without reporting (e.g. OOM).
            await self._fail(ctx, f"Gave up after {attempts - 1} attempts; the worker stopped "
                                  "unexpectedly (possibly out of memory or timed out)")
            shutil.rmtree(ctx.workdir, ignore_errors=True)
            return RunOutcome("failed", "too many attempts")

        heartbeat = asyncio.create_task(self._heartbeat(ctx))
        try:
            await self._execute(ctx)
            return RunOutcome("completed")
        except Handoff:
            try:
                await self._continue(ctx)
                return RunOutcome("continued", f"seq {ctx.seq + 1}")
            except LeaseLost:
                return RunOutcome("noop", "lease lost")
            except Exception as e:  # enqueue failed: let the queue retry this task
                logger.exception("Could not enqueue continuation for %s", job_id)
                await self._release(ctx, f"Retrying (could not schedule continuation: {_summarize(e)})")
                return RunOutcome("retry", _summarize(e), 500)
        except LeaseLost:
            return RunOutcome("noop", "lease lost")
        except PermanentJobError as e:
            logger.warning("Job %s failed permanently: %s", job_id, e)
            await self._fail(ctx, str(e)[:1000])
            return RunOutcome("failed", str(e))
        except Exception as e:
            logger.exception("Job %s attempt %s/%s failed", job_id, attempts, max_attempts)
            if attempts >= max_attempts:
                await self._fail(ctx, _summarize(e))
                return RunOutcome("failed", _summarize(e))
            await self._release(
                ctx, f"Attempt {attempts}/{max_attempts} failed, retrying: {_summarize(e)[:200]}"
            )
            return RunOutcome("retry", _summarize(e), 500)
        finally:
            heartbeat.cancel()
            shutil.rmtree(ctx.workdir, ignore_errors=True)

    # -- lease handling ------------------------------------------------------

    async def _claim(self, job_id: str, seq: int):
        lease = float(self.cfg.JOB_LEASE_SECONDS)
        wait_limit = self.monotonic() + lease * 2 + 30
        last_expiry = None
        while True:
            doc = await self.store.get(job_id)
            if doc is None:
                return RunOutcome("noop", "unknown job")
            if doc["status"] in TERMINAL:
                return RunOutcome("noop", f"job already {doc['status']}")
            task = doc["task"]
            if seq < task["seq"]:
                return RunOutcome("noop", "stale task")
            now = self.now()
            expires = parse_iso(task.get("lease_expires_at"))
            free = task.get("lease_owner") is None or expires is None or expires <= now
            if free:
                owner = uuid.uuid4().hex
                try:
                    claimed = await self.store.update(job_id, self._claim_mutation(seq, owner))
                except _Busy:
                    continue
                except _Skip as s:
                    return RunOutcome("noop", str(s))
                return claimed, owner
            # Someone holds a live lease.
            if seq == task["seq"] and last_expiry is not None and task["lease_expires_at"] != last_expiry:
                # Heartbeat moved: the holder is alive and will finish or hand off.
                return RunOutcome("noop", "another worker is running this task")
            last_expiry = task["lease_expires_at"]
            if self.monotonic() > wait_limit:
                return RunOutcome("retry", "job lease is busy", 503)
            await self.sleep(self.poll_seconds)

    def _claim_mutation(self, seq: int, owner: str):
        lease = float(self.cfg.JOB_LEASE_SECONDS)

        def mutate(doc):
            if doc["status"] in TERMINAL:
                raise _Skip(f"job already {doc['status']}")
            task = doc["task"]
            if seq < task["seq"]:
                raise _Skip("stale task")
            now = self.now()
            expires = parse_iso(task.get("lease_expires_at"))
            if task.get("lease_owner") is not None and expires is not None and expires > now:
                raise _Busy()
            if seq > task["seq"]:
                task["seq"] = seq
                task["attempts"] = 0
            task["attempts"] += 1
            task["lease_owner"] = owner
            task["lease_expires_at"] = iso(now + timedelta(seconds=lease))
            doc["heartbeat_at"] = iso(now)
            if doc["status"] == QUEUED:
                transition(doc, PROCESSING, now)
                doc["message"] = "Starting"
            doc["updated_at"] = iso(now)

        return mutate

    async def _save(self, ctx: _Ctx, fn: Callable[[Dict[str, Any]], None]) -> None:
        if ctx.lost:
            raise LeaseLost()
        owner = ctx.owner

        def mutate(doc):
            if doc["status"] in TERMINAL or doc["task"].get("lease_owner") != owner:
                raise LeaseLost()
            fn(doc)
            now = self.now()
            doc["updated_at"] = iso(now)
            doc["heartbeat_at"] = iso(now)

        ctx.doc = await self.store.update(ctx.job_id, mutate)

    async def _heartbeat(self, ctx: _Ctx) -> None:
        lease = float(self.cfg.JOB_LEASE_SECONDS)
        while True:
            await asyncio.sleep(lease / 3)

            def renew(doc):
                doc["task"]["lease_expires_at"] = iso(self.now() + timedelta(seconds=lease))

            try:
                await self._save(ctx, renew)
            except LeaseLost:
                ctx.lost = True
                return
            except Exception:
                logger.warning("Heartbeat for %s failed; will retry", ctx.job_id, exc_info=True)

    async def _release(self, ctx: _Ctx, message: str) -> None:
        def mutate(doc):
            doc["task"]["lease_owner"] = None
            doc["task"]["lease_expires_at"] = None
            doc["message"] = message

        try:
            await self._save(ctx, mutate)
        except Exception:
            logger.warning("Could not release lease for %s", ctx.job_id, exc_info=True)

    async def _fail(self, ctx: _Ctx, error: str) -> None:
        def mutate(doc):
            transition(doc, FAILED, self.now())
            doc["error"] = error
            doc["message"] = "Failed"
            doc["task"]["lease_owner"] = None
            doc["task"]["lease_expires_at"] = None

        try:
            await self._save(ctx, mutate)
        except Exception:
            logger.warning("Could not mark %s failed", ctx.job_id, exc_info=True)

    async def _continue(self, ctx: _Ctx) -> None:
        next_seq = ctx.seq + 1
        # Enqueue first: if we die before the record update, the continuation
        # waits for our lease to expire and then takes over.
        await self.dispatcher.enqueue(ctx.job_id, next_seq)

        def mutate(doc):
            doc["task"].update(seq=next_seq, attempts=0, lease_owner=None, lease_expires_at=None)
            doc["message"] = "Continuing in a new task"

        await self._save(ctx, mutate)

    def _check_budget(self, ctx: _Ctx) -> None:
        if ctx.budget is not None and self.monotonic() - ctx.started > ctx.budget:
            raise Handoff()

    # -- steps ---------------------------------------------------------------

    async def _execute(self, ctx: _Ctx) -> None:
        await self._step_audio(ctx)
        await self._step_transcribe(ctx)
        await self._step_slides(ctx)
        await self._step_finish(ctx)

    async def _set_progress(self, ctx: _Ctx, progress: int, message: str, **checkpoints) -> None:
        def mutate(doc):
            doc["progress"] = max(int(doc.get("progress") or 0), progress)
            doc["message"] = message
            doc["checkpoints"].update(checkpoints)

        await self._save(ctx, mutate)

    async def _step_audio(self, ctx: _Ctx) -> None:
        if "audio" in ctx.doc["checkpoints"]:
            return
        self._check_budget(ctx)
        await self._set_progress(ctx, 2, "Extracting audio")
        chunks, duration = await self.steps.make_audio_chunks(
            ctx.doc["input"]["video_uri"], ctx.workdir, int(self.cfg.TRANSCRIBE_CHUNK_SECONDS)
        )
        records = []
        for c in chunks:
            uri = self.work_uri(ctx.job_id, f"audio/chunk_{c.index:03d}.mp3")
            await asyncio.to_thread(self.gcs.upload_file, c.path, uri, "audio/mpeg")
            ctx.local_chunks[c.index] = c.path
            records.append({"index": c.index, "start": c.start, "end": c.end, "uri": uri})
        await self._set_progress(
            ctx, 15, f"Transcribing audio (0/{len(records)} chunks)",
            audio={"chunks": records, "duration": duration},
        )

    async def _transcribe_one(self, ctx: _Ctx, chunk: Dict[str, Any]) -> None:
        idx = chunk["index"]
        path = ctx.local_chunks.get(idx)
        if not path or not os.path.exists(path):
            path = os.path.join(ctx.workdir, f"chunk_{idx:03d}.mp3")
            await asyncio.to_thread(self.gcs.download_to_file, chunk["uri"], path)
            ctx.local_chunks[idx] = path
        out = await self.steps.transcribe_chunk(path, ctx.doc["input"].get("language"))
        offset = float(chunk["start"])
        segments = []
        for s in out.get("segments", []):
            text = (s.get("text") or "").strip()
            if text:
                segments.append({
                    "start": round(float(s["start"]) + offset, 3),
                    "end": round(float(s["end"]) + offset, 3),
                    "text": text,
                })
        payload = {"index": idx, "segments": segments, "language": out.get("language")}
        await asyncio.to_thread(
            self.gcs.upload_bytes,
            json.dumps(payload).encode(),
            self.work_uri(ctx.job_id, f"transcripts/chunk_{idx:03d}.json"),
            "application/json",
            None,
        )

    async def _step_transcribe(self, ctx: _Ctx) -> None:
        chunks = ctx.doc["checkpoints"]["audio"]["chunks"]
        total = len(chunks)
        done = set(ctx.doc["checkpoints"].get("transcribed", []))
        pending = [c for c in chunks if c["index"] not in done]
        width = max(1, int(self.cfg.TRANSCRIBE_PARALLELISM))
        for i in range(0, len(pending), width):
            self._check_budget(ctx)
            batch = pending[i:i + width]
            results = await asyncio.gather(
                *[self._transcribe_one(ctx, c) for c in batch], return_exceptions=True
            )
            ok = [c["index"] for c, r in zip(batch, results) if not isinstance(r, BaseException)]
            if ok:
                def mutate(doc, ok=ok):
                    merged = sorted(set(doc["checkpoints"].get("transcribed", [])) | set(ok))
                    doc["checkpoints"]["transcribed"] = merged
                    doc["progress"] = max(int(doc.get("progress") or 0), 15 + int(55 * len(merged) / total))
                    doc["message"] = f"Transcribing audio ({len(merged)}/{total} chunks)"

                await self._save(ctx, mutate)
            errors = [r for r in results if isinstance(r, BaseException)]
            if errors:
                raise errors[0]

    async def _step_slides(self, ctx: _Ctx) -> None:
        if "slides" in ctx.doc["checkpoints"]:
            return
        deck_uri = ctx.doc["input"].get("presentation_uri")
        if not deck_uri:
            await self._set_progress(ctx, 75, "No presentation; skipping slides", slides=[])
            return
        self._check_budget(ctx)
        await self._set_progress(ctx, 72, "Rendering slides")
        try:
            info = await asyncio.to_thread(self.gcs.stat, deck_uri)
        except ObjectNotReadable:
            raise PermanentJobError(f"presentation_uri is not readable by the service account: {deck_uri}")
        if info is None:
            raise PermanentJobError(f"presentation_uri not found: {deck_uri}")
        suffix = Path(parse_gs_uri(deck_uri).name).suffix.lower()
        local = os.path.join(ctx.workdir, f"deck{suffix}")
        await asyncio.to_thread(self.gcs.download_to_file, deck_uri, local)
        out_dir = os.path.join(ctx.workdir, "slides")
        os.makedirs(out_dir, exist_ok=True)
        paths = await self.steps.render_slides(local, out_dir)
        uris = []
        for n, p in enumerate(paths, 1):
            uri = self.out_uri(ctx.job_id, f"slides/{n:02d}.jpg")
            await asyncio.to_thread(self.gcs.upload_file, p, uri, "image/jpeg")
            uris.append(uri)
        await self._set_progress(ctx, 80, f"Rendered {len(uris)} slides", slides=uris)

    async def _load_transcript(self, ctx: _Ctx) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        segments: List[Dict[str, Any]] = []
        language = None
        for c in sorted(ctx.doc["checkpoints"]["audio"]["chunks"], key=lambda c: c["index"]):
            uri = self.work_uri(ctx.job_id, f"transcripts/chunk_{c['index']:03d}.json")
            got = await asyncio.to_thread(self.gcs.read_bytes, uri)
            if got is None:
                idx = c["index"]

                def forget(doc, idx=idx):
                    doc["checkpoints"]["transcribed"] = [
                        i for i in doc["checkpoints"].get("transcribed", []) if i != idx
                    ]

                await self._save(ctx, forget)
                raise RuntimeError(f"Transcript for chunk {idx} is missing; it will be redone")
            data = json.loads(got[0])
            segments.extend(data["segments"])
            language = language or data.get("language")
        return segments, language

    async def _step_finish(self, ctx: _Ctx) -> None:
        self._check_budget(ctx)
        await self._set_progress(ctx, 82, "Generating chapters")
        job_id = ctx.job_id
        segments, _language = await self._load_transcript(ctx)
        duration = ctx.doc["checkpoints"]["audio"].get("duration")
        slides: List[str] = ctx.doc["checkpoints"].get("slides", [])

        srt_uri = self.out_uri(job_id, "subtitles.srt")
        await asyncio.to_thread(
            self.gcs.upload_bytes, format_srt(segments).encode(), srt_uri,
            "application/x-subrip", None,
        )
        await asyncio.to_thread(
            self.gcs.upload_bytes, json.dumps(segments).encode(),
            self.out_uri(job_id, "transcript.json"), "application/json", None,
        )

        raw_chapters: List[Dict[str, Any]] = []
        if segments:
            transcription = {
                "full_text": " ".join(s["text"] for s in segments),
                "segments": segments,
                "duration": duration,
            }
            raw_chapters = await self.steps.generate_chapters(
                transcription, len(slides), ctx.doc["input"].get("title")
            )

        qa_uri = None
        if any(str(c.get("image_name")) == "qa" for c in raw_chapters):
            qa_local = next((p for p in QA_IMAGE_CANDIDATES if p.exists()), None)
            if qa_local is not None:
                qa_uri = self.out_uri(job_id, "slides/qa.jpg")
                await asyncio.to_thread(self.gcs.upload_file, str(qa_local), qa_uri, "image/jpeg")

        chapters = []
        for c in raw_chapters:
            image = str(c.get("image_name", ""))
            slide_uri = None
            if image == "qa":
                slide_uri = qa_uri
            elif image.isdigit() and 1 <= int(image) <= len(slides):
                slide_uri = slides[int(image) - 1]
            chapters.append({
                "start_seconds": float(c["time_seconds"]),
                "title": c["description"],
                "description": None,
                "slide_uri": slide_uri,
            })

        result = {
            "chapters": chapters,
            "srt_uri": srt_uri,
            "transcript": segments,
            "slides": slides,
            "qa_slide_uri": qa_uri,
            "duration_seconds": float(duration) if duration is not None else None,
        }
        await self.store.put_result(job_id, result)

        def complete(doc):
            transition(doc, COMPLETED, self.now())
            doc["progress"] = 100
            doc["message"] = "Completed"
            doc["error"] = None
            doc["task"]["lease_owner"] = None
            doc["task"]["lease_expires_at"] = None

        await self._save(ctx, complete)
        try:
            await asyncio.to_thread(self.gcs.delete_prefix, self.output_bucket, f"work/{job_id}/")
        except Exception:
            logger.warning("Could not clean up work files for %s", job_id, exc_info=True)

    # -- stale job detection (called from status reads) -----------------------

    async def reap_if_stale(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc["status"] in TERMINAL:
            return doc
        stale = timedelta(seconds=int(self.cfg.JOB_STALE_SECONDS))

        def is_stale(d) -> bool:
            now = self.now()
            hb = parse_iso(d.get("heartbeat_at")) or parse_iso(d["updated_at"])
            exp = parse_iso(d["task"].get("lease_expires_at"))
            return (
                d["status"] not in TERMINAL
                and hb is not None and now - hb > stale
                and (exp is None or exp <= now)
            )

        if not is_stale(doc):
            return doc

        def mutate(d):
            if not is_stale(d):
                raise _Skip("no longer stale")
            minutes = int(stale.total_seconds() // 60)
            transition(d, FAILED, self.now())
            d["error"] = f"Job stopped making progress (no worker activity for {minutes} minutes)"
            d["message"] = "Failed"

        try:
            return await self.store.update(doc["job_id"], mutate)
        except _Skip:
            return await self.store.get(doc["job_id"]) or doc


class _Busy(Exception):
    pass


class _Skip(Exception):
    pass
