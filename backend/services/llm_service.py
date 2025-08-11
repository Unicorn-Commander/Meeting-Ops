"""
LLM Service for Meeting-Ops
Provides Gemma3n integration for meeting notes generation and AI chat
"""

import json
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import ollama
from redis import Redis
import hashlib

logger = logging.getLogger(__name__)

class GemmaService:
    """Service for Gemma3n LLM operations"""
    
    def __init__(self, host: str = "http://localhost:11434", redis_client: Optional[Redis] = None):
        """
        Initialize Gemma3n service
        
        Args:
            host: Ollama server URL
            redis_client: Optional Redis client for caching
        """
        self.client = ollama.Client(host=host)
        self.model = "gemma3n:e4b"
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 hour cache
        
        # Check if model is available
        self._check_model_availability()
    
    def _check_model_availability(self):
        """Check if Gemma3n model is available"""
        try:
            models = self.client.list()
            available_models = [m['name'] for m in models.get('models', [])]
            if self.model not in available_models:
                logger.warning(f"Model {self.model} not found. Available models: {available_models}")
                logger.info(f"Pulling {self.model}...")
                self.client.pull(self.model)
        except Exception as e:
            logger.error(f"Error checking model availability: {e}")
    
    def _get_cache_key(self, prefix: str, content: str) -> str:
        """Generate cache key from content"""
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"gemma:{prefix}:{content_hash}"
    
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
        
        prompt = f"""
        Analyze this meeting transcript and generate structured notes.
        Focus on extracting actionable information and key discussion points.
        
        TRANSCRIPT:
        {transcript}
        
        Generate a JSON response with the following structure:
        {{
            "summary": "Brief 2-3 sentence meeting summary",
            "keyPoints": ["Key point 1", "Key point 2", ...],
            "decisions": ["Decision 1", "Decision 2", ...],
            "actionItems": [
                {{"task": "Task description", "owner": "Person name or 'Unassigned'", "deadline": "Date or 'TBD'"}},
                ...
            ],
            "questions": ["Unresolved question 1", ...],
            "nextSteps": ["Next step 1", "Next step 2", ...],
            "participants": ["Name 1", "Name 2", ...] (if identifiable),
            "sentiment": "positive/neutral/negative",
            "topics": ["Topic 1", "Topic 2", ...] (main discussion topics)
        }}
        
        Important:
        - Extract real information from the transcript
        - If something is not mentioned, use empty arrays []
        - Keep responses concise and actionable
        - Format dates as YYYY-MM-DD where possible
        """
        
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                format="json",
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_ctx": 32768,
                    "num_predict": 2048,
                    "seed": 42,  # For reproducibility
                }
            )
            
            result = json.loads(response['response'])
            
            # Add metadata
            result['generated_at'] = datetime.utcnow().isoformat()
            result['model'] = self.model
            
            # Cache the result
            if self.redis:
                cache_key = self._get_cache_key("notes", transcript)
                self.redis.setex(cache_key, self.cache_ttl, json.dumps(result))
            
            return result
            
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
        
        prompt = f"""
        Update the meeting notes with this new transcript segment.
        {context}
        
        NEW TRANSCRIPT SEGMENT:
        {new_transcript}
        
        Generate an updated JSON response with the same structure as before.
        Merge new information with existing notes intelligently:
        - Don't duplicate information
        - Update summary if significant new information
        - Add new action items, decisions, etc.
        - Keep the most relevant key points (max 10)
        
        JSON Structure:
        {{
            "summary": "Updated meeting summary",
            "keyPoints": ["Point 1", ...],
            "decisions": ["Decision 1", ...],
            "actionItems": [{{"task": "", "owner": "", "deadline": ""}}, ...],
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
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                format="json",
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_ctx": 32768,
                    "num_predict": 1536,
                }
            )
            
            result = json.loads(response['response'])
            result['lastUpdated'] = datetime.utcnow().isoformat()
            result['isIncremental'] = True
            
            return result
            
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
        
        prompt = f"""
        You are an AI assistant helping analyze a specific meeting.
        
        MEETING TRANSCRIPT:
        {transcript[:8000]}  # Limit context size
        
        {history_context}
        
        USER QUESTION: {query}
        
        Please provide a helpful, accurate response based on the meeting content.
        - Reference specific parts of the meeting when relevant
        - Be concise but thorough
        - If the information isn't in the transcript, say so
        """
        
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": 0.8,
                    "top_p": 0.9,
                    "num_ctx": 32768,
                    "num_predict": 1024,
                }
            )
            
            return response['response']
            
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
        for i, ctx in enumerate(meeting_contexts[:5], 1):  # Limit to 5 most relevant
            context_str += f"Meeting {i} ({ctx.get('date', 'Unknown date')}):\n"
            context_str += f"Summary: {ctx.get('summary', 'No summary')}\n"
            context_str += f"Relevant excerpt: {ctx.get('excerpt', '')[:500]}\n\n"
        
        prompt = f"""
        You are an intelligent assistant with access to multiple meeting records.
        Help the user by analyzing information across meetings.
        
        {context_str}
        
        USER QUESTION: {query}
        
        Provide a comprehensive response that:
        - Synthesizes information from multiple meetings
        - Identifies patterns or trends
        - References specific meetings when relevant
        - Provides actionable insights
        """
        
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": 0.8,
                    "top_p": 0.95,
                    "num_ctx": 32768,
                    "num_predict": 1536,
                }
            )
            
            return response['response']
            
        except Exception as e:
            logger.error(f"Error in global assistant: {e}")
            return "I apologize, but I'm having trouble accessing the meeting data. Please try again."
    
    async def apply_custom_vocabulary(self, 
                                     text: str, 
                                     vocabulary: List[Dict[str, str]]) -> str:
        """
        Apply custom vocabulary/acronym expansions
        
        Args:
            text: Text to process
            vocabulary: List of term mappings
            
        Returns:
            Text with vocabulary applied
        """
        prompt = f"""
        Apply the following vocabulary replacements to the text.
        Replace acronyms and terms with their full expansions where appropriate.
        Maintain natural readability - don't over-expand common terms.
        
        VOCABULARY:
        {json.dumps(vocabulary, indent=2)}
        
        TEXT:
        {text}
        
        Return ONLY the processed text with replacements applied.
        """
        
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": 0.3,  # Lower temperature for consistency
                    "top_p": 0.95,
                    "num_ctx": 16384,
                    "num_predict": len(text) * 2,  # Allow for expansion
                }
            )
            
            return response['response']
            
        except Exception as e:
            logger.error(f"Error applying vocabulary: {e}")
            return text  # Return original on error
    
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
            "generated_at": datetime.utcnow().isoformat(),
            "error": True
        }
    
    async def test_connection(self) -> bool:
        """Test connection to Ollama server"""
        try:
            models = self.client.list()
            logger.info(f"Connected to Ollama. Available models: {models}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
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
            gemma_service: Gemma service instance
            buffer_duration: Seconds to buffer before generating notes
            min_words: Minimum words before generating notes
        """
        self.gemma = gemma_service
        self.buffer_duration = buffer_duration
        self.min_words = min_words
        self.buffer = []
        self.last_generation = datetime.utcnow()
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
        time_elapsed = (datetime.utcnow() - self.last_generation).seconds
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
        self.last_generation = datetime.utcnow()
        
        return self.current_notes
    
    async def force_generation(self) -> Optional[Dict]:
        """Force notes generation regardless of buffer state"""
        if self.buffer:
            return await self.generate_notes()
        return self.current_notes