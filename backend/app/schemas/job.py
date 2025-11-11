"""
Job-related Pydantic schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class JobStatusEnum(str, Enum):
    """Job status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(BaseModel):
    """Job status information"""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatusEnum = Field(..., description="Current job status")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    message: str = Field(default="", description="Status message")
    video_path: str = Field(..., description="Input video path")
    presentation_path: str = Field(..., description="Input presentation path")
    created_at: datetime = Field(..., description="Job creation time")
    updated_at: datetime = Field(..., description="Last update time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class JobListResponse(BaseModel):
    """Response for job listing"""
    jobs: List[JobStatus] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total number of jobs")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Page offset")


class JobResult(BaseModel):
    """Completed job results"""
    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Final status")
    output_files: Dict[str, str] = Field(..., description="Output file paths")
    download_urls: Optional[Dict[str, str]] = Field(None, description="Signed download URLs")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="Processing statistics")
    
    class Config:
        schema_extra = {
            "example": {
                "job_id": "job_12345",
                "status": "completed",
                "output_files": {
                    "chapters": "outputs/job_12345/importChapters.csv",
                    "subtitles": "outputs/job_12345/subtitles.srt",
                    "slides": "outputs/job_12345/slides/"
                },
                "statistics": {
                    "duration_seconds": 1800,
                    "chapters_count": 15,
                    "slides_extracted": 14,
                    "processing_time_seconds": 120
                }
            }
        }
