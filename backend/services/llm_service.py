"""
LLM Service for Meeting-Ops
Uses Granite 3.3 2B on llama.cpp Vulkan via OpenAI-compatible API
"""

import json
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

import requests
from redis import Redis
import hashlib

logger = logging.getLogger(__name__)

# llama.cpp Vulkan endpoint
LLAMACPP_URL = "http://localhost:11437"
LLAMACPP_MODEL = "granite-3.3-2b-instruct"


class GemmaService:
    """Service for LLM operations via llama.cpp Vulkan (name kept for backward compatibility)"""

    def __init__(self, host: str = LLAMACPP_URL, redis_client: Optional[Redis] = None):
        """
        Initialize LLM service

        Args:
            host: llama.cpp server URL
            redis_client: Optional Redis client for caching
        """
        self.base_url = host
        self.model = LLAMACPP_MODEL
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 hour cache

    def _call_llm(self, system_prompt: str, user_prompt: str,
                  max_tokens: int = 2048, temperature: float = 0.7,
                  top_p: float = 0.9, timeout: int = 30) -> Optional[str]:
        """Call Granite 3.3 2B via OpenAI-compatible chat completions API"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "top_p": top_p,
                    "stream": False
                },
                timeout=timeout
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()
            else:
                logger.error(f"llama.cpp API error: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            logger.error("llama.cpp request timed out")
            return None
        except Exception as e:
            logger.error(f"llama.cpp call failed: {e}")
            return None

    def _get_cache_key(self, prefix: str, content: str) -> str:
        """Generate cache key from content"""
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"llm:{prefix}:{content_hash}"

    async def generate_meeting_notes(self, transcript: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Generate structured meeting notes from transcript

        Args:
            transcript: Meeting transcript text
            use_cache: Whether to use cached results

        Returns:
            Dictionary with meeting notes structure
        """
        # Check cache first
        if use_cache and self.redis:
            cache_key = self._get_cache_key("notes", transcript)
            cached = self.redis.get(cache_key)
            if cached:
                logger.info("Returning cached meeting notes")
                return json.loads(cached)

        system_prompt = "You are an expert meeting assistant. Extract structured information from meeting transcripts and format it as valid JSON."

        user_prompt = f"""
        Analyze this meeting transcript and generate structured notes.
        Focus on extracting actionable information and key discussion points.

        TRANSCRIPT:
        {transcript}

        Generate a JSON response with the following structure:
        {{
            "summary": "Brief 2-3 sentence meeting summary",
            "keyPoints": ["Key point 1", "Key point 2"],
            "decisions": ["Decision 1", "Decision 2"],
            "actionItems": [
                {{"task": "Task description", "owner": "Person name or 'Unassigned'", "deadline": "Date or 'TBD'"}}
            ],
            "questions": ["Unresolved question 1"],
            "nextSteps": ["Next step 1", "Next step 2"],
            "participants": ["Name 1", "Name 2"],
            "sentiment": "positive/neutral/negative",
            "topics": ["Topic 1", "Topic 2"]
        }}

        Important:
        - Extract real information from the transcript
        - If something is not mentioned, use empty arrays []
        - Keep responses concise and actionable
        - Format dates as YYYY-MM-DD where possible
        """

        try:
            response_text = await asyncio.to_thread(
                self._call_llm, system_prompt, user_prompt
            )

            if response_text:
                result = json.loads(response_text)

                # Add metadata
                result['generated_at'] = datetime.now(timezone.utc).isoformat()
                result['model'] = self.model

                # Cache the result
                if self.redis:
                    cache_key = self._get_cache_key("notes", transcript)
                    self.redis.setex(cache_key, self.cache_ttl, json.dumps(result))

                return result
            else:
                return self._get_fallback_notes()

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return self._get_fallback_notes()
        except Exception as e:
            logger.error(f"Error generating meeting notes: {e}")
            return self._get_fallback_notes()

    async def generate_incremental_notes(self,
                                        new_transcript: str,
                                        previous_notes: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Generate incremental meeting notes for live transcription

        Args:
            new_transcript: New transcript segment (last 30-60 seconds)
            previous_notes: Previous meeting notes to update

        Returns:
            Updated meeting notes
        """
        context = ""
        if previous_notes:
            context = f"""
            Previous notes summary: {previous_notes.get('summary', '')}
            Previous key points: {', '.join(previous_notes.get('keyPoints', []))}
            Previous action items: {len(previous_notes.get('actionItems', []))} items
            """

        system_prompt = "You are updating meeting notes with new information. Merge new content with existing notes while avoiding duplication."

        user_prompt = f"""
        Update the meeting notes with this new transcript segment.
        {context}

        NEW TRANSCRIPT SEGMENT:
        {new_transcript}

        Generate an updated JSON response:
        {{
            "summary": "Updated meeting summary",
            "keyPoints": ["Point 1", ...],
            "decisions": ["Decision 1", ...],
            "actionItems": [{{"task": "", "owner": "", "deadline": ""}}],
            "questions": ["Question 1", ...],
            "nextSteps": ["Step 1", ...],
            "participants": ["Name 1", ...],
            "sentiment": "positive/neutral/negative",
            "topics": ["Topic 1", ...],
            "isIncremental": true,
            "lastUpdated": "ISO timestamp"
        }}
        """

        try:
            response_text = await asyncio.to_thread(
                self._call_llm, system_prompt, user_prompt,
                max_tokens=1536, temperature=0.7
            )

            if response_text:
                result = json.loads(response_text)
                result['lastUpdated'] = datetime.now(timezone.utc).isoformat()
                result['isIncremental'] = True
                return result
            else:
                return previous_notes or self._get_fallback_notes()

        except Exception as e:
            logger.error(f"Error generating incremental notes: {e}")
            return previous_notes or self._get_fallback_notes()

    async def chat_with_meeting(self,
                               session_id: str,
                               query: str,
                               transcript: str,
                               history: Optional[List[Dict]] = None) -> str:
        """
        Chat about a specific meeting

        Args:
            session_id: Meeting session ID
            query: User question
            transcript: Meeting transcript for context
            history: Previous chat messages

        Returns:
            AI response
        """
        history_context = ""
        if history:
            history_context = "Previous conversation:\n"
            for msg in history[-5:]:  # Last 5 messages
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                history_context += f"{role}: {content}\n"

        system_prompt = "You are an AI assistant helping analyze a specific meeting. Reference specific parts of the meeting when relevant. Be concise but thorough."

        user_prompt = f"""
        MEETING TRANSCRIPT:
        {transcript[:8000]}

        {history_context}

        USER QUESTION: {query}

        Please provide a helpful, accurate response based on the meeting content.
        If the information isn't in the transcript, say so.
        """

        try:
            response_text = await asyncio.to_thread(
                self._call_llm, system_prompt, user_prompt,
                max_tokens=1024, temperature=0.8
            )

            return response_text or "I apologize, but I'm having trouble processing your request. Please try again."

        except Exception as e:
            logger.error(f"Error in meeting chat: {e}")
            return "I apologize, but I'm having trouble processing your request. Please try again."

    async def global_assistant_query(self,
                                   query: str,
                                   meeting_contexts: List[Dict],
                                   user_id: str) -> str:
        """
        Handle queries across multiple meetings

        Args:
            query: User question
            meeting_contexts: Relevant meeting contexts from RAG
            user_id: User ID for personalization

        Returns:
            AI response
        """
        # Build context from multiple meetings
        context_str = "Relevant meeting information:\n\n"
        for i, ctx in enumerate(meeting_contexts[:5], 1):
            context_str += f"Meeting {i} ({ctx.get('date', 'Unknown date')}):\n"
            context_str += f"Summary: {ctx.get('summary', 'No summary')}\n"
            context_str += f"Relevant excerpt: {ctx.get('excerpt', '')[:500]}\n\n"

        system_prompt = "You are an intelligent assistant with access to multiple meeting records. Synthesize information across meetings and provide actionable insights."

        user_prompt = f"""
        {context_str}

        USER QUESTION: {query}

        Provide a comprehensive response that references specific meetings when relevant.
        """

        try:
            response_text = await asyncio.to_thread(
                self._call_llm, system_prompt, user_prompt,
                max_tokens=1536, temperature=0.8, top_p=0.95
            )

            return response_text or "I apologize, but I'm having trouble accessing the meeting data. Please try again."

        except Exception as e:
            logger.error(f"Error in global assistant: {e}")
            return "I apologize, but I'm having trouble accessing the meeting data. Please try again."

    def _get_fallback_notes(self) -> Dict[str, Any]:
        """Get fallback notes structure when generation fails"""
        return {
            "summary": "Meeting notes generation failed",
            "keyPoints": [],
            "decisions": [],
            "actionItems": [],
            "questions": [],
            "nextSteps": [],
            "participants": [],
            "sentiment": "neutral",
            "topics": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": True
        }

    async def test_connection(self) -> bool:
        """Test connection to llama.cpp server"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=3)
            if response.status_code == 200:
                logger.info(f"Connected to llama.cpp at {self.base_url}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to connect to llama.cpp: {e}")
            return False


class MeetingNotesBuffer:
    """Buffer for accumulating transcript segments for notes generation"""

    def __init__(self,
                 gemma_service: GemmaService,
                 buffer_duration: int = 60,
                 min_words: int = 50):
        """
        Initialize meeting notes buffer

        Args:
            gemma_service: LLM service instance
            buffer_duration: Seconds to buffer before generating notes
            min_words: Minimum words before generating notes
        """
        self.gemma = gemma_service
        self.buffer_duration = buffer_duration
        self.min_words = min_words
        self.buffer = []
        self.last_generation = datetime.now(timezone.utc)
        self.current_notes = None

    async def add_segment(self, segment: Dict) -> Optional[Dict]:
        """
        Add transcript segment to buffer

        Args:
            segment: Transcript segment with text and metadata

        Returns:
            Updated notes if generated, None otherwise
        """
        self.buffer.append(segment)

        # Check if we should generate notes
        time_elapsed = (datetime.now(timezone.utc) - self.last_generation).seconds
        word_count = sum(len(s.get('text', '').split()) for s in self.buffer)

        if time_elapsed >= self.buffer_duration and word_count >= self.min_words:
            return await self.generate_notes()

        return None

    async def generate_notes(self) -> Optional[Dict]:
        """Generate notes from current buffer"""
        if not self.buffer:
            return None

        # Combine buffer segments
        transcript = "\n".join([
            f"{s.get('speaker', 'SPEAKER')}: {s.get('text', '')}"
            for s in self.buffer
        ])

        # Generate incremental notes
        self.current_notes = await self.gemma.generate_incremental_notes(
            transcript,
            self.current_notes
        )

        # Clear buffer and reset timer
        self.buffer = []
        self.last_generation = datetime.now(timezone.utc)

        return self.current_notes

    async def force_generation(self) -> Optional[Dict]:
        """Force notes generation regardless of buffer state"""
        if self.buffer:
            return await self.generate_notes()
        return self.current_notes
