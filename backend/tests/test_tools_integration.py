"""Runs the real ffmpeg / pdftoppm when installed (CI installs both)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.api_pipeline import PermanentJobError, PipelineSteps
from app.services.presentation import PresentationService

from .conftest import FakeGcs, make_cfg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
needs_pdftoppm = pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="poppler not installed")


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@needs_ffmpeg
async def test_real_ffmpeg_extracts_and_chunks_audio(tmp_path):
    src = tmp_path / "talk.mp4"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=25",
           "-f", "lavfi", "-i", "color=c=black:s=64x64:d=25",
           "-shortest", "-c:a", "aac", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src))
    gcs = FakeGcs()
    gcs.put("gs://inframe-bucket/talk.mp4", src.read_bytes())
    work = tmp_path / "work"
    work.mkdir()
    chunks, duration = await PipelineSteps(gcs, make_cfg()).make_audio_chunks(
        "gs://inframe-bucket/talk.mp4", str(work), 10)
    assert len(chunks) == 3
    assert chunks[0].start == 0 and abs(chunks[1].start - 10) < 0.5
    assert abs(duration - 25) < 1
    assert all(Path(c.path).stat().st_size > 0 for c in chunks)


@needs_ffmpeg
async def test_real_ffmpeg_video_without_audio_is_permanent(tmp_path):
    src = tmp_path / "silent.mp4"
    ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=2", "-pix_fmt", "yuv420p", str(src))
    gcs = FakeGcs()
    gcs.put("gs://inframe-bucket/silent.mp4", src.read_bytes())
    with pytest.raises(PermanentJobError):
        await PipelineSteps(gcs, make_cfg()).make_audio_chunks(
            "gs://inframe-bucket/silent.mp4", str(tmp_path), 10)


@needs_pdftoppm
async def test_real_pdf_rendering(tmp_path):
    from PIL import Image

    pdf = tmp_path / "deck.pdf"
    pages = [Image.new("RGB", (320, 180), c) for c in ("red", "green", "blue")]
    pages[0].save(pdf, "PDF", save_all=True, append_images=pages[1:])
    svc = PresentationService.__new__(PresentationService)  # no GCS client needed
    slides = await svc.extract_slides_from_local(str(pdf), "jpg")
    assert [s["filename"] for s in slides] == ["01.jpg", "02.jpg", "03.jpg"]
    assert all(Path(s["local_path"]).read_bytes()[:2] == b"\xff\xd8" for s in slides)
