"""
Presentation processing service for extracting slides
"""

import logging
from typing import List, Dict, Any, Tuple
from pathlib import Path
import asyncio
from PIL import Image
from pptx import Presentation
from pdf2image import convert_from_path
import tempfile
import shutil
from app.core.config import settings
from app.services.storage import StorageService
from app.services.presentation_converter import PresentationConverter

logger = logging.getLogger(__name__)


class PresentationService:
    """Service for processing presentations and extracting slides"""
    
    def __init__(self):
        self.storage_service = StorageService()
        self.converter = PresentationConverter()
        
    async def extract_slides(
        self,
        presentation_path: str,
        job_id: str,
        output_format: str = "jpg"
    ) -> Dict[str, Any]:
        """
        Extract slides from presentation file
        
        Args:
            presentation_path: GCS path to presentation
            job_id: Job ID for organizing outputs
            output_format: Image format for slides (jpg/png)
            
        Returns:
            Dictionary with slide information and paths
        """
        try:
            logger.info(f"Extracting slides from {presentation_path}")
            
            # Download presentation to temporary location
            local_path = await self.storage_service.download_to_temp(presentation_path)
            
            try:
                # Determine file type and extract slides
                file_ext = Path(local_path).suffix.lower()
                
                if file_ext in ['.pptx', '.ppt']:
                    slides = await self._extract_powerpoint_slides(local_path, output_format)
                elif file_ext == '.pdf':
                    slides = await self._extract_pdf_slides(local_path, output_format)
                else:
                    raise ValueError(f"Unsupported presentation format: {file_ext}")
                
                # Upload slides to GCS
                uploaded_slides = await self._upload_slides(slides, job_id)
                
                # Copy Q&A image to output
                qa_path = await self._copy_qa_image(job_id)
                
                return {
                    "slide_count": len(slides),
                    "slides": uploaded_slides,
                    "qa_image": qa_path,
                    "format": output_format
                }
                
            finally:
                # Clean up temporary files
                if Path(local_path).exists():
                    Path(local_path).unlink()
                # Clean up extracted slide files
                for slide_info in slides:
                    if Path(slide_info['local_path']).exists():
                        Path(slide_info['local_path']).unlink()
                        
        except Exception as e:
            logger.error(f"Error extracting slides: {str(e)}")
            raise
            
    async def _extract_powerpoint_slides(
        self,
        pptx_path: str,
        output_format: str
    ) -> List[Dict[str, Any]]:
        """Extract slides from PowerPoint presentation"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Use the converter to extract slides
            slides = await self.converter.convert_pptx_to_images(
                pptx_path=pptx_path,
                output_dir=temp_dir,
                output_format=output_format
            )
            
            logger.info(f"Extracted {len(slides)} slides from PowerPoint")
            return slides
            
        except Exception as e:
            logger.error(f"Error in PowerPoint extraction: {str(e)}")
            # Clean up temp directory on error
            if Path(temp_dir).exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
                
    async def _extract_pdf_slides(
        self,
        pdf_path: str,
        output_format: str
    ) -> List[Dict[str, Any]]:
        """Extract slides from PDF presentation"""
        slides = []
        
        try:
            # Convert PDF pages to images
            images = await asyncio.to_thread(
                convert_from_path,
                pdf_path,
                dpi=300,
                fmt=output_format
            )
            
            # Save each page as an image
            for idx, image in enumerate(images, 1):
                # Create temporary file for slide
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=f".{output_format}"
                )
                slide_path = temp_file.name
                temp_file.close()
                
                # Save image
                image.save(slide_path, output_format.upper(), quality=95)
                
                slides.append({
                    "number": idx,
                    "local_path": slide_path,
                    "filename": f"{idx:02d}.{output_format}"
                })
                
            logger.info(f"Extracted {len(slides)} slides from PDF")
            return slides
            
        except Exception as e:
            logger.error(f"Error extracting PDF slides: {str(e)}")
            raise
            
        
    async def _upload_slides(
        self,
        slides: List[Dict[str, Any]],
        job_id: str
    ) -> List[Dict[str, Any]]:
        """Upload extracted slides to GCS"""
        uploaded = []
        
        for slide in slides:
            # Define GCS path
            gcs_path = f"outputs/{job_id}/slides/{slide['filename']}"
            
            # Upload slide
            await self.storage_service.upload_file(
                local_path=slide['local_path'],
                gcs_path=gcs_path,
                content_type=f"image/{Path(slide['local_path']).suffix[1:]}"
            )
            
            uploaded.append({
                "number": slide['number'],
                "filename": slide['filename'],
                "gcs_path": gcs_path
            })
            
        return uploaded
        
    async def _copy_qa_image(self, job_id: str) -> str:
        """Copy Q&A image to job output directory"""
        try:
            # Source Q&A image should be in the project root
            # For now, we'll assume it's uploaded to GCS during setup
            source_path = "static/qa.jpg"
            dest_path = f"outputs/{job_id}/slides/qa.jpg"
            
            # Copy the Q&A image
            await self.storage_service.copy_file(source_path, dest_path)
            
            return dest_path
            
        except Exception as e:
            logger.warning(f"Could not copy Q&A image: {str(e)}")
            # Return a placeholder path - the image can be added manually
            return f"outputs/{job_id}/slides/qa.jpg"
