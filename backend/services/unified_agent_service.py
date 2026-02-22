"""
Unified Agent Service
Single agent that handles all meeting tasks with Granite 3.3 2B on llama.cpp Vulkan
"""
import asyncio
import json
import logging
import time
from typing import Dict, Optional, List
from datetime import datetime, timezone

import requests

from sqlalchemy.orm import Session
from database.database import get_db_session
from models.unified_agent import UnifiedMeetingAgent
from services.progressive_interval_manager import progressive_interval_manager, ProgressiveConfig

# Import AI backend configuration
try:
    from config.ai_backends import get_ai_backend, get_available_backend, check_backend_health
except ImportError:
    # Fallback if config doesn't exist yet
    def get_ai_backend(name=None):
        return {
            "url": "http://localhost:11437",
            "endpoint": "/v1/chat/completions",
            "type": "llamacpp",
            "name": "Granite 3.3 2B (llama.cpp Vulkan)",
            "model": "granite-3.3-2b-instruct",
            "timeout": 30,
            "health_check": "/health"
        }
    def get_available_backend():
        return "llamacpp", get_ai_backend()
    def check_backend_health(config):
        return True

logger = logging.getLogger(__name__)

# Constants for the single Granite 3.3 2B model
LLAMACPP_BASE_URL = "http://localhost:11437"
LLAMACPP_MODEL = "granite-3.3-2b-instruct"


class UnifiedAgentService:
    """
    Simplified service for single meeting agent
    Uses Granite 3.3 2B for all tasks via llama.cpp Vulkan
    """

    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}

        # Get AI backend configuration
        backend_name, self.ai_backend = get_available_backend()
        self.base_url = self.ai_backend["url"]
        self.model_name = self.ai_backend.get("model", LLAMACPP_MODEL)

        logger.info(f"Unified Agent Service initialized")
        logger.info(f"   Using AI backend: {self.ai_backend['name']} at {self.base_url}")

    def _extract_json_from_ai_response(self, response_text: str) -> Optional[str]:
        """
        Extract JSON from AI response that may contain extra text
        Handles markdown code blocks, prefix text, and trailing content
        """
        if not response_text:
            return None

        # Strip leading/trailing whitespace first
        cleaned = response_text.strip()

        # Remove common prefix patterns (with and without leading spaces)
        prefix_patterns = [
            "Response:", " Response:", "Here is the analysis:", "Here's the analysis:",
            "Output:", " Output:", "JSON:", " JSON:", "Result:", " Result:",
            "Analysis:", " Analysis:", "Summary:", " Summary:", "Here is the JSON:",
            "Here's the JSON:", "Returning JSON:", "Generated JSON:", "Answer:",
            "Based on the transcript:", "After analyzing:", "The meeting summary:",
            "Here is the summary:", "Here's the summary:", "Meeting analysis:",
            "Solution 1:", "Solution:", "<|end|>", " <|end|>",
        ]

        for pattern in prefix_patterns:
            if pattern.lower() in cleaned.lower():
                idx = cleaned.lower().find(pattern.lower())
                cleaned = cleaned[idx + len(pattern):].strip()
                break

        # Handle markdown code blocks
        if '```json' in cleaned:
            start = cleaned.find('```json') + 7
            end = cleaned.find('```', start)
            if end > start:
                return cleaned[start:end].strip()
        elif '```' in cleaned:
            start = cleaned.find('```') + 3
            end = cleaned.find('```', start)
            if end > start:
                potential = cleaned[start:end].strip()
                if potential.startswith(('json', 'JSON')):
                    potential = potential[4:].strip()
                if potential.startswith('{'):
                    return potential

        # Extract raw JSON using brace matching
        json_start = cleaned.find('{')
        if json_start >= 0:
            brace_count = 0
            for i in range(json_start, len(cleaned)):
                if cleaned[i] == '{':
                    brace_count += 1
                elif cleaned[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_candidate = cleaned[json_start:i+1]
                        if '"executive"' in json_candidate or '"bullets"' in json_candidate:
                            return json_candidate

            # If we couldn't find a complete JSON object, try to find just the opening
            remaining = cleaned[json_start:]
            if remaining.count('{') > remaining.count('}'):
                for end_marker in ['\n\n', 'Solution', '<|end|>', 'QUESTION:', 'ANSWER:']:
                    if end_marker in remaining:
                        partial = remaining[:remaining.find(end_marker)]
                        open_braces = partial.count('{')
                        close_braces = partial.count('}')
                        if open_braces > close_braces:
                            partial += '}' * (open_braces - close_braces)
                        return partial

        return None

    async def _call_llm(self, prompt: str, max_tokens: int = 500, temperature: float = 0.7,
                        system_prompt: str = "You are a meeting assistant.", timeout: int = 30) -> Optional[str]:
        """
        Call Granite 3.3 2B via OpenAI-compatible chat completions API
        Single unified method for all LLM calls
        """
        try:
            url = f"{self.base_url}/v1/chat/completions"

            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }

            start_time = time.time()
            response = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                timeout=timeout
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                inference_time = time.time() - start_time
                tokens_generated = len(content.split()) if content else 0
                tokens_per_sec = tokens_generated / inference_time if inference_time > 0 else 0
                logger.info(f"Granite 3.3 2B inference: {inference_time:.1f}s ({tokens_per_sec:.1f} tokens/sec)")
                return content.strip()
            else:
                logger.error(f"llama.cpp API error: {response.status_code}")
                return None

        except asyncio.TimeoutError:
            logger.error("llama.cpp request timed out")
            return None
        except Exception as e:
            logger.error(f"llama.cpp call failed: {e}")
            return None

    async def start_meeting_analysis(self, session_id: str, websocket_callback=None) -> bool:
        """Start progressive meeting analysis for a session"""
        if session_id in self.active_sessions:
            logger.warning(f"Meeting analysis already active for session {session_id}")
            return False

        try:
            db_session = get_db_session()

            # Get or create default agent
            agent = UnifiedMeetingAgent.get_default_agent(db_session)
            if not agent:
                agent = UnifiedMeetingAgent.create_default_agent(db_session)

            # Parse progressive config
            config = ProgressiveConfig.from_dict(agent.progressive_config)

            # Initialize progressive intervals
            progressive_interval_manager.initialize_session(session_id, str(agent.id), config)

            # Store session info
            session_info = {
                'session_id': session_id,
                'agent': agent,
                'config': config,
                'websocket_callback': websocket_callback,
                'started_at': datetime.now(timezone.utc),
                'summary_count': 0
            }

            self.active_sessions[session_id] = session_info

            # Start monitoring task
            task = asyncio.create_task(self._monitoring_loop(session_id))
            self.monitoring_tasks[session_id] = task

            logger.info(f"Started meeting analysis for session {session_id}")
            logger.info(f"  Agent: {agent.name}")
            logger.info(f"  Model: {self.model_name}")
            logger.info(f"  Initial interval: {config.initial_word_count} words")

            return True

        except Exception as e:
            logger.error(f"Failed to start meeting analysis: {e}")
            return False
        finally:
            if db_session:
                db_session.close()

    async def stop_meeting_analysis(self, session_id: str) -> Optional[Dict]:
        """Stop meeting analysis and generate final summary"""
        if session_id not in self.active_sessions:
            return None

        try:
            session_info = self.active_sessions[session_id]

            # Cancel monitoring task
            if session_id in self.monitoring_tasks:
                task = self.monitoring_tasks[session_id]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del self.monitoring_tasks[session_id]

            # Generate final comprehensive summary
            final_summary = await self._generate_final_summary(session_id)

            # Generate meeting title
            meeting_title = await self._generate_meeting_title(session_id)

            # Clean up
            del self.active_sessions[session_id]
            progressive_interval_manager.cleanup_session(session_id)

            logger.info(f"Stopped meeting analysis for session {session_id}")
            logger.info(f"  Generated {session_info.get('summary_count', 0)} progressive summaries")
            if meeting_title:
                logger.info(f"  Suggested title: {meeting_title}")

            return {
                "final_summary": final_summary,
                "meeting_title": meeting_title,
                "summary_count": session_info.get('summary_count', 0)
            }

        except Exception as e:
            logger.error(f"Error stopping meeting analysis: {e}")
            return None

    async def _monitoring_loop(self, session_id: str):
        """Main monitoring loop for progressive analysis"""
        session_info = self.active_sessions[session_id]
        agent = session_info['agent']
        config = session_info['config']

        try:
            while session_id in self.active_sessions:
                # Get current word count
                current_word_count = await self._get_session_word_count(session_id)

                # Check if we should generate a summary
                should_generate, interval_info = progressive_interval_manager.should_generate_summary(
                    session_id, str(agent.id), current_word_count, config
                )

                if should_generate:
                    await self._generate_progressive_summary(session_id, interval_info)

                # Check every 5 seconds
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info(f"Monitoring cancelled for session {session_id}")
            raise
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")

    async def _get_session_word_count(self, session_id: str) -> int:
        """Get current word count for a session"""
        try:
            # Try WebSocket registry first
            try:
                from api.websocket_auto_summary import session_word_counts
                if session_id in session_word_counts:
                    return session_word_counts[session_id]
            except ImportError:
                pass

            # Fallback to live transcription buffer
            try:
                from services.live_recording_transcription import live_recording_transcription
                if hasattr(live_recording_transcription, 'transcript_buffer') and live_recording_transcription.transcript_buffer:
                    if live_recording_transcription.session_id == session_id:
                        total = sum(len(seg.get('text', '').split()) for seg in live_recording_transcription.transcript_buffer)
                        return total
            except Exception:
                pass

            return 0

        except Exception as e:
            logger.debug(f"Could not get word count for session {session_id}: {e}")
            return 0

    async def _generate_progressive_summary(self, session_id: str, interval_info: Dict):
        """Generate progressive plain text summary using Granite 3.3 2B"""
        session_info = self.active_sessions[session_id]
        agent = session_info['agent']

        start_time = time.time()

        try:
            # Get transcript
            transcript = await self._get_session_transcript(session_id)

            if not transcript or len(transcript.split()) < 10:
                logger.debug(f"Not enough content for summary (session {session_id})")
                return

            # Generate plain text summary
            summary_text = await self._generate_text_summary(transcript, interval_info)

            if not summary_text:
                logger.warning(f"Failed to generate progressive summary for session {session_id}")
                return

            processing_time = int((time.time() - start_time) * 1000)
            session_info['summary_count'] += 1

            # Save progressive summary to database (as plain text)
            await self._save_progressive_text_summary_to_db(
                session_id, interval_info, summary_text, processing_time
            )

            # Send via WebSocket - always broadcast for database-backed sessions
            websocket_callback = session_info.get('websocket_callback')
            if websocket_callback:
                await self._send_text_summary_update(session_id, session_info, interval_info, summary_text, processing_time)
            else:
                # Direct broadcast for database-backed sessions
                summary_message = {
                    "type": "progressive_summary",
                    "session_id": session_id,
                    "agent": {
                        "id": str(session_info['agent'].id),
                        "name": session_info['agent'].name,
                        "role": "unified"
                    },
                    "summary_data": {
                        "text": summary_text,
                        "word_count": interval_info['current_word_count'],
                        "interval_used": interval_info['current_interval'],
                        "next_interval": interval_info.get('next_interval', interval_info['current_interval']),
                        "model": self.model_name,
                        "processing_time_ms": processing_time
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                # Try to broadcast to /ws/transcription-auto/{session_id} connections
                from api.websocket_auto_summary import broadcast_progressive_summary
                await broadcast_progressive_summary(session_id, summary_message)

                # Also broadcast to /ws/transcription/{session_id} connections
                try:
                    from api.websocket_transcription import manager as transcription_manager
                    await transcription_manager.broadcast_transcription(session_id, summary_message)
                    logger.info(f"Broadcast progressive summary to transcription WebSocket for {session_id}")
                except Exception as e:
                    logger.debug(f"Could not broadcast to transcription WebSocket: {e}")

            logger.info(f"Generated progressive summary for session {session_id}")
            logger.info(f"  Word count: {interval_info['current_word_count']}")
            logger.info(f"  Interval: {interval_info['current_interval']} words")
            logger.info(f"  Processing time: {processing_time}ms")

        except Exception as e:
            logger.error(f"Error generating progressive summary: {e}")

    async def _generate_text_summary(self, transcript: str, interval_info: Dict) -> Optional[str]:
        """Generate a plain text summary for progressive updates"""
        # Truncate transcript if too long for real-time processing
        if len(transcript) > 2000:
            transcript = transcript[:2000] + "..."

        prompt = f"""Below is a meeting transcript. Write a 2-3 sentence summary of the key points.

Meeting transcript:
{transcript}

Brief summary:"""

        result = await self._call_llm(
            prompt=prompt,
            max_tokens=150,
            temperature=0.7,
            system_prompt="You are a fast meeting summarizer. Provide brief, clear summaries.",
            timeout=10
        )

        if not result:
            return None

        # Clean up the response
        cleaned_result = result.strip()

        if cleaned_result.lower().startswith("summary:"):
            cleaned_result = cleaned_result[8:].strip()

        # Remove common instruction artifacts from small models
        if "[Your answer should be" in cleaned_result:
            parts = cleaned_result.split("]")
            if len(parts) > 1:
                cleaned_result = parts[1].strip()

        if "**Final Answer**" in cleaned_result or "Final Answer:" in cleaned_result:
            cleaned_result = cleaned_result.split("**Final Answer**")[0].strip()
            cleaned_result = cleaned_result.split("Final Answer:")[0].strip()

        cleaned_result = cleaned_result.replace("**", "")

        # Limit length for real-time display
        if len(cleaned_result) > 300:
            sentences = cleaned_result.split('. ')
            cleaned_result = '. '.join(sentences[:3])
            if not cleaned_result.endswith('.'):
                cleaned_result += '.'

        if cleaned_result:
            logger.info(f"Generated progressive text summary: {cleaned_result[:80]}...")
            return cleaned_result

        return None

    async def _get_progressive_summaries(self, session_id: str) -> List[Dict]:
        """Get progressive summaries for a session to provide context for final summary"""
        try:
            from database.database import get_db_session
            from database.models import RecordingSession

            db = get_db_session()
            session = db.query(RecordingSession).filter(
                RecordingSession.session_id == session_id
            ).first()

            if session and session.progressive_summaries:
                return session.progressive_summaries
            else:
                return []

        except Exception as e:
            logger.error(f"Error getting progressive summaries: {e}")
            return []
        finally:
            if db:
                db.close()

    async def _get_session_transcript(self, session_id: str) -> str:
        """Get current transcript for a session"""
        try:
            # First try to get from live recording transcription buffer
            from services.live_recording_transcription import live_recording_transcription
            if hasattr(live_recording_transcription, 'transcript_buffer') and live_recording_transcription.transcript_buffer:
                if live_recording_transcription.session_id == session_id:
                    transcript_text = ' '.join(
                        segment.get('text', '') for segment in live_recording_transcription.transcript_buffer
                    )
                    if transcript_text:
                        logger.debug(f"Got transcript from live buffer: {len(transcript_text.split())} words")
                        return transcript_text

            # Try from database
            from database.database import get_db_session
            from database.models import RecordingSession
            db = get_db_session()
            try:
                session = db.query(RecordingSession).filter_by(session_id=session_id).first()
                if session and session.transcript:
                    return session.transcript
            finally:
                db.close()

            return ""

        except Exception as e:
            logger.error(f"Error getting transcript for session {session_id}: {e}")
            return ""

    async def _generate_final_summary(self, session_id: str) -> Optional[Dict]:
        """Generate comprehensive final summary using Granite 3.3 2B"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return None

        transcript = await self._get_session_transcript(session_id)

        if not transcript:
            return None

        # Get progressive summaries to provide additional context
        progressive_summaries = await self._get_progressive_summaries(session_id)
        progressive_context = ""
        if progressive_summaries:
            progressive_context = "\n\nPROGRESSIVE SUMMARIES DURING MEETING:\n"
            for i, summary in enumerate(progressive_summaries, 1):
                progressive_context += f"{i}. {summary.get('text', '')}\n"

        final_prompt = f"""TRANSCRIPT:
{transcript}
{progressive_context}

Provide JSON analysis:

{{
    "executive": "2-3 sentence summary",
    "bullets": ["key point 1", "key point 2"],
    "actions": [{{"action": "task", "owner": "person", "priority": "high"}}],
    "decisions": ["decision 1"],
    "title": "Meeting Title"
}}"""

        try:
            result = await self._call_llm(
                prompt=final_prompt,
                max_tokens=600,
                temperature=0.3,
                system_prompt="You are a meeting analyst. Provide comprehensive meeting analysis in valid JSON format.",
                timeout=90
            )

            if result:
                logger.info(f"Final summary generated using {self.model_name}")
                try:
                    json_str = self._extract_json_from_ai_response(result)
                    if json_str:
                        parsed_result = json.loads(json_str)
                        logger.info(f"Comprehensive final summary generated with {len(parsed_result.get('bullets', []))} key points")
                        return parsed_result
                    else:
                        raise json.JSONDecodeError("No JSON found", result, 0)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse final summary JSON, using fallback format")
                    return {
                        "executive": "Final summary generation completed. Please review the transcript for details.",
                        "bullets": [
                            "Meeting concluded successfully",
                            f"Total transcript length: {len(transcript.split())} words",
                            "Summary processing complete"
                        ],
                        "actions": [],
                        "decisions": [],
                        "title": f"Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    }

        except Exception as e:
            logger.error(f"Error generating final summary: {e}")

        return None

    async def _generate_meeting_title(self, session_id: str) -> Optional[str]:
        """Generate meeting title from transcript"""
        transcript = await self._get_session_transcript(session_id)
        if not transcript:
            return None

        title_prompt = f"""Based on this meeting transcript, generate a concise, descriptive meeting title (4-8 words):

{transcript[:1000]}...

Title should capture the main purpose/topic. Examples:
- "Q4 Budget Planning Review"
- "Product Launch Strategy Meeting"
- "Weekly Team Standup"

RESPOND WITH ONLY THE TITLE:"""

        try:
            result = await self._call_llm(
                prompt=title_prompt,
                max_tokens=20,
                temperature=0.3,
                system_prompt="You generate concise meeting titles. Respond with ONLY the title.",
                timeout=15
            )

            if result:
                title = result.replace('"', '').replace('\n', ' ').strip()
                return title[:100] if title else None

        except Exception as e:
            logger.error(f"Error generating meeting title: {e}")

        return None

    async def analyze_meeting(self, session_id: str, transcript: str) -> Dict:
        """
        Analyze a meeting transcript - with timeout protection
        Consolidates both analysis paths into one method
        """
        try:
            # Truncate very long transcripts to avoid timeout
            if len(transcript) > 5000:
                transcript = transcript[:5000] + "... [truncated for processing]"

            db_session = get_db_session()

            # Get or create default agent
            agent = UnifiedMeetingAgent.get_default_agent(db_session)
            if not agent:
                agent = UnifiedMeetingAgent.create_default_agent(db_session)

            # Simplified prompt
            prompt = f"""Analyze this meeting transcript and provide a brief summary:

TRANSCRIPT:
{transcript}

Provide:
1. Brief summary (2-3 sentences)
2. Key points (3-5 bullets)
3. Action items with owners
4. Important decisions
5. Suggested title

RESPOND WITH JSON:
{{
    "executive": "Brief summary of the meeting",
    "bullets": ["Key point 1", "Key point 2", "Key point 3"],
    "actions": [{{"action": "Task", "owner": "Person", "priority": "high"}}],
    "decisions": ["Decision 1"],
    "title": "Meeting title"
}}"""

            try:
                result = await self._call_llm(
                    prompt=prompt,
                    max_tokens=500,
                    temperature=0.7,
                    system_prompt="You are a meeting analyst. Provide meeting analysis in valid JSON format.",
                    timeout=120
                )

                if result:
                    json_str = self._extract_json_from_ai_response(result)
                    if json_str:
                        try:
                            analysis_result = json.loads(json_str)
                            logger.info(f"Meeting analysis completed using {self.model_name}")
                            return {
                                "success": True,
                                "analysis": analysis_result,
                                "agent_id": str(agent.id)
                            }
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse extracted JSON: {e}")
                    else:
                        logger.warning("No JSON found in AI response")

                # Fallback to basic analysis
                return await self._create_fallback_analysis(session_id, transcript)

            except asyncio.TimeoutError:
                logger.error(f"AI analysis timed out for session {session_id}")
                return await self._create_fallback_analysis(session_id, transcript)

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return await self._create_fallback_analysis(session_id, transcript)
        finally:
            if db_session:
                db_session.close()

    async def _send_text_summary_update(self, session_id: str, session_info: Dict, interval_info: Dict, summary_text: str, processing_time: int):
        """Send plain text summary update via WebSocket"""
        try:
            agent = session_info['agent']
            websocket_callback = session_info['websocket_callback']

            message = {
                "type": "progressive_summary",
                "session_id": session_id,
                "agent": {
                    "id": str(agent.id),
                    "name": agent.name,
                    "role": "unified"
                },
                "summary_data": {
                    "text": summary_text,
                    "word_count": interval_info['current_word_count'],
                    "interval_used": interval_info['current_interval'],
                    "next_interval": interval_info.get('next_interval', interval_info['current_interval']),
                    "model": self.model_name,
                    "processing_time_ms": processing_time
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            await websocket_callback(message)
            logger.info(f"Sent text summary update via WebSocket for session {session_id}")

        except Exception as e:
            logger.error(f"Error sending text summary update: {e}")

    async def _send_summary_update(self, session_id: str, session_info: Dict, interval_info: Dict, summary: Dict, processing_time: int):
        """Send summary update via WebSocket (for structured summaries)"""
        try:
            agent = session_info['agent']
            websocket_callback = session_info['websocket_callback']

            message = {
                "type": "progressive_summary",
                "session_id": session_id,
                "agent": {
                    "id": str(agent.id),
                    "name": agent.name,
                    "role": "unified"
                },
                "summary_data": {
                    "word_count_at_summary": interval_info['current_word_count'],
                    "interval_used": interval_info['current_interval'],
                    "next_interval": interval_info.get('next_interval', interval_info['current_interval']),
                    "model_size": self.model_name,
                    "sections": summary
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            await websocket_callback(message)

        except Exception as e:
            logger.error(f"Error sending summary update: {e}")

    async def _save_progressive_text_summary_to_db(self, session_id: str, interval_info: Dict, summary_text: str, processing_time: int):
        """Save progressive plain text summary to database"""
        try:
            from database.database import get_db_session
            from database.models import RecordingSession

            db = get_db_session()

            # Find session by session_id
            session = db.query(RecordingSession).filter(
                RecordingSession.session_id == session_id
            ).first()

            if not session:
                logger.warning(f"Session {session_id} not found in database for progressive summary save")
                return

            # Create progressive summary entry (plain text format)
            progressive_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "word_count_at_summary": interval_info.get('current_word_count', 0),
                "interval_used": interval_info.get('current_interval', 500),
                "processing_time_ms": processing_time,
                "text": summary_text,
                "model": self.model_name
            }

            # Get existing progressive summaries or initialize empty list
            if session.progressive_summaries:
                summaries = session.progressive_summaries if isinstance(session.progressive_summaries, list) else []
            else:
                summaries = []

            # Append new summary
            summaries.append(progressive_entry)

            # Update session
            session.progressive_summaries = summaries

            # Also update processing_metadata with latest stats
            metadata = session.processing_metadata or {}
            metadata.update({
                "last_progressive_summary": datetime.now(timezone.utc).isoformat(),
                "total_progressive_summaries": len(summaries),
                "current_word_count": interval_info.get('current_word_count', 0),
                "model_used": self.model_name
            })
            session.processing_metadata = metadata

            db.commit()
            logger.info(f"Saved progressive text summary #{len(summaries)} to database for session {session_id}")

        except Exception as e:
            logger.error(f"Failed to save progressive summary to database: {e}")
        finally:
            if db:
                db.close()

    async def _create_fallback_analysis(self, session_id: str, transcript: str) -> Dict:
        """Create basic fallback analysis when AI fails"""
        word_count = len(transcript.split())
        duration_estimate = word_count / 150  # Approximate minutes

        # Extract first few sentences for summary
        sentences = transcript.split('. ')[:3]
        brief_text = '. '.join(sentences)[:200] + "..."

        fallback_analysis = {
            "executive": f"Meeting recorded with {word_count} words transcribed. {brief_text}",
            "bullets": [
                f"Meeting duration: approximately {duration_estimate:.1f} minutes",
                f"Total words transcribed: {word_count}",
                "Meeting content captured successfully",
                "AI analysis temporarily unavailable"
            ],
            "actions": [],
            "decisions": [],
            "title": f"Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        }

        return {
            "success": True,  # Mark as success even with fallback
            "analysis": fallback_analysis,
            "agent_id": "fallback",
            "fallback": True
        }

    def get_agent_status(self) -> Dict:
        """Get current agent configuration"""
        try:
            db_session = get_db_session()
            agent = UnifiedMeetingAgent.get_default_agent(db_session)

            if agent:
                return {
                    "agent": agent.to_dict(),
                    "active_sessions": len(self.active_sessions),
                    "model_ready": True
                }
            else:
                return {
                    "agent": None,
                    "active_sessions": 0,
                    "model_ready": False
                }
        except Exception as e:
            logger.error(f"Error getting agent status: {e}")
            return {"error": str(e)}
        finally:
            if db_session:
                db_session.close()

# Global instance
unified_agent_service = UnifiedAgentService()
