#!/usr/bin/env python3
"""
Video Chapter Maker CLI Tool
Command-line interface for batch processing videos locally
"""

import os
import sys
import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
import requests
from google.cloud import storage
from google.oauth2 import service_account

# Add parent directory to path to import backend modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.config import Settings
from app.services.video_processor import VideoProcessorService
from app.services.storage import StorageService
from app.services.job_manager import JobManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChapterMakerCLI:
    """CLI tool for Video Chapter Maker"""
    
    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.storage_service = StorageService()
        self.processor = VideoProcessorService()
        self.job_manager = JobManager()
        
    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """Load configuration from file or environment"""
        config = {}
        
        # Try to load from config file
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
        
        # Override with environment variables
        config['openai_api_key'] = os.getenv('OPENAI_API_KEY', config.get('openai_api_key'))
        config['gcp_project_id'] = os.getenv('GCP_PROJECT_ID', config.get('gcp_project_id', 'ai-mvp-452812'))
        config['service_account_key'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 
                                                  config.get('service_account_key', 'service-account-key.json'))
        
        # Validate required settings
        if not config.get('openai_api_key'):
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        return config
        
    async def process_single(
        self, 
        video_path: str, 
        presentation_path: str,
        output_dir: str = None
    ) -> Dict[str, Any]:
        """Process a single video/presentation pair"""
        logger.info(f"Processing video: {video_path}")
        logger.info(f"With presentation: {presentation_path}")
        
        # Validate files exist
        if not Path(video_path).exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if not Path(presentation_path).exists():
            raise FileNotFoundError(f"Presentation file not found: {presentation_path}")
        
        # Upload files to GCS
        video_gcs_path = await self._upload_file(video_path, 'video')
        presentation_gcs_path = await self._upload_file(presentation_path, 'presentation')
        
        # Create job
        job_id = await self.processor.create_processing_job(
            video_path=video_gcs_path,
            presentation_path=presentation_gcs_path,
            options={'language': 'en'}
        )
        
        logger.info(f"Created job: {job_id}")
        
        # Process video
        await self.processor.process_video_async(job_id)
        
        # Download results
        if output_dir:
            await self._download_results(job_id, output_dir)
            
        return {'job_id': job_id, 'status': 'completed'}
        
    async def process_batch(
        self,
        input_dir: str,
        output_dir: str,
        pattern: str = "*.mp4"
    ) -> List[Dict[str, Any]]:
        """Process all videos in a directory"""
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")
            
        # Find video files
        video_files = list(input_path.glob(pattern))
        logger.info(f"Found {len(video_files)} video files")
        
        results = []
        for video_path in video_files:
            # Look for matching presentation
            base_name = video_path.stem
            presentation_path = None
            
            for ext in ['.pptx', '.ppt', '.pdf']:
                candidate = input_path / f"{base_name}{ext}"
                if candidate.exists():
                    presentation_path = candidate
                    break
                    
            if not presentation_path:
                logger.warning(f"No presentation found for {video_path.name}, skipping")
                continue
                
            try:
                # Process the pair
                result = await self.process_single(
                    str(video_path),
                    str(presentation_path),
                    output_dir
                )
                results.append({
                    'video': video_path.name,
                    'presentation': presentation_path.name,
                    **result
                })
                
            except Exception as e:
                logger.error(f"Error processing {video_path.name}: {str(e)}")
                results.append({
                    'video': video_path.name,
                    'presentation': presentation_path.name if presentation_path else None,
                    'status': 'failed',
                    'error': str(e)
                })
                
        return results
        
    async def _upload_file(self, local_path: str, file_type: str) -> str:
        """Upload file to GCS"""
        file_name = Path(local_path).name
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        gcs_path = f"cli-uploads/{timestamp}/{file_type}/{file_name}"
        
        logger.info(f"Uploading {file_name} to GCS...")
        
        await self.storage_service.upload_file(
            local_path=local_path,
            gcs_path=gcs_path
        )
        
        return gcs_path
        
    async def _download_results(self, job_id: str, output_dir: str) -> None:
        """Download job results to local directory"""
        logger.info(f"Downloading results for job {job_id}...")
        
        # Get job results
        results = await self.job_manager.get_job_results(job_id)
        if not results:
            logger.error(f"No results found for job {job_id}")
            return
            
        # Create output directory
        output_path = Path(output_dir) / job_id
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Download each file
        for file_type, gcs_path in results.output_files.items():
            if file_type == 'slides':
                # Create slides directory
                slides_dir = output_path / 'slides'
                slides_dir.mkdir(exist_ok=True)
                
                # Download all slide images
                # This is simplified - in production you'd list the directory
                logger.info(f"Slides saved to: {slides_dir}")
            else:
                # Download individual file
                local_file = output_path / Path(gcs_path).name
                download_url = await self.storage_service.generate_download_url(gcs_path)
                
                response = requests.get(download_url)
                with open(local_file, 'wb') as f:
                    f.write(response.content)
                    
                logger.info(f"Downloaded: {local_file}")
                
    def list_jobs(self, status: str = None) -> None:
        """List processing jobs"""
        # This would connect to the API or database
        logger.info("Listing jobs functionality not implemented in offline mode")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Video Chapter Maker CLI - Process videos to generate chapters and subtitles"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Process single video
    single_parser = subparsers.add_parser('process', help='Process a single video')
    single_parser.add_argument('--video', '-v', required=True, help='Path to video file')
    single_parser.add_argument('--presentation', '-p', required=True, help='Path to presentation file')
    single_parser.add_argument('--output', '-o', help='Output directory for results')
    single_parser.add_argument('--config', '-c', help='Config file path')
    
    # Batch process
    batch_parser = subparsers.add_parser('batch', help='Batch process videos')
    batch_parser.add_argument('--input', '-i', required=True, help='Input directory containing videos')
    batch_parser.add_argument('--output', '-o', required=True, help='Output directory for results')
    batch_parser.add_argument('--pattern', default='*.mp4', help='Video file pattern (default: *.mp4)')
    batch_parser.add_argument('--config', '-c', help='Config file path')
    
    # List jobs
    list_parser = subparsers.add_parser('list', help='List processing jobs')
    list_parser.add_argument('--status', '-s', help='Filter by status')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    try:
        # Initialize CLI
        cli = ChapterMakerCLI(config_path=args.config if 'config' in args else None)
        
        # Run async command
        if args.command == 'process':
            asyncio.run(cli.process_single(
                video_path=args.video,
                presentation_path=args.presentation,
                output_dir=args.output
            ))
        elif args.command == 'batch':
            results = asyncio.run(cli.process_batch(
                input_dir=args.input,
                output_dir=args.output,
                pattern=args.pattern
            ))
            
            # Print summary
            logger.info(f"\nBatch processing complete:")
            logger.info(f"Total: {len(results)}")
            logger.info(f"Successful: {len([r for r in results if r['status'] == 'completed'])}")
            logger.info(f"Failed: {len([r for r in results if r['status'] == 'failed'])}")
            
        elif args.command == 'list':
            cli.list_jobs(status=args.status)
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
