"""
Internal endpoints called by Cloud Tasks (not part of the public API).

POST /internal/run/{job_id} runs (or resumes) one api job inside the request
so Cloud Run keeps CPU allocated. Status codes drive Cloud Tasks retries:
2xx = done with this task (completed, failed for good, handed off, or a
duplicate), 5xx = retry later.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.api_job_store import JOB_ID_RE
from app.services.api_jobs import ApiJobService, get_api_job_service

logger = logging.getLogger(__name__)
router = APIRouter()


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
    # Cloud Run IAM already restricts who can call the service. When tasks
    # are enabled, additionally require the header Cloud Tasks sets so a
    # stray call from another invoker is rejected.
    if settings.CLOUD_TASKS_QUEUE:
        queue = request.headers.get("x-cloudtasks-queuename")
        if queue != settings.CLOUD_TASKS_QUEUE:
            raise HTTPException(status_code=403, detail="Only Cloud Tasks may call this endpoint")
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
