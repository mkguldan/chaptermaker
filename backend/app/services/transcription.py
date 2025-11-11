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
        # Initialize OpenAI client with increased timeout for large files
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=600.0,  # 10 minutes timeout for large audio files
            max_retries=3
        )
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
            
    async def _compress_audio(self, audio_path: str) -> str:
        """Compress audio file to reduce size while maintaining quality for speech"""
        try:
            import subprocess
            
            output_path = audio_path.replace(Path(audio_path).suffix, "_compressed.mp3")
            
            logger.info(f"Compressing audio from {Path(audio_path).stat().st_size / (1024*1024):.2f} MB...")
            
            # Use ffmpeg to compress: mono, 64kbps (good for speech), 16kHz sample rate
            cmd = [
                "ffmpeg",
                "-i", audio_path,
                "-ac", "1",  # mono
                "-ar", "16000",  # 16kHz sample rate
                "-b:a", "64k",  # 64kbps bitrate
                "-y",  # overwrite
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg compression failed: {result.stderr}")
                raise Exception("Audio compression failed")
            
            compressed_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
            logger.info(f"Compressed audio to {compressed_size_mb:.2f} MB")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error compressing audio: {str(e)}")
            raise
    
    async def _split_audio(self, audio_path: str, chunk_duration_minutes: int = 10) -> list:
        """Split large audio file into smaller chunks"""
        try:
            import subprocess
            
            chunks = []
            chunk_dir = Path(audio_path).parent / "chunks"
            chunk_dir.mkdir(exist_ok=True)
            
            # Get audio duration
            duration_cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ]
            
            result = subprocess.run(duration_cmd, capture_output=True, text=True)
            total_duration = float(result.stdout.strip())
            
            logger.info(f"Splitting audio: {total_duration:.2f} seconds into {chunk_duration_minutes}-minute chunks")
            
            chunk_duration_seconds = chunk_duration_minutes * 60
            num_chunks = int(total_duration / chunk_duration_seconds) + 1
            
            for i in range(num_chunks):
                start_time = i * chunk_duration_seconds
                chunk_path = chunk_dir / f"chunk_{i:03d}.mp3"
                
                cmd = [
                    "ffmpeg",
                    "-i", audio_path,
                    "-ss", str(start_time),
                    "-t", str(chunk_duration_seconds),
                    "-ac", "1",  # mono
                    "-ar", "16000",  # 16kHz
                    "-b:a", "64k",  # 64kbps
                    "-y",
                    str(chunk_path)
                ]
                
                subprocess.run(cmd, capture_output=True, check=True)
                
                if chunk_path.exists() and chunk_path.stat().st_size > 0:
                    chunks.append({
                        "path": str(chunk_path),
                        "start_time": start_time,
                        "chunk_index": i
                    })
            
            logger.info(f"Split audio into {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error splitting audio: {str(e)}")
            raise
    
    async def _transcribe_audio(
        self,
        audio_path: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """Transcribe audio file using OpenAI, with automatic compression and chunking for large files"""
        # Check file size first
        file_size = Path(audio_path).stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"Audio file size: {file_size_mb:.2f} MB")
        
        processed_audio_path = audio_path
        needs_cleanup = False
        chunks_to_cleanup = []
        
        try:
            # If file is too large, try compression first
            if file_size_mb > 25:
                logger.info(f"File exceeds 25 MB limit, attempting compression...")
                processed_audio_path = await self._compress_audio(audio_path)
                needs_cleanup = True
                
                compressed_size_mb = Path(processed_audio_path).stat().st_size / (1024 * 1024)
                
                # If still too large after compression, split into chunks
                if compressed_size_mb > 25:
                    logger.info(f"Compressed file still too large ({compressed_size_mb:.2f} MB), splitting into chunks...")
                    chunks = await self._split_audio(processed_audio_path, chunk_duration_minutes=10)
                    chunks_to_cleanup = [chunk["path"] for chunk in chunks]
                    
                    # Transcribe each chunk
                    all_segments = []
                    cumulative_offset = 0.0
                    
                    for chunk_info in chunks:
                        logger.info(f"Transcribing chunk {chunk_info['chunk_index'] + 1}/{len(chunks)}...")
                        
                        with open(chunk_info["path"], "rb") as audio_file:
                            transcription = await asyncio.to_thread(
                                self.client.audio.transcriptions.create,
                                model="whisper-1",
                                file=audio_file,
                                language=language,
                                response_format="verbose_json",
                                timestamp_granularities=["segment", "word"]
                            )
                        
                        # Adjust timestamps to account for chunk offset
                        if hasattr(transcription, 'segments'):
                            for segment in transcription.segments:
                                segment["start"] += cumulative_offset
                                segment["end"] += cumulative_offset
                                if "words" in segment:
                                    for word in segment["words"]:
                                        word["start"] += cumulative_offset
                                        word["end"] += cumulative_offset
                                all_segments.append(segment)
                        
                        cumulative_offset += chunk_info.get("duration", 600)  # 10 minutes default
                    
                    # Create a combined transcription object
                    class CombinedTranscription:
                        def __init__(self, segments):
                            self.segments = segments
                            self.text = " ".join([seg.get("text", "") for seg in segments])
                    
                    logger.info(f"Successfully transcribed all {len(chunks)} chunks")
                    return CombinedTranscription(all_segments)
            
            # File is small enough, transcribe directly
            with open(processed_audio_path, "rb") as audio_file:
                logger.info("Sending audio to OpenAI for transcription...")
                transcription = await asyncio.to_thread(
                    self.client.audio.transcriptions.create,
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment", "word"]
                )
            
            logger.info("Transcription completed successfully")
            return transcription
            
        except Exception as e:
            logger.error(f"Error in OpenAI transcription: {str(e)}", exc_info=True)
            if "Connection error" in str(e) or "timeout" in str(e).lower():
                raise Exception(f"OpenAI API connection timeout. Please try again.")
            raise
            
        finally:
            # Clean up temporary files
            if needs_cleanup and Path(processed_audio_path).exists():
                try:
                    Path(processed_audio_path).unlink()
                except:
                    pass
            
            for chunk_path in chunks_to_cleanup:
                try:
                    Path(chunk_path).unlink()
                except:
                    pass
            
            # Clean up chunks directory
            chunk_dir = Path(audio_path).parent / "chunks"
            if chunk_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                except:
                    pass
            
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
