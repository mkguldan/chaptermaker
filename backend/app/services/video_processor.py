"""
Main video processing service that orchestrates all operations
"""

import logging
from typing import Dict, Any, Optional
import uuid
import csv
import io
from pathlib import Path
from app.services.transcription import TranscriptionService
from app.services.chapter_generation import ChapterGenerationService
from app.services.presentation import PresentationService
from app.services.storage import StorageService
from app.services.job_manager import JobManager
from app.schemas.job import JobStatusEnum

logger = logging.getLogger(__name__)


class VideoProcessorService:
    """Main service for processing videos and generating outputs"""
    
    def __init__(self):
        self.transcription_service = TranscriptionService()
        self.chapter_service = ChapterGenerationService()
        self.presentation_service = PresentationService()
        self.storage_service = StorageService()
        self.job_manager = JobManager()
        
    async def create_processing_job(
        self,
        video_path: str,
        presentation_path: str,
        options: Dict[str, Any]
    ) -> str:
        """Create a new processing job"""
        # Generate job ID
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        
        # Create job entry
        await self.job_manager.create_job(
            job_id=job_id,
            video_path=video_path,
            presentation_path=presentation_path,
            options=options
        )
        
        return job_id
        
    async def process_video_async(self, job_id: str) -> None:
        """
        Process video asynchronously (called from background task)
        """
        try:
            logger.info(f"Starting processing for job {job_id}")
            
            # Get job details
            job = await self.job_manager.get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return
                
            # Update status to processing
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.PROCESSING,
                progress=0,
                message="Starting video processing"
            )
            
            # Step 1: Extract slides from presentation (but don't create ZIP yet)
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.PROCESSING,
                progress=10,
                message="Extracting presentation slides"
            )
            
            slide_results = await self.presentation_service.extract_slides(
                presentation_path=job.presentation_path,
                job_id=job_id
            )
            
            # Step 2: Transcribe video
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.PROCESSING,
                progress=30,
                message="Transcribing video"
            )
            
            options = job.metadata.get("options", {})
            transcription = await self.transcription_service.transcribe_video(
                video_path=job.video_path,
                language=options.get("language", "en"),
                job_id=job_id
            )
            
            # Step 3: Generate chapters
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.PROCESSING,
                progress=70,
                message="Generating chapters"
            )
            
            chapters = await self.chapter_service.generate_chapters(
                transcription=transcription,
                slide_count=slide_results["slide_count"],
                custom_prompts=options.get("custom_prompts")
            )
            
            # Step 3.5: Check for Q&A and create ZIP with qa.jpg only if Q&A exists
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.PROCESSING,
                progress=85,
                message="Creating slides package"
            )
            
            has_qa = any(chapter.get('image_name') == 'qa' for chapter in chapters)
            logger.info(f"Q&A detection for job {job_id}: {has_qa}")
            
            zip_path = await self.presentation_service.create_slides_zip_from_results(
                slide_results=slide_results,
                job_id=job_id,
                include_qa=has_qa
            )
            slide_results["zip_path"] = zip_path
            
            # Step 4: Generate output files
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.PROCESSING,
                progress=90,
                message="Generating output files"
            )
            
            output_files = await self._generate_outputs(
                job_id=job_id,
                chapters=chapters,
                transcription=transcription,
                slide_results=slide_results
            )
            
            # Calculate statistics
            statistics = {
                "duration_seconds": transcription.get("duration", 0),
                "chapters_count": len(chapters),
                "slides_extracted": slide_results["slide_count"],
                "transcription_length": len(transcription["full_text"]),
                "language": transcription.get("language", "en")
            }
            
            # Save results
            await self.job_manager.save_job_results(
                job_id=job_id,
                output_files=output_files,
                statistics=statistics
            )
            
            # Update job status to completed
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.COMPLETED,
                progress=100,
                message="Processing completed successfully"
            )
            
            logger.info(f"Successfully completed processing for job {job_id}")
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {str(e)}")
            
            # Update job status to failed
            await self.job_manager.update_job(
                job_id,
                JobStatusEnum.FAILED,
                error=str(e),
                message="Processing failed"
            )
            
    async def _generate_outputs(
        self,
        job_id: str,
        chapters: list,
        transcription: Dict[str, Any],
        slide_results: Dict[str, Any]
    ) -> Dict[str, str]:
        """Generate and save output files"""
        output_files = {}
        
        # Generate chapters CSV
        csv_content = self._generate_chapters_csv(chapters)
        csv_path = f"outputs/{job_id}/importChapters.csv"
        await self.storage_service.upload_content(
            content=csv_content,
            gcs_path=csv_path,
            content_type="text/csv"
        )
        output_files["chapters"] = csv_path
        
        # Save SRT subtitles
        if transcription.get("srt_content"):
            srt_path = f"outputs/{job_id}/subtitles.srt"
            await self.storage_service.upload_content(
                content=transcription["srt_content"],
                gcs_path=srt_path,
                content_type="text/plain"
            )
            output_files["subtitles"] = srt_path
            
        # Save full transcript
        transcript_path = f"outputs/{job_id}/transcript.txt"
        await self.storage_service.upload_content(
            content=transcription["full_text"],
            gcs_path=transcript_path,
            content_type="text/plain"
        )
        output_files["transcript"] = transcript_path
        
        # Reference to slides folder
        output_files["slides"] = f"outputs/{job_id}/slides/"
        
        return output_files
        
    def _generate_chapters_csv(self, chapters: list) -> str:
        """Generate CSV content for chapters"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["Time (s)", "Image name", "Description"])
        
        # Write chapters
        for chapter in chapters:
            writer.writerow([
                chapter["time_seconds"],
                chapter["image_name"],
                chapter["description"]
            ])
            
        return output.getvalue()
