"""
Internal endpoints called by Cloud Tasks (not part of the public API).

POST /internal/run/{job_id} runs (or resumes) one api job inside the request
so Cloud Run keeps CPU allocated. POST /internal/run-ui/{job_id} does the same
for a job started from the web UI. Status codes drive Cloud Tasks retries:
2xx = done with this task (completed, failed for good, handed off, or a
duplicate), 5xx = retry later.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.job import JobStatusEnum
from app.services.api_job_store import JOB_ID_RE
from app.services.api_jobs import ApiJobService, get_api_job_service

logger = logging.getLogger(__name__)
router = APIRouter()


UI_JOB_ID_RE = re.compile(r"^job_[0-9a-f]{12}$")


def _require_queue(request: Request) -> None:
    # Cloud Run IAM already restricts who can call the service. When tasks
    # are enabled, additionally require the header Cloud Tasks sets so a
    # stray call from another invoker is rejected.
    if settings.CLOUD_TASKS_QUEUE:
        queue = request.headers.get("x-cloudtasks-queuename")
        if queue != settings.CLOUD_TASKS_QUEUE:
            raise HTTPException(status_code=403, detail="Only Cloud Tasks may call this endpoint")


def get_video_processor():
    from app.services.video_processor import VideoProcessorService

    return VideoProcessorService()


class RunTaskBody(BaseModel):
    seq: int = Field(default=0, ge=0)


def _base_url(request: Request) -> str:
    from app.api.v1.endpoints.jobs import derive_base_url

    return derive_base_url(request)


@router.post("/run/{job_id}", include_in_schema=False)
async def run_job_task(
    job_id: str,
    request: Request,
    body: RunTaskBody = RunTaskBody(),
    service: ApiJobService = Depends(get_api_job_service),
):
    _require_queue(request)
    if not JOB_ID_RE.match(job_id):
        return JSONResponse({"action": "noop", "detail": "unknown job"}, status_code=200)

    service.dispatcher.learn_service_url(_base_url(request))
    retry_count = request.headers.get("x-cloudtasks-taskretrycount", "0")
    logger.info("Running job %s seq %s (queue retry count %s)", job_id, body.seq, retry_count)
    outcome = await service.runner.run(job_id, body.seq)
    logger.info("Job %s seq %s -> %s %s", job_id, body.seq, outcome.action, outcome.detail[:200])
    return JSONResponse(
        {"job_id": job_id, "action": outcome.action, "detail": outcome.detail[:500]},
        status_code=outcome.http_status,
    )


@router.post("/run-ui/{job_id}", include_in_schema=False)
async def run_ui_job_task(
    job_id: str,
    request: Request,
    processor=Depends(get_video_processor),
):
    """
    Runs a web UI job inside the request. The UI pipeline has no checkpoints,
    so it runs once: process_video_async records its own failures, and a
    redelivery (the instance died, or the run outlived the 30-minute task
    deadline) marks the job failed instead of starting a second run.
    """
    _require_queue(request)
    if not UI_JOB_ID_RE.match(job_id):
        return JSONResponse({"action": "noop", "detail": "unknown job"}, status_code=200)
    job = await processor.job_manager.get_job(job_id)
    if job is None:
        return JSONResponse({"action": "noop", "detail": "unknown job"}, status_code=200)
    if job.status == JobStatusEnum.PENDING:
        logger.info("Running UI job %s", job_id)
        await processor.process_video_async(job_id=job_id)
        return JSONResponse({"job_id": job_id, "action": "ran"}, status_code=200)
    if job.status == JobStatusEnum.PROCESSING:
        logger.warning("UI job %s was redelivered while processing; marking it failed", job_id)
        await processor.job_manager.update_job(
            job_id,
            JobStatusEnum.FAILED,
            error="Processing was interrupted. Start the job again.",
            message="Processing failed",
        )
        return JSONResponse({"job_id": job_id, "action": "failed"}, status_code=200)
    return JSONResponse({"job_id": job_id, "action": "noop", "detail": job.status.value}, status_code=200)
