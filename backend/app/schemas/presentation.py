"""
Presentation-related Pydantic schemas
"""

from pydantic import BaseModel, Field


class PresentationUploadResponse(BaseModel):
    """Response for presentation upload URL request"""
    upload_url: str = Field(..., description="Signed URL for uploading presentation")
    file_path: str = Field(..., description="GCS path where file will be stored")
    expires_in: int = Field(..., description="URL expiry time in seconds")
    content_type: str = Field(..., description="Content type to use for upload")
