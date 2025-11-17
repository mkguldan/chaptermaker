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
        # Set a generous timeout for GPT-5 reasoning (5 minutes)
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=300.0  # 5 minutes for GPT-5 reasoning with timestamped transcripts
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
                    "effort": "medium"  # Balanced reasoning - "high" takes 9+ minutes and times out
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
                                        "timestamp_seconds": {
                                            "type": "integer",
                                            "description": "The EXACT timestamp in seconds where this chapter begins. Read the [MM:SS] timestamp from the transcript line where the topic/question starts and convert to seconds (MM*60 + SS). Be precise - use the timestamp of the FIRST line introducing this topic."
                                        },
                                        "slide_number": {
                                            "type": "integer",
                                            "description": "The slide number being discussed (1 to N)"
                                        },
                                        "title": {
                                            "type": "string",
                                            "description": "Concise chapter title describing the content"
                                        },
                                        "is_qa": {
                                            "type": "boolean",
                                            "description": "Set to true ONLY when an actual question is being asked by an audience member (not for transitions like 'let's take questions' or 'transition to Q&A'). Create a SEPARATE chapter for EACH individual question. Must contain a real question starting with words like 'how', 'what', 'why', 'can', 'should', 'thanks for', etc. Verify the transcript text at this timestamp contains an actual question being asked."
                                        }
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
            # Format transcript with timestamps so GPT-5 can see WHEN things are said
            timestamped_transcript = self._format_transcript_with_timestamps(transcription)
            
            base_prompt = f"""Analyze this presentation transcript and create chapter markers.

TRANSCRIPT WITH TIMESTAMPS:
{timestamped_transcript}

CONTEXT:
- Total presentation slides: {slide_count}
- Video duration: {transcription.get('duration', 'unknown')} seconds
- The presentation slides are numbered from 1 to {slide_count}

INSTRUCTIONS:
1. Each line in the transcript shows EXACTLY when (in [MM:SS] format) that text is spoken
2. Identify major topic transitions by analyzing the ACTUAL CONTENT and noting the timestamp where they occur
3. Use the EXACT timestamps you see in the transcript - convert [MM:SS] to seconds (MM*60 + SS)
4. When a topic changes, use the timestamp of the FIRST sentence introducing that new topic (not nearby sentences)
5. Look for phrases that signal new topics: "So...", "Now...", "Second example...", "And I will give you...", "What is important..."
6. Create chapter markers that align with slide changes when possible
7. Each chapter should have a clear, descriptive title
8. Try to have one chapter per slide, but combine if slides are discussed very briefly
9. Ensure timestamps are in seconds and monotonically increasing
10. CRITICAL: DO NOT estimate or space chapters evenly - use the EXACT timestamps from the transcript
11. Precision matters: Use the timestamp of the EXACT line where the speaker begins the new topic, not 20-40 seconds before or after
12. For case studies/examples, mark the chapter at the line where the speaker explicitly introduces it (e.g., "I will give you this example", "Second example")
13. WORKFLOW: Read through the transcript systematically, note each topic change and its [MM:SS] timestamp, then convert all to seconds
14. Double-check: Before finalizing, verify each timestamp matches the actual line in the transcript where that topic/question begins

CRITICAL Q&A DETECTION RULES:
- SCAN THE ENTIRE TRANSCRIPT carefully to find ALL questions asked by audience members
- CREATE A SEPARATE CHAPTER for EACH individual question asked
- ONLY mark a chapter as Q&A (is_qa=true) when an ACTUAL QUESTION is being asked by an audience member
- Look for explicit questions like: "How do...", "What is...", "Can you...", "Why does...", "When should...", "Thanks for...", "Would you..."
- Look for audience members asking: "So my question is...", "I was wondering...", "Could you explain...", "I have a question about..."
- Questions often start with "Thanks/Thank you for..." followed by actual question content
- CRITICAL: DO NOT mark transitions/announcements as Q&A, such as:
  * "Now let's take questions"
  * "We have time for Q&A"
  * "Let's open it up for questions"
  * "Any questions?"
  * "Transition to Q&A" or "Transition to audience Q&A"
  * "Moving to questions"
  * "Closing remarks"
  * "Thank you" (without a question following)
- Each Q&A chapter should start at the EXACT timestamp where the question asker begins speaking
- Scan through the ENTIRE Q&A section - there may be 5, 6, or more individual questions
- If someone says "let me answer that" or "great question", that's the presenter answering, NOT a new question
- Use the [MM:SS] timestamp of the FIRST line where each new person asks a question
- Place the timestamp at the EXACT second when the question asker starts speaking (use the timestamp from that transcript line)
- VERIFY: For each Q&A chapter, ensure the timestamp points to the start of a question, not an answer or transition

EXAMPLES - Correct Timestamp Detection:

Topic Transitions:
"[08:28] Just I want to discuss a little bit about chain of custody..."
→ New topic starts HERE at 508s (8*60 + 28), not 20s before or after

"[12:02] And I will give you this example. We start a 10-year project..."
→ Example begins HERE at 722s (12*60 + 2), mark this exact timestamp

Q&A Detection:
"[21:19] Thanks a lot for your presentation. You mentioned that you are willing to pay a higher price..."
→ Q&A #1 starts at 1279s (21*60 + 19)

"[24:01] Thank you very much for the presentation. Very interesting. And actually, I love your identify options..."
→ Q&A #2 starts at 1441s (24*60 + 1)

"[27:02] Thanks for the presentation. I think you've been focusing on the area of recyclability..."
→ Q&A #3 starts at 1622s (27*60 + 2)

"[31:00] I was really impressed by how you're involving stakeholders..."
→ Q&A #5 starts at 1860s (31*60 + 0)

"[21:02] Thank you very much." (no question follows)
→ NOT Q&A (just closing)

"[28:20] We now have time for questions."
→ NOT Q&A (transition announcement)

Create concise, professional chapter titles that reflect the content being discussed."""

        return base_prompt
    
    def _format_transcript_with_timestamps(self, transcription: Dict[str, Any]) -> str:
        """Format transcript with timestamps so GPT-5 can see WHEN things are said"""
        segments = transcription.get('segments', [])
        
        if not segments:
            # Fallback to full text if segments not available
            return transcription['full_text']
        
        formatted_lines = []
        for segment in segments:
            start_time = int(segment['start'])
            # Format as "[MM:SS] text"
            minutes = start_time // 60
            seconds = start_time % 60
            timestamp = f"[{minutes:02d}:{seconds:02d}]"
            text = segment['text'].strip()
            formatted_lines.append(f"{timestamp} {text}")
        
        return "\n".join(formatted_lines)
        
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
            
            # Check if this is a Q&A chapter
            is_qa = chapter.get('is_qa', False)
            
            # Filter out false Q&A markers (transitions, closings, etc.)
            if is_qa:
                title_lower = title.lower()
                # Phrases that indicate this is NOT an actual Q&A section
                transition_phrases = [
                    'transition', 'opening', 'closing', 'introduction',
                    'let\'s take', 'time for', 'any questions', 'open it up',
                    'now for questions', 'we have time', 'thank you',
                    'that\'s all', 'wrapping up', 'in conclusion',
                    'audience q&a', 'transition to', 'moving to', 'questions section'
                ]
                
                # If the title contains transition phrases, don't mark as Q&A
                if any(phrase in title_lower for phrase in transition_phrases):
                    logger.info(f"Filtering out false Q&A marker: '{title}'")
                    is_qa = False
            
            # Determine image name
            if is_qa:
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
