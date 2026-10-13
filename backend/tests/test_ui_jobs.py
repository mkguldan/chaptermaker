"""Web UI jobs run inside a Cloud Tasks request, not as a BackgroundTask."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.internal import get_video_processor
from app.core.config import settings
from app.main import app
from app.schemas.job import JobStatus, JobStatusEnum
from app.services.api_jobs import get_api_job_service
from app.services.video_processor import VideoProcessorService

from .conftest import RecordingDispatcher

JOB = "job_0123456789ab"
HEADERS = {"x-cloudtasks-queuename": "video-processing"}


class FakeJobManager:
    def __init__(self):
        self.jobs = {}

    async def get_job(self, job_id):
        return self.jobs.get(job_id)

    async def update_job(self, job_id, status, progress=None, message=None, error=None):
        job = self.jobs[job_id]
        job.status = status
        if error is not None:
            job.error = error
        return True


class FakeProcessor:
    def __init__(self):
        self.job_manager = FakeJobManager()
        self.ran = []

    async def create_processing_job(self, video_path, presentation_path, options):
        now = datetime.utcnow()
        self.job_manager.jobs[JOB] = JobStatus(
            job_id=JOB, status=JobStatusEnum.PENDING, video_path=video_path,
            presentation_path=presentation_path, created_at=now, updated_at=now,
        )
        return JOB

    async def process_video_async(self, job_id):
        self.ran.append(job_id)
        await self.job_manager.update_job(job_id, JobStatusEnum.COMPLETED)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(settings, "CLOUD_TASKS_QUEUE", "video-processing")
    dispatcher = RecordingDispatcher()
    processor = FakeProcessor()
    app.dependency_overrides[get_api_job_service] = lambda: SimpleNamespace(dispatcher=dispatcher)
    app.dependency_overrides[VideoProcessorService] = lambda: processor
    app.dependency_overrides[get_video_processor] = lambda: processor
    with TestClient(app) as c:
        yield SimpleNamespace(client=c, dispatcher=dispatcher, processor=processor)
    app.dependency_overrides.clear()


def start(client):
    return client.post("/api/v1/videos/process", json={
        "video_path": "uploads/talk.mp4", "presentation_path": "uploads/deck.pdf", "options": {},
    })


def test_process_enqueues_a_task_instead_of_running(setup):
    r = start(setup.client)
    assert r.status_code == 200, r.text
    assert r.json()["job_id"] == JOB
    assert setup.dispatcher.enqueued == [(JOB, "ui")]
    assert setup.processor.ran == []


def test_enqueue_failure_fails_the_job(setup):
    setup.dispatcher.fail = True
    r = start(setup.client)
    assert r.status_code == 503
    assert setup.processor.job_manager.jobs[JOB].status == JobStatusEnum.FAILED


def test_task_runs_a_pending_job_once(setup):
    start(setup.client)
    r = setup.client.post(f"/internal/run-ui/{JOB}", headers=HEADERS)
    assert r.status_code == 200 and r.json()["action"] == "ran"
    again = setup.client.post(f"/internal/run-ui/{JOB}", headers=HEADERS)
    assert again.json()["action"] == "noop"
    assert setup.processor.ran == [JOB]


def test_redelivery_while_processing_fails_the_job(setup):
    start(setup.client)
    setup.processor.job_manager.jobs[JOB].status = JobStatusEnum.PROCESSING
    r = setup.client.post(f"/internal/run-ui/{JOB}", headers=HEADERS)
    assert r.json()["action"] == "failed"
    assert setup.processor.job_manager.jobs[JOB].status == JobStatusEnum.FAILED
    assert setup.processor.ran == []


def test_run_ui_requires_cloud_tasks_header(setup):
    start(setup.client)
    assert setup.client.post(f"/internal/run-ui/{JOB}").status_code == 403


def test_run_ui_unknown_job_is_noop(setup):
    r = setup.client.post("/internal/run-ui/job_ffffffffffff", headers=HEADERS)
    assert r.status_code == 200 and r.json()["action"] == "noop"
    assert setup.client.post("/internal/run-ui/../etc", headers=HEADERS).status_code in (200, 404)
