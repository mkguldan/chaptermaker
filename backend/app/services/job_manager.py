"""
Job management service for tracking processing status
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
import json
import asyncio
from app.schemas.job import JobStatus, JobStatusEnum, JobResult
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


class JobManager:
    """Service for managing job state and tracking"""
    
    def __init__(self):
        self.storage_service = StorageService()
        # In production, use a database or Redis for job tracking
        # For now, we'll use GCS for simplicity
        self._jobs_bucket = "job-tracking"
        
    async def create_job(
        self,
        job_id: str,
        video_path: str,
        presentation_path: str,
        options: Dict[str, Any]
    ) -> JobStatus:
        """Create a new job entry"""
        job = JobStatus(
            job_id=job_id,
            status=JobStatusEnum.PENDING,
            video_path=video_path,
            presentation_path=presentation_path,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata={"options": options}
        )
        
        # Save job to storage
        await self._save_job(job)
        
        logger.info(f"Created job {job_id}")
        return job
        
    async def get_job(self, job_id: str) -> Optional[JobStatus]:
        """Get job by ID"""
        try:
            job_path = f"{self._jobs_bucket}/{job_id}.json"
            
            # Download job data
            temp_path = await self.storage_service.download_to_temp(job_path)
            
            with open(temp_path, 'r') as f:
                job_data = json.load(f)
                
            # Convert to JobStatus object
            job = JobStatus(**job_data)
            
            return job
            
        except Exception as e:
            logger.error(f"Error fetching job {job_id}: {str(e)}")
            return None
            
    async def update_job(
        self,
        job_id: str,
        status: JobStatusEnum,
        progress: int = None,
        message: str = None,
        error: str = None
    ) -> bool:
        """Update job status"""
        try:
            job = await self.get_job(job_id)
            if not job:
                return False
                
            # Update fields
            job.status = status
            job.updated_at = datetime.utcnow()
            
            if progress is not None:
                job.progress = progress
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            if status == JobStatusEnum.COMPLETED:
                job.completed_at = datetime.utcnow()
                
            # Save updated job
            await self._save_job(job)
            
            logger.info(f"Updated job {job_id} - status: {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {str(e)}")
            return False
            
    async def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> Tuple[List[JobStatus], int]:
        """List jobs with optional filtering"""
        # In production, this would query a database
        # For now, we'll return a placeholder response
        jobs = []
        total = 0
        
        logger.warning("Job listing not fully implemented - using placeholder")
        
        return jobs, total
        
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        try:
            job = await self.get_job(job_id)
            if not job:
                return False
                
            if job.status in [JobStatusEnum.COMPLETED, JobStatusEnum.FAILED]:
                return False
                
            # Update status to cancelled
            await self.update_job(
                job_id,
                JobStatusEnum.CANCELLED,
                message="Job cancelled by user"
            )
            
            # In production, also signal the worker to stop processing
            
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling job {job_id}: {str(e)}")
            return False
            
    async def save_job_results(
        self,
        job_id: str,
        output_files: Dict[str, str],
        statistics: Dict[str, Any]
    ) -> bool:
        """Save job results"""
        try:
            result = JobResult(
                job_id=job_id,
                status="completed",
                output_files=output_files,
                statistics=statistics
            )
            
            # Save result to storage
            result_path = f"{self._jobs_bucket}/{job_id}_result.json"
            content = result.json()
            
            await self.storage_service.upload_content(
                content=content,
                gcs_path=result_path,
                content_type="application/json"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving job results: {str(e)}")
            return False
            
    async def get_job_results(self, job_id: str) -> Optional[JobResult]:
        """Get job results"""
        try:
            result_path = f"{self._jobs_bucket}/{job_id}_result.json"
            
            # Download result data
            temp_path = await self.storage_service.download_to_temp(result_path)
            
            with open(temp_path, 'r') as f:
                result_data = json.load(f)
                
            # Convert to JobResult object
            result = JobResult(**result_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching job results: {str(e)}")
            return None
            
    async def _save_job(self, job: JobStatus) -> None:
        """Save job to storage"""
        job_path = f"{self._jobs_bucket}/{job.job_id}.json"
        
        # Convert datetime fields to ISO format for JSON serialization
        job_dict = job.dict()
        for field in ['created_at', 'updated_at', 'completed_at']:
            if job_dict.get(field):
                job_dict[field] = job_dict[field].isoformat()
                
        content = json.dumps(job_dict, indent=2)
        
        await self.storage_service.upload_content(
            content=content,
            gcs_path=job_path,
            content_type="application/json"
        )
