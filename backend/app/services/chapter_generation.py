"""
Chapter generation service using OpenAI GPT-5
"""

import logging
from typing import Dict, Any, List, Optional
from openai import OpenAI
import json
import re
from datetime import timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)


class ChapterGenerationService:
    """Service for generating chapters using GPT-5's new Responses API"""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
    async def generate_chapters(
        self,
        transcription: Dict[str, Any],
        slide_count: int,
        custom_prompts: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate chapters from transcription using GPT-5
        
        Args:
            transcription: Transcription data with text and segments
            slide_count: Number of slides extracted from presentation
            custom_prompts: Optional custom prompts for generation
            
        Returns:
            List of chapter entries with timestamps and descriptions
        """
        try:
            logger.info("Generating chapters using GPT-5")
            
            # Prepare the input for GPT-5
            input_text = self._prepare_input(transcription, slide_count, custom_prompts)
            
            # Call GPT-5 using the new Responses API
            response = self.client.responses.create(
                model=settings.GPT5_MODEL,
                input=input_text,
                reasoning={
                    "effort": "medium"  # Use medium reasoning for balanced performance
                },
                text={
                    "verbosity": "low"  # We want concise chapter descriptions
                },
                tools=[{
                    "type": "function",
                    "name": "create_chapters",
                    "description": "Create chapter markers for the video presentation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chapters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "timestamp_seconds": {"type": "integer"},
                                        "slide_number": {"type": "integer"},
                                        "title": {"type": "string"},
                                        "is_qa": {"type": "boolean"}
                                    },
                                    "required": ["timestamp_seconds", "slide_number", "title", "is_qa"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["chapters"],
                        "additionalProperties": False
                    }
                }],
                tool_choice={
                    "type": "function",
                    "name": "create_chapters"
                }
            )
            
            # Extract chapters from the response
            chapters = self._extract_chapters_from_response(response)
            
            # Validate and format chapters
            formatted_chapters = self._format_chapters(chapters, transcription)
            
            # Detect and mark Q&A sections
            formatted_chapters = self._detect_qa_sections(formatted_chapters)
            
            return formatted_chapters
            
        except Exception as e:
            logger.error(f"Error generating chapters: {str(e)}")
            raise
            
    def _prepare_input(
        self,
        transcription: Dict[str, Any],
        slide_count: int,
        custom_prompts: Optional[Dict[str, str]] = None
    ) -> str:
        """Prepare input prompt for GPT-5"""
        
        base_prompt = custom_prompts.get("base_prompt") if custom_prompts else None
        
        if not base_prompt:
            base_prompt = f"""Analyze this presentation transcript and create chapter markers.

TRANSCRIPT:
{transcription['full_text']}

CONTEXT:
- Total presentation slides: {slide_count}
- Video duration: {transcription.get('duration', 'unknown')} seconds
- The presentation slides are numbered from 1 to {slide_count}

INSTRUCTIONS:
1. Identify major topic transitions in the presentation
2. Create chapter markers that align with slide changes when possible
3. Each chapter should have a clear, descriptive title
4. Detect Q&A sections - look for phrases like "questions", "Q&A", "let me answer", etc.
5. For Q&A sections, set is_qa to true
6. Ensure timestamps are in seconds and monotonically increasing
7. Try to have one chapter per slide, but combine if slides are discussed very briefly

Create concise, professional chapter titles that reflect the content being discussed."""

        return base_prompt
        
    def _extract_chapters_from_response(self, response: Any) -> List[Dict[str, Any]]:
        """Extract chapters from GPT-5 response"""
        # The response should contain tool calls
        for item in response.output:
            if hasattr(item, 'type') and item.type == 'function_call':
                if item.name == 'create_chapters':
                    # Parse the function call output
                    chapters_data = json.loads(item.output)
                    return chapters_data.get('chapters', [])
        
        # If no function call found, try to extract from message
        for item in response.output:
            if hasattr(item, 'type') and item.type == 'message':
                # Try to extract JSON from the message content
                content = item.content[0].text if item.content else ""
                try:
                    # Look for JSON in the message
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group())
                        if 'chapters' in data:
                            return data['chapters']
                except:
                    pass
        
        logger.warning("No chapters found in GPT-5 response")
        return []
        
    def _format_chapters(
        self,
        chapters: List[Dict[str, Any]],
        transcription: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Format chapters into the required output format"""
        formatted = []
        
        for i, chapter in enumerate(chapters):
            # Determine image name
            if chapter.get('is_qa', False):
                image_name = "qa"
            else:
                slide_num = chapter.get('slide_number', i + 1)
                image_name = str(slide_num)
            
            formatted.append({
                "time_seconds": chapter['timestamp_seconds'],
                "image_name": image_name,
                "description": chapter['title']
            })
        
        # Sort by timestamp
        formatted.sort(key=lambda x: x['time_seconds'])
        
        return formatted
        
    def _detect_qa_sections(
        self,
        chapters: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect and mark Q&A sections based on keywords"""
        qa_keywords = [kw.lower() for kw in settings.QA_KEYWORDS]
        
        for chapter in chapters:
            description_lower = chapter['description'].lower()
            
            # Check if any Q&A keyword is in the description
            if any(keyword in description_lower for keyword in qa_keywords):
                chapter['image_name'] = "qa"
        
        return chapters
