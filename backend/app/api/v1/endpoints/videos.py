"""
Video processing endpoints
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from typing import Dict, List
import logging
from app.schemas.video import (
    VideoProcessRequest,
    VideoProcessResponse,
    VideoUploadResponse,
    BatchProcessRequest
)
from app.services.storage import StorageService
from app.services.video_processor import VideoProcessorService
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=VideoUploadResponse)
async def get_upload_url(
    filename: str,
    storage_service: StorageService = Depends()
) -> VideoUploadResponse:
    """
    Get a signed URL for direct video or audio upload to GCS
    
    Args:
        filename: Name of the video or audio file
        
    Returns:
        Signed upload URL and file metadata
    """
    try:
        logger.info(f"Upload URL request received for: {filename}")
        
        # Validate file extension (video or audio)
        is_video = any(filename.lower().endswith(ext) for ext in settings.ALLOWED_VIDEO_EXTENSIONS)
        is_audio = any(filename.lower().endswith(ext) for ext in settings.ALLOWED_AUDIO_EXTENSIONS)
        
        if not is_video and not is_audio:
            logger.warning(f"Invalid file type for: {filename}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed video: {settings.ALLOWED_VIDEO_EXTENSIONS}, audio: {settings.ALLOWED_AUDIO_EXTENSIONS}"
            )
        
        # Determine exact content type based on extension
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            # Fallback to generic types
            content_type = "audio/mpeg" if is_audio else "video/mp4"
        logger.info(f"File type: {'audio' if is_audio else 'video'}, content_type: {content_type}")
        
        # Generate signed URL
        upload_url, file_path = await storage_service.generate_upload_url(
            filename=filename,
            content_type=content_type
        )
        
        return VideoUploadResponse(
            upload_url=upload_url,
            file_path=file_path,
            expires_in=settings.SIGNED_URL_EXPIRY_SECONDS,
            content_type=content_type
        )
        
    except Exception as e:
        logger.error(f"Error generating upload URL: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")


@router.post("/process", response_model=VideoProcessResponse)
async def process_video(
    request: VideoProcessRequest,
    background_tasks: BackgroundTasks,
    video_processor: VideoProcessorService = Depends()
) -> VideoProcessResponse:
    """
    Process a single video with its presentation
    
    Args:
        request: Video processing request with video and presentation paths
        
    Returns:
        Job ID and status
    """
    try:
        # Create processing job
        job_id = await video_processor.create_processing_job(
            video_path=request.video_path,
            presentation_path=request.presentation_path,
            options=request.options
        )
        
        # Add to background tasks
        background_tasks.add_task(
            video_processor.process_video_async,
            job_id=job_id
        )
        
        return VideoProcessResponse(
            job_id=job_id,
            status="processing",
            message="Video processing started"
        )
        
    except Exception as e:
        logger.error(f"Error starting video processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start video processing")


@router.post("/batch", response_model=List[VideoProcessResponse])
async def batch_process_videos(
    request: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    video_processor: VideoProcessorService = Depends()
) -> List[VideoProcessResponse]:
    """
    Process multiple videos in batch
    
    Args:
        request: Batch processing request with multiple video/presentation pairs
        
    Returns:
        List of job IDs and statuses
    """
    try:
        responses = []
        
        # Validate batch size
        if len(request.items) > settings.BATCH_PROCESSING_MAX_CONCURRENT:
            raise HTTPException(
                status_code=400,
                detail=f"Batch size exceeds limit of {settings.BATCH_PROCESSING_MAX_CONCURRENT}"
            )
        
        # Create jobs for each video
        for item in request.items:
            job_id = await video_processor.create_processing_job(
                video_path=item.video_path,
                presentation_path=item.presentation_path,
                options=item.options
            )
            
            # Add to background tasks
            background_tasks.add_task(
                video_processor.process_video_async,
                job_id=job_id
            )
            
            responses.append(VideoProcessResponse(
                job_id=job_id,
                status="processing",
                message=f"Processing started for {item.video_path}"
            ))
        
        return responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start batch processing")
