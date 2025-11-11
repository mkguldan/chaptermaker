"""
Job tracking and status endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List
import logging
from app.schemas.job import JobStatus, JobListResponse, JobResult
from app.services.job_manager import JobManager
from app.services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    job_manager: JobManager = Depends()
) -> JobStatus:
    """
    Get the status of a specific job
    
    Args:
        job_id: Job identifier
        
    Returns:
        Job status and metadata
    """
    try:
        job = await job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch job status")


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
        
        # Create signed download URLs
        download_urls = {}
        for key, path in result.output_files.items():
            download_urls[key] = await storage_service.generate_download_url(path)
        
        result.download_urls = download_urls
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job results: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch job results")


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
