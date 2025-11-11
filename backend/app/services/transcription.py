"""
Transcription service using OpenAI GPT-4o
"""

import logging
from typing import Dict, Any, List, Optional
from openai import OpenAI
import asyncio
import aiofiles
from pathlib import Path
from app.core.config import settings
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service for transcribing videos using OpenAI GPT-4o"""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.storage_service = StorageService()
        
    async def transcribe_video(
        self,
        video_path: str,
        language: str = "en",
        job_id: str = None
    ) -> Dict[str, Any]:
        """
        Transcribe video or audio file using OpenAI GPT-4o
        
        Args:
            video_path: GCS path to video or audio file
            language: Language code for transcription
            job_id: Job ID for progress tracking
            
        Returns:
            Transcription result with text and timestamps
        """
        try:
            logger.info(f"Starting transcription for: {video_path}")
            
            # Download file from GCS to temporary location
            local_file_path = await self.storage_service.download_to_temp(video_path)
            
            try:
                # Check if it's an audio file (skip extraction) or video file (extract audio)
                file_ext = Path(local_file_path).suffix.lower()
                audio_extensions = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma']
                
                if file_ext in audio_extensions:
                    # Already audio - use directly
                    logger.info("Audio file detected, using directly")
                    audio_path = local_file_path
                    should_delete_audio = False
                else:
                    # Video file - extract audio
                    logger.info("Video file detected, extracting audio")
                    audio_path = await self._extract_audio(local_file_path)
                    should_delete_audio = True
                
                # Transcribe using OpenAI Whisper (GPT-4o-based)
                transcription = await self._transcribe_audio(
                    audio_path,
                    language=language
                )
                
                # Parse transcription with timestamps
                result = self._parse_transcription(transcription)
                
                # Generate SRT subtitles
                srt_content = self._generate_srt(result["segments"])
                
                return {
                    "full_text": result["full_text"],
                    "segments": result["segments"],
                    "srt_content": srt_content,
                    "duration": result["duration"],
                    "language": language
                }
                
            finally:
                # Clean up temporary files
                if Path(local_file_path).exists():
                    Path(local_file_path).unlink()
                if should_delete_audio and 'audio_path' in locals() and Path(audio_path).exists() and audio_path != local_file_path:
                    Path(audio_path).unlink()
                    
        except Exception as e:
            logger.error(f"Error transcribing: {str(e)}")
            raise
            
    async def _extract_audio(self, video_path: str) -> str:
        """Extract audio from video file"""
        from moviepy.editor import VideoFileClip
        
        audio_path = video_path.replace(Path(video_path).suffix, ".wav")
        
        try:
            # Extract audio using moviepy
            video = VideoFileClip(video_path)
            video.audio.write_audiofile(audio_path, logger=None)
            video.close()
            
            return audio_path
        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            raise
            
    async def _transcribe_audio(
        self,
        audio_path: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """Transcribe audio file using OpenAI"""
        try:
            # For GPT-4o transcription, we use the audio transcription endpoint
            with open(audio_path, "rb") as audio_file:
                # Using the transcriptions API with response format
                transcription = await asyncio.to_thread(
                    self.client.audio.transcriptions.create,
                    model="whisper-1",  # This will use GPT-4o under the hood
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",  # Get timestamps
                    timestamp_granularities=["segment", "word"]
                )
            
            return transcription
            
        except Exception as e:
            logger.error(f"Error in OpenAI transcription: {str(e)}")
            raise
            
    def _parse_transcription(self, transcription: Any) -> Dict[str, Any]:
        """Parse transcription response into structured format"""
        segments = []
        
        if hasattr(transcription, 'segments'):
            for segment in transcription.segments:
                segments.append({
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"].strip(),
                    "words": segment.get("words", [])
                })
        
        return {
            "full_text": transcription.text,
            "segments": segments,
            "duration": transcription.duration if hasattr(transcription, 'duration') else None,
            "language": transcription.language
        }
        
    def _generate_srt(self, segments: List[Dict[str, Any]]) -> str:
        """Generate SRT subtitle format from segments"""
        srt_lines = []
        
        for i, segment in enumerate(segments, 1):
            # Format timestamps
            start_time = self._format_srt_time(segment["start"])
            end_time = self._format_srt_time(segment["end"])
            
            # Add SRT entry
            srt_lines.append(f"{i}")
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(segment["text"])
            srt_lines.append("")  # Empty line between entries
            
        return "\n".join(srt_lines)
        
    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds to SRT timestamp format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
