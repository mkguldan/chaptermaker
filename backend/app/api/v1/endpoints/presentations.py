"""
Presentation upload and processing endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
import logging
from app.schemas.presentation import PresentationUploadResponse
from app.services.storage import StorageService
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=PresentationUploadResponse)
async def get_presentation_upload_url(
    filename: str,
    storage_service: StorageService = Depends()
) -> PresentationUploadResponse:
    """
    Get a signed URL for direct presentation upload to GCS
    
    Args:
        filename: Name of the presentation file
        
    Returns:
        Signed upload URL and file metadata
    """
    try:
        # Validate file extension
        if not any(filename.lower().endswith(ext) for ext in settings.ALLOWED_PRESENTATION_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {settings.ALLOWED_PRESENTATION_EXTENSIONS}"
            )
        
        # Determine exact content type based on extension
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            # Fallback to generic types
            content_type = "application/pdf" if filename.lower().endswith(".pdf") else "application/vnd.ms-powerpoint"
        
        # Generate signed URL
        upload_url, file_path = await storage_service.generate_upload_url(
            filename=filename,
            content_type=content_type
        )
        
        return PresentationUploadResponse(
            upload_url=upload_url,
            file_path=file_path,
            expires_in=settings.SIGNED_URL_EXPIRY_SECONDS,
            content_type=content_type
        )
        
    except Exception as e:
        logger.error(f"Error generating presentation upload URL: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")
