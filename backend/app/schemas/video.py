"""
Video-related Pydantic schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ProcessingOptions(BaseModel):
    """Options for video processing"""
    generate_subtitles: bool = Field(default=True, description="Generate SRT subtitles")
    generate_chapters: bool = Field(default=True, description="Generate chapter markers")
    extract_slides: bool = Field(default=True, description="Extract slides from presentation")
    language: str = Field(default="en", description="Language code for transcription")
    custom_prompts: Optional[Dict[str, str]] = Field(default=None, description="Custom prompts for chapter generation")


class VideoUploadResponse(BaseModel):
    """Response for video upload URL request"""
    upload_url: str = Field(..., description="Signed URL for uploading video")
    file_path: str = Field(..., description="GCS path where file will be stored")
    expires_in: int = Field(..., description="URL expiry time in seconds")
    content_type: str = Field(..., description="Content type to use for upload")


class VideoProcessRequest(BaseModel):
    """Request to process a single video"""
    video_path: str = Field(..., description="GCS path to video file")
    presentation_path: str = Field(..., description="GCS path to presentation file")
    options: ProcessingOptions = Field(default_factory=ProcessingOptions)


class BatchProcessItem(BaseModel):
    """Single item in batch processing request"""
    video_path: str = Field(..., description="GCS path to video file")
    presentation_path: str = Field(..., description="GCS path to presentation file")
    options: Optional[ProcessingOptions] = Field(default_factory=ProcessingOptions)


class BatchProcessRequest(BaseModel):
    """Request to process multiple videos"""
    items: List[BatchProcessItem] = Field(..., description="List of videos to process")


class VideoProcessResponse(BaseModel):
    """Response for video processing request"""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status")
    message: str = Field(..., description="Status message")
    created_at: datetime = Field(default_factory=datetime.utcnow)
