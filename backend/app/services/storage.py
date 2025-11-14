"""
Google Cloud Storage service for file operations
"""

import logging
import os
from typing import Tuple, Optional, BinaryIO
from google.cloud import storage
from google.cloud.storage import Blob
import google.auth
from google.auth.transport import requests as google_requests
from datetime import datetime, timedelta
import asyncio
import aiofiles
from pathlib import Path
import tempfile
import uuid
from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Service for Google Cloud Storage operations"""
    
    def __init__(self):
        self.client = storage.Client(project=settings.GCP_PROJECT_ID)
        self.upload_bucket = self.client.bucket(settings.GCS_UPLOAD_BUCKET)
        self.output_bucket = self.client.bucket(settings.GCS_OUTPUT_BUCKET)
        self._credentials = None
        
    async def _get_credentials_and_token(self):
        """Get credentials and ensure fresh access token"""
        if self._credentials is None:
            credentials, project = await asyncio.to_thread(google.auth.default)
            self._credentials = credentials
            logger.info(f"Initialized credentials type: {type(self._credentials).__name__}")
            
        # Ensure credentials have a fresh token
        request = google_requests.Request()
        await asyncio.to_thread(self._credentials.refresh, request)
        
        # Get service account email
        if hasattr(self._credentials, 'service_account_email'):
            service_account_email = self._credentials.service_account_email
            logger.info(f"Using service account email from credentials: {service_account_email}")
        else:
            # For compute engine credentials, get from metadata
            service_account_email = f"{settings.GCP_PROJECT_ID}@appspot.gserviceaccount.com"
            logger.warning(f"Service account email not in credentials, using computed: {service_account_email}")
            
        # Log token info (safely)
        token = self._credentials.token
        if token:
            logger.info(f"Access token available: {token[:20]}...{token[-20:] if len(token) > 40 else ''}")
        else:
            logger.error("No access token available!")
            
        return token, service_account_email
        
    async def generate_upload_url(
        self,
        filename: str,
        content_type: str
    ) -> Tuple[str, str]:
        """
        Generate a signed URL for direct file upload using access token
        
        Args:
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            Tuple of (signed_url, file_path)
        """
        try:
            # Generate unique file path
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            file_path = f"uploads/{timestamp}/{unique_id}/{filename}"
            
            logger.info(f"Generating upload URL for: {filename}")
            logger.info(f"Bucket: {self.upload_bucket.name}")
            logger.info(f"File path: {file_path}")
            logger.info(f"Content type: {content_type}")
            
            # Create blob reference
            blob = self.upload_bucket.blob(file_path)
            
            # Get access token and service account email
            access_token, service_account_email = await self._get_credentials_and_token()
            
            logger.info(f"Calling generate_signed_url with:")
            logger.info(f"  - version: v4")
            logger.info(f"  - expiration: {settings.SIGNED_URL_EXPIRY_SECONDS}s")
            logger.info(f"  - method: PUT")
            logger.info(f"  - content_type: {content_type}")
            logger.info(f"  - service_account_email: {service_account_email}")
            logger.info(f"  - access_token: {'present' if access_token else 'missing'}")
                
            # Generate signed URL using access token (Cloud Run compatible)
            url = await asyncio.to_thread(
                blob.generate_signed_url,
                version="v4",
                expiration=timedelta(seconds=settings.SIGNED_URL_EXPIRY_SECONDS),
                method="PUT",
                content_type=content_type,
                service_account_email=service_account_email,
                access_token=access_token
            )
            
            logger.info(f"Successfully generated upload URL for {filename}")
            logger.info(f"URL starts with: {url[:100]}...")
            return url, file_path
            
        except Exception as e:
            logger.error(f"Error generating upload URL: {str(e)}", exc_info=True)
            raise
            
    async def generate_download_url(
        self,
        file_path: str,
        expiration_seconds: int = 3600
    ) -> str:
        """
        Generate a signed URL for file download using access token
        
        Args:
            file_path: GCS path to file
            expiration_seconds: URL expiration time
            
        Returns:
            Signed download URL
        """
        try:
            # Determine which bucket based on path
            if file_path.startswith("outputs/") or file_path.startswith("job-tracking/"):
                bucket = self.output_bucket
            else:
                bucket = self.upload_bucket
                
            blob = bucket.blob(file_path)
            
            # Get access token and service account email
            access_token, service_account_email = await self._get_credentials_and_token()
            
            # Generate signed URL for download
            url = await asyncio.to_thread(
                blob.generate_signed_url,
                version="v4",
                expiration=timedelta(seconds=expiration_seconds),
                method="GET",
                service_account_email=service_account_email,
                access_token=access_token
            )
            
            return url
            
        except Exception as e:
            logger.error(f"Error generating download URL: {str(e)}")
            raise
            
    async def download_to_temp(self, gcs_path: str) -> str:
        """
        Download file from GCS to temporary location
        
        Args:
            gcs_path: GCS path to file
            
        Returns:
            Path to temporary file
        """
        try:
            # Determine bucket
            if gcs_path.startswith("outputs/") or gcs_path.startswith("job-tracking/"):
                bucket = self.output_bucket
            else:
                bucket = self.upload_bucket
                
            # Always get a fresh blob reference to avoid generation mismatch issues
            blob = bucket.get_blob(gcs_path)
            if not blob:
                raise Exception(f"Blob not found: {gcs_path}")
            
            # Check file size
            file_size_mb = blob.size / (1024 * 1024) if blob.size else 0
            logger.info(f"Downloading {gcs_path} ({file_size_mb:.2f} MB)...")
            
            # Create temporary file
            suffix = Path(gcs_path).suffix
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_path = temp_file.name
            temp_file.close()
            
            # Download file with timeout (2 minutes per MB, min 1 minute, max 10 minutes)
            timeout_seconds = min(max(int(file_size_mb * 120), 60), 600)
            logger.info(f"Download timeout set to {timeout_seconds} seconds")
            
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(blob.download_to_filename, temp_path),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(f"Download timed out after {timeout_seconds} seconds")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise Exception(f"Download of {gcs_path} timed out after {timeout_seconds} seconds")
            
            logger.info(f"Downloaded {gcs_path} to {temp_path} ({file_size_mb:.2f} MB)")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            raise
            
    async def upload_file(
        self,
        local_path: str,
        gcs_path: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload file from local path to GCS
        
        Args:
            local_path: Local file path
            gcs_path: Destination GCS path
            content_type: Optional MIME type
            
        Returns:
            GCS path
        """
        try:
            # Use output bucket for results
            blob = self.output_bucket.blob(gcs_path)
            
            # Upload file
            await asyncio.to_thread(
                blob.upload_from_filename,
                local_path,
                content_type=content_type
            )
            
            logger.info(f"Uploaded {local_path} to {gcs_path}")
            return gcs_path
            
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise
            
    async def upload_content(
        self,
        content: str,
        gcs_path: str,
        content_type: str = "text/plain"
    ) -> str:
        """
        Upload text content directly to GCS
        
        Args:
            content: Text content to upload
            gcs_path: Destination GCS path
            content_type: MIME type
            
        Returns:
            GCS path
        """
        try:
            blob = self.output_bucket.blob(gcs_path)
            
            # Upload content
            await asyncio.to_thread(
                blob.upload_from_string,
                content,
                content_type=content_type
            )
            
            logger.info(f"Uploaded content to {gcs_path}")
            return gcs_path
            
        except Exception as e:
            logger.error(f"Error uploading content: {str(e)}")
            raise
            
    async def copy_file(
        self,
        source_path: str,
        dest_path: str
    ) -> str:
        """
        Copy file within GCS
        
        Args:
            source_path: Source GCS path
            dest_path: Destination GCS path
            
        Returns:
            Destination path
        """
        try:
            # Determine source bucket
            if source_path.startswith("outputs/"):
                source_bucket = self.output_bucket
            else:
                source_bucket = self.upload_bucket
                
            source_blob = source_bucket.blob(source_path)
            dest_blob = self.output_bucket.blob(dest_path)
            
            # Copy blob
            await asyncio.to_thread(source_bucket.copy_blob, source_blob, self.output_bucket, dest_blob)
            
            logger.info(f"Copied {source_path} to {dest_path}")
            return dest_path
            
        except Exception as e:
            logger.error(f"Error copying file: {str(e)}")
            raise
            
    async def check_health(self) -> bool:
        """Check GCS connectivity"""
        try:
            # Try to list buckets as a health check
            await asyncio.to_thread(list, self.client.list_buckets(max_results=1))
            return True
        except Exception as e:
            logger.error(f"GCS health check failed: {str(e)}")
            return False
