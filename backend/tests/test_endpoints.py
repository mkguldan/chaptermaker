"""HTTP contract for Inframe: POST /api/v1/jobs, GET status/result, /internal/run."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.api_jobs import get_api_job_service

from .conftest import OUT

VIDEO = "gs://inframe-bucket/events/e1/talk.mp4"
DECK = "gs://inframe-bucket/events/e1/deck.pdf"


@pytest.fixture
def client(env, monkeypatch):
    monkeypatch.setattr(settings, "CLOUD_TASKS_QUEUE", "video-processing")
    app.dependency_overrides[get_api_job_service] = lambda: env.service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def create(client, **body):
    payload = {"video_uri": VIDEO, "presentation_uri": DECK, "title": "Keynote", "language": "en"}
    payload.update(body)
    return client.post("/api/v1/jobs", json=payload)


def test_create_job_returns_202_and_enqueues(client, env):
    r = create(client)
    assert r.status_code == 202
    body = r.json()
    assert set(body) == {"job_id", "status"} and body["status"] == "queued"
    job_id = body["job_id"]
    assert job_id.startswith("job_") and len(job_id) == 36
    assert env.dispatcher.enqueued == [(job_id, 0)]
    doc = json.loads(env.gcs.objects[f"gs://{OUT}/job-tracking/{job_id}.json"][0])
    assert doc["kind"] == "api" and doc["input"]["video_uri"] == VIDEO
    # Cloud Run terminates TLS, so non-local hosts are always https
    assert env.dispatcher.learned == ["https://testserver"]


def test_create_job_without_optional_fields(client):
    r = client.post("/api/v1/jobs", json={"video_uri": VIDEO})
    assert r.status_code == 202


def test_create_job_no_trailing_slash_redirect(client):
    r = client.post("/api/v1/jobs", json={"video_uri": VIDEO}, follow_redirects=False)
    assert r.status_code == 202


@pytest.mark.parametrize("body", [
    {"video_uri": "https://example.com/v.mp4"},
    {"video_uri": "gs://bucket"},
    {"video_uri": VIDEO, "presentation_uri": "gs://inframe-bucket/deck.txt"},
    {},
])
def test_create_job_rejects_invalid_input(client, env, body):
    r = client.post("/api/v1/jobs", json=body)
    assert r.status_code == 422
    assert env.dispatcher.enqueued == []


def test_create_job_missing_object(client, env):
    r = create(client, video_uri="gs://inframe-bucket/nope.mp4")
    assert r.status_code == 422 and "not found" in r.json()["detail"]
    assert env.dispatcher.enqueued == []


def test_create_job_unreadable_object(client, env):
    env.gcs.forbidden.add(VIDEO)
    r = create(client)
    assert r.status_code == 422 and "not readable" in r.json()["detail"]


def test_create_job_bucket_allowlist(client, env):
    env.service.allowed_buckets = {"other-bucket"}
    r = create(client)
    assert r.status_code == 422 and "not allowed" in r.json()["detail"]


def test_create_job_enqueue_failure_returns_503_and_fails_job(client, env):
    env.dispatcher.fail = True
    r = create(client)
    assert r.status_code == 503
    docs = [json.loads(v[0]) for k, v in env.gcs.objects.items() if "/job-tracking/" in k]
    assert len(docs) == 1 and docs[0]["status"] == "failed"


def test_status_shape(client):
    job_id = create(client).json()["job_id"]
    r = client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"job_id", "status", "progress", "message", "error",
                         "created_at", "updated_at"}
    assert body["status"] == "queued" and body["progress"] == 0 and body["error"] is None


def test_status_unknown_job(client):
    assert client.get("/api/v1/jobs/job_" + "b" * 32).status_code == 404
    assert client.get("/api/v1/jobs/bad..id").status_code == 404


def test_legacy_job_status_unchanged(client, env):
    legacy = {
        "job_id": "job_123456789abc", "status": "processing", "progress": 30,
        "message": "Transcribing", "video_path": "uploads/x/v.mp4",
        "presentation_path": "uploads/x/d.pdf",
        "created_at": "2026-10-01T10:00:00", "updated_at": "2026-10-01T10:05:00",
        "completed_at": None, "error": None, "metadata": {"options": {}},
    }
    env.gcs.put(f"gs://{OUT}/job-tracking/job_123456789abc.json", json.dumps(legacy).encode())
    r = client.get("/api/v1/jobs/job_123456789abc")
    assert r.status_code == 200
    body = r.json()
    assert body["video_path"] == "uploads/x/v.mp4" and body["status"] == "processing"
    assert body["metadata"] == {"options": {}}
    # the new /result endpoint does not serve legacy jobs
    assert client.get("/api/v1/jobs/job_123456789abc/result").status_code == 404


def test_result_lifecycle(client, env):
    job_id = create(client).json()["job_id"]
    r = client.get(f"/api/v1/jobs/{job_id}/result")
    assert r.status_code == 409 and "queued" in r.json()["detail"]

    run = client.post(f"/internal/run/{job_id}", json={"seq": 0},
                      headers={"X-CloudTasks-QueueName": "video-processing"})
    assert run.status_code == 200 and run.json()["action"] == "completed"

    status = client.get(f"/api/v1/jobs/{job_id}").json()
    assert status["status"] == "completed" and status["progress"] == 100

    r = client.get(f"/api/v1/jobs/{job_id}/result")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"chapters", "srt_uri", "transcript", "slides", "qa_slide_uri",
                         "duration_seconds"}
    assert set(body["chapters"][0]) == {"start_seconds", "title", "description", "slide_uri"}
    assert body["srt_uri"].startswith(f"gs://{OUT}/outputs/{job_id}/")
    assert set(body["transcript"][0]) == {"start", "end", "text"}

    # retried delivery of a completed job: 200 no-op
    again = client.post(f"/internal/run/{job_id}", json={"seq": 0},
                        headers={"X-CloudTasks-QueueName": "video-processing"})
    assert again.status_code == 200 and again.json()["action"] == "noop"


def test_result_unknown_job(client):
    assert client.get("/api/v1/jobs/job_" + "c" * 32 + "/result").status_code == 404


def test_internal_run_requires_cloud_tasks_header(client):
    job_id = create(client).json()["job_id"]
    assert client.post(f"/internal/run/{job_id}", json={"seq": 0}).status_code == 403
    wrong = client.post(f"/internal/run/{job_id}", json={"seq": 0},
                        headers={"X-CloudTasks-QueueName": "other"})
    assert wrong.status_code == 403


def test_internal_run_retry_returns_5xx(client, env):
    job_id = create(client).json()["job_id"]
    env.steps.audio_error = RuntimeError("transient")
    r = client.post(f"/internal/run/{job_id}", json={"seq": 0},
                    headers={"X-CloudTasks-QueueName": "video-processing"})
    assert r.status_code == 500 and r.json()["action"] == "retry"
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "processing"


def test_internal_run_without_queue_configured(client, env, monkeypatch):
    monkeypatch.setattr(settings, "CLOUD_TASKS_QUEUE", "")
    job_id = create(client).json()["job_id"]
    r = client.post(f"/internal/run/{job_id}", json={"seq": 0})
    assert r.status_code == 200 and r.json()["action"] == "completed"
