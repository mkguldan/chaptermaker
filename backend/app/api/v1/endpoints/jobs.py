"""
Job tracking and status endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List
import logging
import re
from app.schemas.job import JobStatus, JobListResponse, JobResult
from app.schemas.api_job import (
    ApiJobResult,
    ApiJobStatus,
    CreateJobRequest,
    CreateJobResponse,
)
from app.services.api_job_store import public_status
from app.services.api_jobs import (
    ApiJobService,
    InputError,
    ScheduleError,
    get_api_job_service,
)
from app.services.job_manager import JobManager
from app.services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter()

_JOB_ID_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def derive_base_url(request: Request) -> str:
    """Public base URL of this service as seen by the caller (Cloud Run host)."""
    host = request.headers.get("host", "")
    if not host:
        return ""
    if host.startswith(("localhost", "127.0.0.1", "0.0.0.0", "[::1]")):
        return f"{request.url.scheme}://{host}"
    return f"https://{host}"


@router.post("", status_code=202, response_model=CreateJobResponse)
async def create_job(
    body: CreateJobRequest,
    request: Request,
    service: ApiJobService = Depends(get_api_job_service),
) -> CreateJobResponse:
    """
    Queue a chaptering job for a video in GCS (used by Inframe).

    The objects are read with the service account; no signed URLs are needed.
    Poll GET /api/v1/jobs/{job_id}, then fetch GET /api/v1/jobs/{job_id}/result.
    """
    service.dispatcher.learn_service_url(derive_base_url(request))
    try:
        job_id = await service.create_job(body)
    except InputError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ScheduleError:
        raise HTTPException(status_code=503, detail="Could not schedule the job; try again")
    return CreateJobResponse(job_id=job_id)


@router.get(
    "/{job_id}",
    # Two shapes (api jobs vs legacy UI jobs), so no response_model filtering.
    response_model=None,
    responses={200: {"model": ApiJobStatus, "description": "Status of an api job"}},
)
async def get_job_status(
    job_id: str,
    service: ApiJobService = Depends(get_api_job_service),
):
    """
    Get the status of a job.

    Jobs created with POST /api/v1/jobs return
    {job_id, status: queued|processing|completed|failed, progress, message,
    error, created_at, updated_at}. Jobs from the web UI keep their original
    shape.
    """
    if not _JOB_ID_SAFE.match(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        doc = await service.get_doc(job_id)
    except Exception as e:
        logger.error(f"Error fetching job status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch job status")
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if doc.get("kind") == "api":
        return ApiJobStatus(**public_status(doc))
    try:
        return JobStatus(**doc)
    except Exception as e:
        logger.error(f"Unreadable job record {job_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/{job_id}/result", response_model=ApiJobResult)
async def get_api_job_result(
    job_id: str,
    service: ApiJobService = Depends(get_api_job_service),
) -> ApiJobResult:
    """
    Result of a completed job created with POST /api/v1/jobs. All URIs point
    into Chaptermaker's output bucket; copy what you need.

    404 if the job does not exist, 409 if it has not completed.
    """
    try:
        status, result = await service.get_result(job_id)
    except Exception as e:
        logger.error(f"Error fetching job result: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch job result")
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if status["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed. Current status: {status['status']}",
        )
    if result is None:
        raise HTTPException(status_code=500, detail="Job result is missing")
    return ApiJobResult(**result)


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    status: str = None,
    limit: int = 10,
    offset: int = 0,
    job_manager: JobManager = Depends()
) -> JobListResponse:
    """
    List jobs with optional filtering
    
    Args:
        status: Optional status filter
        limit: Number of jobs to return
        offset: Pagination offset
        
    Returns:
        List of jobs and pagination metadata
    """
    try:
        jobs, total = await job_manager.list_jobs(
            status=status,
            limit=limit,
            offset=offset
        )
        
        return JobListResponse(
            jobs=jobs,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list jobs")


@router.get("/{job_id}/results", response_model=JobResult)
async def get_job_results(
    job_id: str,
    job_manager: JobManager = Depends(),
    storage_service: StorageService = Depends()
) -> JobResult:
    """
    Get the results of a completed job
    
    Args:
        job_id: Job identifier
        
    Returns:
        Job results with download URLs
    """
    try:
        job = await job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Job is not completed. Current status: {job.status}"
            )
        
        # Generate download URLs for results
        result = await job_manager.get_job_results(job_id)
        
        # Extract original filenames from paths
        from pathlib import Path
        original_filenames = {}
        if job.presentation_path:
            pres_name = Path(job.presentation_path).stem  # Get filename without extension
            original_filenames['presentation_name'] = pres_name
        
        result.original_filenames = original_filenames
        
        # Create signed download URLs with custom filenames
        download_urls = {}
        for key, path in result.output_files.items():
            custom_filename = None
            
            # Use original presentation name for transcript and subtitles
            if key == 'transcript' and original_filenames.get('presentation_name'):
                custom_filename = f"{original_filenames['presentation_name']}.txt"
            elif key == 'subtitles' and original_filenames.get('presentation_name'):
                custom_filename = f"{original_filenames['presentation_name']}.srt"
            
            download_urls[key] = await storage_service.generate_download_url(
                path,
                custom_filename=custom_filename
            )
        
        result.download_urls = download_urls
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job results: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch job results")


@router.get("/{job_id}/download-all")
async def download_all_outputs(
    job_id: str,
    job_manager: JobManager = Depends(),
    storage_service: StorageService = Depends()
):
    """
    Download all output files as a single ZIP
    
    Args:
        job_id: Job identifier
        
    Returns:
        Redirect to signed download URL for the ZIP file
    """
    try:
        from fastapi.responses import RedirectResponse
        
        job = await job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Job is not completed. Current status: {job.status}"
            )
        
        # Get job results
        result = await job_manager.get_job_results(job_id)
        
        # Create ZIP of all outputs
        logger.info(f"Creating all-outputs ZIP for job {job_id}")
        zip_path = await storage_service.create_all_outputs_zip(
            output_files=result.output_files,
            job_id=job_id
        )
        
        # Generate download URL for the ZIP
        from pathlib import Path
        custom_filename = None
        if job.presentation_path:
            pres_name = Path(job.presentation_path).stem
            custom_filename = f"{pres_name}_all_outputs.zip"
        
        download_url = await storage_service.generate_download_url(
            zip_path,
            custom_filename=custom_filename
        )
        
        # Redirect to the signed URL
        return RedirectResponse(url=download_url, status_code=302)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating download-all ZIP: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create download ZIP")


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    job_manager: JobManager = Depends()
) -> dict:
    """
    Cancel a running job
    
    Args:
        job_id: Job identifier
        
    Returns:
        Cancellation status
    """
    try:
        success = await job_manager.cancel_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found or already completed")
        
        return {"message": f"Job {job_id} cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to cancel job")
