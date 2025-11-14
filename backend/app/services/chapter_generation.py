"""
Chapter generation service using OpenAI GPT-5
"""

import logging
from typing import Dict, Any, List, Optional
from openai import OpenAI
import json
import re
import asyncio
from datetime import timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)


class ChapterGenerationService:
    """Service for generating chapters using GPT-5's new Responses API"""
    
    def __init__(self):
        # Set a generous timeout for GPT-5 reasoning (3 minutes)
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=180.0  # 3 minutes for GPT-5 reasoning
        )
        
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
            logger.info("Generating chapters using GPT-5 Responses API")
            
            # Prepare the input for GPT-5
            input_text = self._prepare_input(transcription, slide_count, custom_prompts)
            
            logger.debug(f"Calling GPT-5 with model: {settings.GPT5_MODEL}")
            
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
            
            logger.info("GPT-5 response received successfully")
            logger.debug(f"Response ID: {response.id if hasattr(response, 'id') else 'unknown'}")
            
            # Extract chapters from the response
            chapters = self._extract_chapters_from_response(response)
            
            if not chapters:
                logger.error("No chapters extracted from GPT-5 response")
                logger.debug(f"Response output types: {[item.type for item in response.output if hasattr(item, 'type')]}")
            
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
        # The response should contain function calls in the output array
        for item in response.output:
            if hasattr(item, 'type') and item.type == 'function_call':
                if hasattr(item, 'name') and item.name == 'create_chapters':
                    # Parse the function call arguments
                    # In Responses API, arguments can be a string or already parsed
                    arguments = item.arguments if hasattr(item, 'arguments') else item.output
                    if isinstance(arguments, str):
                        chapters_data = json.loads(arguments)
                    else:
                        chapters_data = arguments
                    return chapters_data.get('chapters', [])
        
        # If no function call found, try to extract from message
        for item in response.output:
            if hasattr(item, 'type') and item.type == 'message':
                if hasattr(item, 'content') and item.content:
                    # Content is an array of content items
                    for content_item in item.content:
                        if hasattr(content_item, 'type') and content_item.type == 'output_text':
                            text = content_item.text if hasattr(content_item, 'text') else str(content_item)
                            try:
                                # Look for JSON in the message
                                json_match = re.search(r'\{.*"chapters".*\}', text, re.DOTALL)
                                if json_match:
                                    data = json.loads(json_match.group())
                                    if 'chapters' in data:
                                        return data['chapters']
                            except Exception as e:
                                logger.debug(f"Failed to parse JSON from message: {e}")
        
        logger.warning("No chapters found in GPT-5 response")
        return []
        
    def _format_chapters(
        self,
        chapters: List[Dict[str, Any]],
        transcription: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Format chapters into the required output format"""
        formatted = []
        qa_counter = 0
        
        for i, chapter in enumerate(chapters):
            # Get title and normalize special characters
            title = chapter['title']
            title = self._normalize_text(title)
            
            # Determine image name
            if chapter.get('is_qa', False):
                qa_counter += 1
                image_name = "qa"
                # Override title to standard Q&A format
                title = f"Q&A #{qa_counter}"
            else:
                slide_num = chapter.get('slide_number', i + 1)
                image_name = str(slide_num)
            
            formatted.append({
                "time_seconds": chapter['timestamp_seconds'],
                "image_name": image_name,
                "description": title
            })
        
        # Sort by timestamp
        formatted.sort(key=lambda x: x['time_seconds'])
        
        return formatted
    
    def _normalize_text(self, text: str) -> str:
        """Normalize Unicode characters to ASCII equivalents"""
        import unicodedata
        
        # Replace common Unicode characters with ASCII equivalents
        replacements = {
            '\u2011': '-',  # Non-breaking hyphen
            '\u2013': '-',  # En dash
            '\u2014': '--', # Em dash
            '\u2018': "'",  # Left single quote
            '\u2019': "'",  # Right single quote
            '\u201c': '"',  # Left double quote
            '\u201d': '"',  # Right double quote
            '\u2026': '...', # Ellipsis
        }
        
        for unicode_char, ascii_char in replacements.items():
            text = text.replace(unicode_char, ascii_char)
        
        # Remove any remaining non-ASCII characters
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ascii', 'ignore').decode('ascii')
        
        return text
        
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
