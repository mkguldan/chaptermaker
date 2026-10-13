"""
Shared fakes: an in-memory GCS (with generation preconditions), a recording
task dispatcher and scripted pipeline steps. No network, no ffmpeg, no OpenAI.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("GCS_OUTPUT_BUCKET", "out-bucket")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.api_job_store import ApiJobStore  # noqa: E402
from app.services.api_pipeline import ApiJobRunner, AudioChunk, PermanentJobError  # noqa: E402
from app.services.api_jobs import ApiJobService  # noqa: E402
from app.services.gcs_io import GenerationMismatch, ObjectInfo, ObjectNotReadable, parse_gs_uri  # noqa: E402
from app.services.task_dispatcher import Dispatcher  # noqa: E402

OUT = "out-bucket"


class FakeGcs:
    def __init__(self):
        self.objects = {}  # uri -> [bytes, generation, content_type]
        self.forbidden = set()
        self._gen = 0

    def put(self, uri, data=b"x", content_type=None):
        self._gen += 1
        self.objects[uri] = [data, self._gen, content_type]

    def stat(self, uri):
        parse_gs_uri(uri)
        if uri in self.forbidden:
            raise ObjectNotReadable(uri)
        obj = self.objects.get(uri)
        return None if obj is None else ObjectInfo(size=len(obj[0]), content_type=obj[2])

    def download_to_file(self, uri, path):
        Path(path).write_bytes(self.objects[uri][0])

    def upload_file(self, path, uri, content_type=None):
        self.put(uri, Path(path).read_bytes(), content_type)
        return uri

    def upload_bytes(self, data, uri, content_type="application/octet-stream", if_generation_match=None):
        current = self.objects.get(uri)
        if if_generation_match is not None:
            if (current[1] if current else 0) != if_generation_match:
                raise GenerationMismatch(uri)
        self.put(uri, data, content_type)
        return self._gen

    def read_bytes(self, uri):
        obj = self.objects.get(uri)
        return None if obj is None else (obj[0], obj[1])

    def delete_prefix(self, bucket, prefix):
        doomed = [u for u in self.objects if u.startswith(f"gs://{bucket}/{prefix}")]
        for u in doomed:
            del self.objects[u]
        return len(doomed)

    def access_token(self):
        return "fake-token"


class RecordingDispatcher(Dispatcher):
    inline = False

    def __init__(self):
        self.enqueued = []
        self.fail = False
        self.learned = []

    def learn_service_url(self, url):
        self.learned.append(url)

    async def enqueue(self, job_id, seq):
        if self.fail:
            raise RuntimeError("cloud tasks unavailable")
        self.enqueued.append((job_id, seq))

    async def enqueue_ui(self, job_id):
        if self.fail:
            raise RuntimeError("cloud tasks unavailable")
        self.enqueued.append((job_id, "ui"))


class FakeSteps:
    """Scripted stand-in for ffmpeg / Whisper / slide rendering / GPT-5."""

    def __init__(self, n_chunks=3, chunk_seconds=600.0):
        self.n_chunks = n_chunks
        self.chunk_seconds = chunk_seconds
        self.calls = {"audio": 0, "transcribe": [], "slides": 0, "chapters": 0}
        self.fail_transcribe = {}  # chunk index -> exception to raise once
        self.audio_error = None
        self.chapters = [
            {"time_seconds": 0, "image_name": "1", "description": "Intro"},
            {"time_seconds": 700, "image_name": "2", "description": "Main topic"},
            {"time_seconds": 1300, "image_name": "qa", "description": "Q&A #1"},
        ]
        self.on_transcribe = None

    async def make_audio_chunks(self, video_uri, workdir, chunk_seconds):
        self.calls["audio"] += 1
        if self.audio_error:
            raise self.audio_error
        chunks = []
        for i in range(self.n_chunks):
            p = Path(workdir) / f"chunk_{i:03d}.mp3"
            p.write_bytes(f"audio{i}".encode())
            start = i * self.chunk_seconds
            chunks.append(AudioChunk(i, str(p), start, start + self.chunk_seconds))
        return chunks, self.n_chunks * self.chunk_seconds

    async def transcribe_chunk(self, path, language):
        idx = int(Path(path).stem.split("_")[-1])
        self.calls["transcribe"].append(idx)
        if self.on_transcribe:
            self.on_transcribe(idx)
        if idx in self.fail_transcribe:
            raise self.fail_transcribe.pop(idx)
        return {
            "segments": [
                {"start": 1.0, "end": 4.0, "text": f" chunk {idx} first "},
                {"start": 5.0, "end": 9.5, "text": f"chunk {idx} second"},
            ],
            "language": language or "en",
        }

    async def render_slides(self, deck_path, out_dir):
        self.calls["slides"] += 1
        paths = []
        for i in range(1, 3):
            p = Path(out_dir) / f"s{i}.jpg"
            p.write_bytes(b"jpg")
            paths.append(str(p))
        return paths

    async def generate_chapters(self, transcription, slide_count, title):
        self.calls["chapters"] += 1
        self.last_chapter_args = (transcription, slide_count, title)
        return [dict(c) for c in self.chapters]


class Clock:
    def __init__(self):
        self.t = 0.0
        self.wall = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def monotonic(self):
        return self.t

    def now(self):
        return self.wall + timedelta(seconds=self.t)

    async def sleep(self, seconds):
        self.t += seconds


def make_cfg(**over):
    base = dict(
        TASK_MAX_ATTEMPTS=3,
        TASK_SOFT_BUDGET_SECONDS=600,
        JOB_LEASE_SECONDS=120,
        JOB_STALE_SECONDS=3600,
        TRANSCRIBE_CHUNK_SECONDS=600,
        TRANSCRIBE_PARALLELISM=2,
        STREAM_INPUT_THRESHOLD_MB=512,
        FFMPEG_TIMEOUT_SECONDS=60,
        TRANSCRIPTION_MODEL="whisper-1",
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def env():
    gcs = FakeGcs()
    gcs.put("gs://inframe-bucket/events/e1/talk.mp4", b"video-bytes")
    gcs.put("gs://inframe-bucket/events/e1/deck.pdf", b"%PDF")
    store = ApiJobStore(gcs, OUT)
    steps = FakeSteps()
    dispatcher = RecordingDispatcher()
    clock = Clock()
    cfg = make_cfg()
    runner = ApiJobRunner(
        store, gcs, steps, dispatcher, cfg, output_bucket=OUT,
        monotonic=clock.monotonic, now=clock.now, sleep=clock.sleep, poll_seconds=5,
    )
    service = ApiJobService(store, gcs, runner, dispatcher)
    return SimpleNamespace(
        gcs=gcs, store=store, steps=steps, dispatcher=dispatcher, clock=clock,
        cfg=cfg, runner=runner, service=service,
    )


__all__ = ["PermanentJobError"]
