"""
Dispatches job-runner tasks.

CloudTasksDispatcher: creates an HTTP task that POSTs /internal/run/{job_id}
on this same service with an OIDC token, so the work happens inside a request
(Cloud Run keeps CPU allocated) and is retried by the queue if the instance
dies. Web UI jobs (POST /api/v1/videos/process) go the same way to
/internal/run-ui/{job_id}.

InlineDispatcher: local/dev fallback used when CLOUD_TASKS_QUEUE is not set;
runs the job in this process with asyncio.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional, Set

logger = logging.getLogger(__name__)

INTERNAL_RUN_PATH = "/internal/run"
UI_RUN_PATH = "/internal/run-ui"
METADATA_SA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
)


def task_id_for(job_id: str, seq: int) -> str:
    """Deterministic task name -> Cloud Tasks de-duplicates repeated enqueues.

    Starts with the random part of the job id, as Google recommends for task
    name sharding.
    """
    return f"{job_id.split('_', 1)[-1]}-{seq}"


def ui_task_id_for(job_id: str) -> str:
    """Task name for a web UI job: one task per job."""
    return f"{job_id.split('_', 1)[-1]}-ui"


class Dispatcher:
    inline = False

    def learn_service_url(self, url: str) -> None:  # pragma: no cover - default
        pass

    async def enqueue(self, job_id: str, seq: int) -> None:
        raise NotImplementedError

    async def enqueue_ui(self, job_id: str) -> None:
        raise NotImplementedError


class InlineDispatcher(Dispatcher):
    inline = True

    def __init__(self, run: Optional[Callable[[str, int], Awaitable[object]]] = None):
        self.run = run
        self._tasks: Set[asyncio.Task] = set()

    async def enqueue(self, job_id: str, seq: int) -> None:
        if self.run is None:
            raise RuntimeError("InlineDispatcher has no runner attached")
        task = asyncio.create_task(self.run(job_id, seq))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class CloudTasksDispatcher(Dispatcher):
    def __init__(
        self,
        project: str,
        location: str,
        queue: str,
        service_url: str = "",
        service_account: str = "",
        dispatch_deadline_seconds: int = 1800,
        client=None,
    ):
        self.project = project
        self.location = location
        self.queue = queue
        self.service_url = service_url.rstrip("/")
        self.service_account = service_account
        self.dispatch_deadline_seconds = max(15, min(dispatch_deadline_seconds, 1800))
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google.cloud import tasks_v2

            self._client = tasks_v2.CloudTasksClient()
        return self._client

    def learn_service_url(self, url: str) -> None:
        if not self.service_url and url:
            self.service_url = url.rstrip("/")
            logger.info("Cloud Tasks target URL derived from request: %s", self.service_url)

    async def _service_account_email(self) -> str:
        if self.service_account:
            return self.service_account
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as http:
            resp = await http.get(METADATA_SA_URL, headers={"Metadata-Flavor": "Google"})
            resp.raise_for_status()
            self.service_account = resp.text.strip()
        return self.service_account

    def build_task(self, job_id: str, seq: int, service_account: str, ui: bool = False) -> dict:
        from google.protobuf import duration_pb2

        if not self.service_url:
            raise RuntimeError("SERVICE_URL is not set and could not be derived")
        parent = self.client.queue_path(self.project, self.location, self.queue)
        task_id = ui_task_id_for(job_id) if ui else task_id_for(job_id, seq)
        path = UI_RUN_PATH if ui else INTERNAL_RUN_PATH
        return {
            "name": f"{parent}/tasks/{task_id}",
            "http_request": {
                "http_method": "POST",
                "url": f"{self.service_url}{path}/{job_id}",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"seq": seq}).encode(),
                "oidc_token": {
                    "service_account_email": service_account,
                    "audience": self.service_url,
                },
            },
            "dispatch_deadline": duration_pb2.Duration(seconds=self.dispatch_deadline_seconds),
        }

    async def enqueue(self, job_id: str, seq: int) -> None:
        await self._create(job_id, seq, ui=False)

    async def enqueue_ui(self, job_id: str) -> None:
        await self._create(job_id, 0, ui=True)

    async def _create(self, job_id: str, seq: int, ui: bool) -> None:
        from google.api_core import exceptions as gexc

        sa = await self._service_account_email()
        task = self.build_task(job_id, seq, sa, ui=ui)
        parent = self.client.queue_path(self.project, self.location, self.queue)
        try:
            await asyncio.to_thread(self.client.create_task, parent=parent, task=task)
            logger.info("Enqueued task %s for job %s", task["name"].rsplit("/", 1)[-1], job_id)
        except gexc.AlreadyExists:
            # Same (job, seq) already enqueued by an earlier attempt: fine.
            logger.info("Task for job %s seq %s already exists", job_id, seq)
