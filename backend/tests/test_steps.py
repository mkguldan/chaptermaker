"""PipelineSteps with ffmpeg and OpenAI stubbed out."""

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import api_pipeline
from app.services.api_pipeline import PermanentJobError, PipelineSteps, format_srt

from .conftest import FakeGcs, make_cfg

VIDEO = "gs://inframe-bucket/events/e1/talk.mp4"


def fake_ffmpeg(calls, returncode=0, stderr="", chunks=2):
    def run(cmd, **kw):
        calls.append(cmd)
        if returncode == 0:
            out_pattern = Path(cmd[-1])
            list_path = Path(cmd[cmd.index("-segment_list") + 1])
            rows = []
            for i in range(chunks):
                name = out_pattern.name % i
                (out_pattern.parent / name).write_bytes(b"mp3")
                rows.append(f"{name},{i * 600.0:.6f},{(i + 1) * 600.0 - (0 if i < chunks - 1 else 345.5):.6f}")
            list_path.write_text("\n".join(rows) + "\n")
        return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")
    return run


async def test_small_input_is_downloaded_and_segmented(tmp_path, monkeypatch):
    gcs = FakeGcs()
    gcs.put(VIDEO, b"v" * 100)
    calls = []
    monkeypatch.setattr(api_pipeline.subprocess, "run", fake_ffmpeg(calls))
    chunks, duration = await PipelineSteps(gcs, make_cfg()).make_audio_chunks(VIDEO, str(tmp_path), 600)
    cmd = calls[0]
    assert cmd[0] == "ffmpeg" and "-headers" not in cmd
    assert cmd[cmd.index("-i") + 1].endswith("input.mp4")
    assert cmd[cmd.index("-segment_time") + 1] == "600"
    assert [(c.index, c.start, c.end) for c in chunks] == [(0, 0.0, 600.0), (1, 600.0, 854.5)]
    assert duration == 854.5
    assert not (tmp_path / "input.mp4").exists()  # input removed after extraction


async def test_large_input_is_streamed_and_token_not_logged(tmp_path, monkeypatch, caplog):
    gcs = FakeGcs()
    gcs.put(VIDEO, b"v" * 2048)
    calls = []
    monkeypatch.setattr(api_pipeline.subprocess, "run", fake_ffmpeg(calls))
    cfg = make_cfg(STREAM_INPUT_THRESHOLD_MB=0)
    with caplog.at_level(logging.DEBUG):
        await PipelineSteps(gcs, cfg).make_audio_chunks(VIDEO, str(tmp_path), 600)
    cmd = calls[0]
    assert cmd[cmd.index("-headers") + 1] == "Authorization: Bearer fake-token\r\n"
    assert cmd[cmd.index("-i") + 1] == "https://storage.googleapis.com/inframe-bucket/events/e1/talk.mp4"
    assert "fake-token" not in caplog.text


async def test_no_audio_track_is_permanent(tmp_path, monkeypatch):
    gcs = FakeGcs()
    gcs.put(VIDEO, b"v")
    monkeypatch.setattr(api_pipeline.subprocess, "run", fake_ffmpeg(
        [], returncode=1, stderr="Stream map '0:a:0' matches no streams."))
    with pytest.raises(PermanentJobError):
        await PipelineSteps(gcs, make_cfg()).make_audio_chunks(VIDEO, str(tmp_path), 600)


async def test_other_ffmpeg_errors_are_retryable(tmp_path, monkeypatch):
    gcs = FakeGcs()
    gcs.put(VIDEO, b"v")
    monkeypatch.setattr(api_pipeline.subprocess, "run", fake_ffmpeg(
        [], returncode=1, stderr="Connection reset by peer"))
    with pytest.raises(RuntimeError) as e:
        await PipelineSteps(gcs, make_cfg()).make_audio_chunks(VIDEO, str(tmp_path), 600)
    assert not isinstance(e.value, PermanentJobError)


async def test_missing_video_is_permanent(tmp_path):
    with pytest.raises(PermanentJobError):
        await PipelineSteps(FakeGcs(), make_cfg()).make_audio_chunks(VIDEO, str(tmp_path), 600)


async def test_transcribe_chunk_uses_whisper(tmp_path, monkeypatch):
    seen = {}

    class FakeTranscriptions:
        def create(self, **kw):
            seen.update(kw)
            seg = SimpleNamespace(start=0.5, end=2.0, text=" hi ")
            return SimpleNamespace(segments=[seg], language="danish")

    steps = PipelineSteps(FakeGcs(), make_cfg())
    steps._openai = SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions()))
    p = tmp_path / "chunk_000.mp3"
    p.write_bytes(b"mp3")
    out = await steps.transcribe_chunk(str(p), "da")
    assert seen["model"] == "whisper-1" and seen["language"] == "da"
    assert seen["response_format"] == "verbose_json"
    assert out == {"segments": [{"start": 0.5, "end": 2.0, "text": " hi "}], "language": "danish"}
    seen.clear()
    await steps.transcribe_chunk(str(p), None)
    assert "language" not in seen  # auto-detect


async def test_chapter_generation_runs_off_loop_with_title():
    from app.services.chapter_generation import ChapterGenerationService

    captured = {}

    class FakeResponses:
        def create(self, **kw):
            captured.update(kw)
            call = SimpleNamespace(type="function_call", name="create_chapters", arguments=json.dumps(
                {"chapters": [{"timestamp_seconds": 3, "slide_number": 0, "title": "Opening", "is_qa": False}]}))
            return SimpleNamespace(output=[call], id="r1")

    svc = ChapterGenerationService.__new__(ChapterGenerationService)
    svc.client = SimpleNamespace(responses=FakeResponses())
    chapters = await svc.generate_chapters(
        transcription={"full_text": "hello", "segments": [{"start": 3, "end": 5, "text": "hello"}], "duration": 5},
        slide_count=0, title="Future of Events",
    )
    assert chapters == [{"time_seconds": 3, "image_name": "0", "description": "Opening"}]
    assert "Talk title: Future of Events" in captured["input"]
    assert "No presentation slides were provided" in captured["input"]


def test_srt_format():
    srt = format_srt([{"start": 3661.5, "end": 3662.0, "text": "hi"}])
    assert srt.startswith("1\n01:01:01,500 --> 01:01:02,000\nhi\n")
