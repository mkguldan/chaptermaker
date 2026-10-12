import asyncio
import json

import pytest
from google.api_core import exceptions as gexc

from app.services.api_job_store import new_job_doc
from app.services.api_jobs import ApiJobService, build_service
from app.services.task_dispatcher import CloudTasksDispatcher, InlineDispatcher, task_id_for


class FakeTasksClient:
    def __init__(self, error=None):
        self.created = []
        self.error = error

    def queue_path(self, project, location, queue):
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def create_task(self, parent, task):
        if self.error:
            raise self.error
        self.created.append((parent, task))
        return task


def make(client, **kw):
    args = dict(project="p1", location="europe-west1", queue="video-processing",
                service_url="https://chaptermaker-123.europe-west1.run.app/",
                service_account="chaptermaker-runner@p1.iam.gserviceaccount.com",
                dispatch_deadline_seconds=1800, client=client)
    args.update(kw)
    return CloudTasksDispatcher(**args)


async def test_cloud_task_shape():
    client = FakeTasksClient()
    job = "job_" + "d" * 32
    await make(client).enqueue(job, 2)
    parent, task = client.created[0]
    assert parent == "projects/p1/locations/europe-west1/queues/video-processing"
    assert task["name"] == f"{parent}/tasks/{'d' * 32}-2"
    http = task["http_request"]
    assert http["http_method"] == "POST"
    assert http["url"] == f"https://chaptermaker-123.europe-west1.run.app/internal/run/{job}"
    assert json.loads(http["body"]) == {"seq": 2}
    assert http["oidc_token"] == {
        "service_account_email": "chaptermaker-runner@p1.iam.gserviceaccount.com",
        "audience": "https://chaptermaker-123.europe-west1.run.app",
    }
    assert task["dispatch_deadline"].seconds == 1800


async def test_dispatch_deadline_clamped_to_cloud_tasks_max():
    client = FakeTasksClient()
    await make(client, dispatch_deadline_seconds=3600).enqueue("job_" + "e" * 32, 0)
    assert client.created[0][1]["dispatch_deadline"].seconds == 1800


async def test_already_exists_is_success():
    client = FakeTasksClient(error=gexc.AlreadyExists("dup"))
    await make(client).enqueue("job_" + "e" * 32, 0)  # no raise


async def test_other_errors_propagate():
    client = FakeTasksClient(error=gexc.ServiceUnavailable("down"))
    with pytest.raises(gexc.ServiceUnavailable):
        await make(client).enqueue("job_" + "e" * 32, 0)


async def test_service_url_learned_from_request_when_unset():
    client = FakeTasksClient()
    d = make(client, service_url="")
    with pytest.raises(RuntimeError):
        await d.enqueue("job_" + "e" * 32, 0)
    d.learn_service_url("https://svc.a.run.app")
    d.learn_service_url("https://ignored.example")
    await d.enqueue("job_" + "e" * 32, 0)
    assert client.created[0][1]["http_request"]["url"].startswith("https://svc.a.run.app/internal/run/")


def test_task_ids_are_deterministic():
    assert task_id_for("job_abc", 3) == "abc-3"


def test_build_service_selects_dispatcher(monkeypatch):
    from types import SimpleNamespace
    from .conftest import make_cfg

    base = make_cfg(GCP_PROJECT_ID="p1", GCS_OUTPUT_BUCKET="out", CLOUD_TASKS_LOCATION="europe-west1",
                    SERVICE_URL="", TASKS_SERVICE_ACCOUNT="", TASK_DISPATCH_DEADLINE_SECONDS=1800,
                    ALLOWED_INPUT_BUCKETS=" a-bucket ; b-bucket,")
    inline = build_service(SimpleNamespace(**{**vars(base), "CLOUD_TASKS_QUEUE": ""}))
    assert isinstance(inline.dispatcher, InlineDispatcher) and inline.dispatcher.run is not None
    assert inline.allowed_buckets == {"a-bucket", "b-bucket"}
    tasks = build_service(SimpleNamespace(**{**vars(base), "CLOUD_TASKS_QUEUE": "video-processing"}))
    assert isinstance(tasks.dispatcher, CloudTasksDispatcher)


async def test_inline_dispatcher_runs_job(env):
    inline = InlineDispatcher()
    env.runner.dispatcher = inline
    inline.run = env.runner.run
    service = ApiJobService(env.store, env.gcs, env.runner, inline)
    from app.schemas.api_job import CreateJobRequest

    job_id = await service.create_job(CreateJobRequest(video_uri="gs://inframe-bucket/events/e1/talk.mp4"))
    for _ in range(100):
        await asyncio.sleep(0)
        if (await env.store.get(job_id))["status"] == "completed":
            break
    assert (await env.store.get(job_id))["status"] == "completed"
