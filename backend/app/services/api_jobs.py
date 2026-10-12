"""
Wiring for the Inframe-facing job API: creates jobs, reads status/results and
builds the runner + dispatcher from settings.
"""

from __future__ import annotations

import asyncio
import logging
import re
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.schemas.api_job import CreateJobRequest
from app.services.api_job_store import (
    FAILED,
    JOB_ID_RE,
    ApiJobStore,
    new_job_doc,
    new_job_id,
    public_status,
    transition,
    utcnow,
)
from app.services.api_pipeline import ApiJobRunner, PipelineSteps
from app.services.gcs_io import GcsIO, ObjectNotReadable, parse_gs_uri
from app.services.task_dispatcher import (
    CloudTasksDispatcher,
    Dispatcher,
    InlineDispatcher,
)

logger = logging.getLogger(__name__)


class InputError(Exception):
    """The request references inputs the service cannot use (HTTP 422)."""


class ScheduleError(Exception):
    """The job could not be queued (HTTP 503)."""


class ApiJobService:
    def __init__(
        self,
        store: ApiJobStore,
        gcs: GcsIO,
        runner: ApiJobRunner,
        dispatcher: Dispatcher,
        allowed_buckets: Optional[set] = None,
    ):
        self.store = store
        self.gcs = gcs
        self.runner = runner
        self.dispatcher = dispatcher
        self.allowed_buckets = allowed_buckets or set()

    async def _check_input(self, field: str, uri: str) -> None:
        bucket = parse_gs_uri(uri).bucket
        if self.allowed_buckets and bucket not in self.allowed_buckets:
            raise InputError(f"{field}: bucket {bucket} is not allowed")
        try:
            info = await asyncio.to_thread(self.gcs.stat, uri)
        except ObjectNotReadable:
            raise InputError(f"{field}: object is not readable by the Chaptermaker service account")
        if info is None:
            raise InputError(f"{field}: object not found")

    async def create_job(self, req: CreateJobRequest) -> str:
        await self._check_input("video_uri", req.video_uri)
        if req.presentation_uri:
            await self._check_input("presentation_uri", req.presentation_uri)

        job_id = new_job_id()
        doc = new_job_doc(
            job_id, req.video_uri, req.presentation_uri, req.title, req.language, utcnow()
        )
        await self.store.create(doc)
        try:
            await self.dispatcher.enqueue(job_id, 0)
        except Exception as e:
            logger.exception("Could not enqueue job %s", job_id)

            def fail(d):
                transition(d, FAILED, utcnow())
                d["error"] = "Could not schedule processing"
                d["message"] = "Failed"

            try:
                await self.store.update(job_id, fail)
            except Exception:
                logger.warning("Could not mark %s failed", job_id, exc_info=True)
            raise ScheduleError(str(e)) from e
        logger.info("Created api job %s", job_id)
        return job_id

    async def get_doc(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Raw record (api or legacy) for status reads; api jobs are reaped if stale."""
        doc = await self.store.get_raw(job_id)
        if doc is not None and doc.get("kind") == "api":
            doc = await self.runner.reap_if_stale(doc)
        return doc

    async def get_result(self, job_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """(status, result). result is None unless the job completed."""
        if not JOB_ID_RE.match(job_id):
            return None, None
        doc = await self.get_doc(job_id)
        if doc is None or doc.get("kind") != "api":
            return None, None
        if doc["status"] != "completed":
            return public_status(doc), None
        return public_status(doc), await self.store.get_result(job_id)


def build_service(cfg=settings) -> ApiJobService:
    gcs = GcsIO(project=cfg.GCP_PROJECT_ID)
    store = ApiJobStore(gcs, cfg.GCS_OUTPUT_BUCKET)
    if cfg.CLOUD_TASKS_QUEUE:
        dispatcher: Dispatcher = CloudTasksDispatcher(
            project=cfg.GCP_PROJECT_ID,
            location=cfg.CLOUD_TASKS_LOCATION,
            queue=cfg.CLOUD_TASKS_QUEUE,
            service_url=cfg.SERVICE_URL,
            service_account=cfg.TASKS_SERVICE_ACCOUNT,
            dispatch_deadline_seconds=cfg.TASK_DISPATCH_DEADLINE_SECONDS,
        )
    else:
        logger.warning("CLOUD_TASKS_QUEUE not set: api jobs run inline in this process")
        dispatcher = InlineDispatcher()
    runner = ApiJobRunner(
        store, gcs, PipelineSteps(gcs, cfg), dispatcher, cfg,
        output_bucket=cfg.GCS_OUTPUT_BUCKET,
    )
    if isinstance(dispatcher, InlineDispatcher):
        dispatcher.run = runner.run
    allowed = {b.strip() for b in re.split(r"[,;\s]+", cfg.ALLOWED_INPUT_BUCKETS) if b.strip()}
    return ApiJobService(store, gcs, runner, dispatcher, allowed)


@lru_cache(maxsize=1)
def get_api_job_service() -> ApiJobService:
    return build_service()
