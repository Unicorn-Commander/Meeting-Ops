"""
Unified Agent Service
Single agent that handles all meeting tasks with granite3.3:8b
"""
import asyncio
import json
import logging
import time
from typing import Dict, Optional, List
from datetime import datetime

from sqlalchemy.orm import Session
from database.database import get_db_session
from models.unified_agent import UnifiedMeetingAgent
from services.progressive_interval_manager import progressive_interval_manager, ProgressiveConfig

# Import AI backend configuration - Dual model support
try:
    from config.dual_ai_backends import get_live_summary_backend, get_final_summary_backend, get_backend_for_task
    dual_model_support = True
except ImportError:
    try:
        from config.ai_backends import get_ai_backend, get_available_backend, check_backend_health
        dual_model_support = False
    except ImportError:
        # Fallback if config doesn't exist yet
        def get_ai_backend(name=None):
            return {
                "url": "http://localhost:11437",
                "endpoint": "/completion",
                "type": "llamacpp",
                "name": "GPU-Accelerated LLaMA.cpp"
            }
        def get_available_backend():
            return "llamacpp", get_ai_backend()
        def check_backend_health(config):
            return True
        dual_model_support = False

logger = logging.getLogger(__name__)

class UnifiedAgentService:
    """
    Simplified service for single meeting agent
    Uses granite3.3:8b for all tasks with GPU acceleration
    """
    
    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        
        # Get AI backend configuration - Use dual model if available
        global dual_model_support
        if dual_model_support:
            # Use Phi-4 for live summaries by default
            backend_name, self.ai_backend = get_live_summary_backend()
            self.base_url = self.ai_backend["url"]
            self.endpoint_path = self.ai_backend["endpoint"]
            self.backend_type = self.ai_backend["type"]
            logger.info("🎯 Dual-model mode: Phi-4 for live, Granite for final summaries")
        else:
            backend_name, self.ai_backend = get_available_backend()
            self.base_url = self.ai_backend["url"]
            self.endpoint_path = self.ai_backend["endpoint"]
            self.backend_type = self.ai_backend["type"]
        
        logger.info(f"🚀 Unified Agent Service initialized")
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
                        # Basic validation - check if it looks like valid JSON
                        if '"executive"' in json_candidate or '"bullets"' in json_candidate:
                            return json_candidate
            
            # If we couldn't find a complete JSON object, try to find just the opening
            # and see if we can construct something useful
            remaining = cleaned[json_start:]
            if remaining.count('{') > remaining.count('}'):
                # Incomplete JSON - try to find a reasonable stopping point
                for end_marker in ['\n\n', 'Solution', '<|end|>', 'QUESTION:', 'ANSWER:']:
                    if end_marker in remaining:
                        partial = remaining[:remaining.find(end_marker)]
                        # Add missing closing braces if needed
                        open_braces = partial.count('{')
                        close_braces = partial.count('}')
                        if open_braces > close_braces:
                            partial += '}' * (open_braces - close_braces)
                        return partial
        
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
                'started_at': datetime.utcnow(),
                'summary_count': 0
            }
            
            self.active_sessions[session_id] = session_info
            
            # Start monitoring task
            task = asyncio.create_task(self._monitoring_loop(session_id))
            self.monitoring_tasks[session_id] = task
            
            logger.info(f"Started meeting analysis for session {session_id}")
            logger.info(f"  Agent: {agent.name}")
            logger.info(f"  Model: {agent.model_name}")
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
            
            # Fallback to session storage
            from api.simple_recording_fixed import sessions
            if session_id in sessions:
                session = sessions[session_id]
                transcript = session.get('transcript', '') or ''
                return len(transcript.split())
            
            return 0
            
        except Exception as e:
            logger.error(f"Error getting word count for session {session_id}: {e}")
            return 0
    
    async def _generate_progressive_summary(self, session_id: str, interval_info: Dict):
        """Generate progressive plain text summary using Phi-4 Mini for speed"""
        session_info = self.active_sessions[session_id]
        agent = session_info['agent']
        
        start_time = time.time()
        
        try:
            # Get transcript
            transcript = await self._get_session_transcript(session_id)
            
            if not transcript or len(transcript.split()) < 10:
                logger.debug(f"Not enough content for summary (session {session_id})")
                return
            
            # Generate plain text summary using Phi-4 Mini for speed
            summary_text = await self._call_phi4_for_text_summary(transcript, interval_info)
            
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
                # NEW FORMAT: Plain text instead of structured JSON
                summary_message = {
                    "type": "progressive_summary",
                    "session_id": session_id,
                    "agent": {
                        "id": str(session_info['agent'].id),
                        "name": session_info['agent'].name,
                        "role": "unified"
                    },
                    "summary_data": {
                        "text": summary_text,  # Plain text summary
                        "word_count": interval_info['current_word_count'],
                        "interval_used": interval_info['current_interval'],
                        "next_interval": interval_info.get('next_interval', interval_info['current_interval']),
                        "model": "phi-4-mini",
                        "processing_time_ms": processing_time
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Try to broadcast to /ws/transcription-auto/{session_id} connections
                from api.websocket_auto_summary import broadcast_progressive_summary
                await broadcast_progressive_summary(session_id, summary_message)
                
                # Also broadcast to /ws/transcription/{session_id} connections
                try:
                    from api.websocket_transcription import manager as transcription_manager
                    await transcription_manager.broadcast_transcription(session_id, summary_message)
                    logger.info(f"✅ Broadcast progressive summary to transcription WebSocket for {session_id}")
                except Exception as e:
                    logger.debug(f"Could not broadcast to transcription WebSocket: {e}")
            
            logger.info(f"Generated progressive summary for session {session_id}")
            logger.info(f"  Word count: {interval_info['current_word_count']}")
            logger.info(f"  Interval: {interval_info['current_interval']} words")
            logger.info(f"  Processing time: {processing_time}ms")
            
        except Exception as e:
            logger.error(f"Error generating progressive summary: {e}")
    
    async def _call_phi4_for_text_summary(self, transcript: str, interval_info: Dict) -> Optional[str]:
        """Call fast model for real-time summary generation
        Now uses the ultra-fast Qwen3-0.6B model from our agent configuration
        """
        try:
            import requests
            from database.database import SessionLocal
            from models.agent_system import MeetingAgent
            
            # Get the live summary agent from database
            db = SessionLocal()
            try:
                live_agent = db.query(MeetingAgent).filter_by(
                    slug="core-live-summary", 
                    is_active=True
                ).first()
                
                if live_agent:
                    # Use agent configuration
                    url = f"{live_agent.model_endpoint}/completion"
                    system_prompt = live_agent.system_prompt
                    logger.info(f"Using {live_agent.name} ({live_agent.model_name}) at {url}")
                else:
                    # Fallback to Qwen3-0.6B default
                    url = "http://localhost:11440/completion"
                    system_prompt = "You are a fast meeting summarizer. Provide brief, clear summaries."
                    logger.info("Using fallback Qwen3-0.6B at port 11440")
            finally:
                db.close()
            
            # Create a clear instruction-following prompt
            # Truncate transcript if too long for real-time processing
            if len(transcript) > 2000:
                transcript = transcript[:2000] + "..."
            
            prompt = f"""Below is a meeting transcript. Write a 2-3 sentence summary of the key points.

Meeting transcript:
{transcript}

Brief summary:"""

            payload = {
                "prompt": prompt,
                "n_predict": 150,  # Shorter for quick summaries
                "stream": False,
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40
            }
            
            start_time = time.time()
            response = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                timeout=10  # Fast timeout for real-time use
            )
            
            if response.status_code == 200:
                result = response.json().get("content", "")
                
                # Log performance metrics
                inference_time = time.time() - start_time
                tokens_generated = len(result.split()) if result else 0
                tokens_per_sec = tokens_generated / inference_time if inference_time > 0 else 0
                logger.info(f"⚡ Live Summary Model: {inference_time:.1f}s ({tokens_per_sec:.1f} tokens/sec)")
                
                # Clean up the response - remove prompt echoes and extra text
                cleaned_result = result.strip()
                
                # Remove common prompt echoes and instruction artifacts
                if cleaned_result.lower().startswith("summary:"):
                    cleaned_result = cleaned_result[8:].strip()
                
                # Remove common instruction artifacts from small models
                if "[Your answer should be" in cleaned_result:
                    # Extract the actual summary after the instruction
                    parts = cleaned_result.split("]")
                    if len(parts) > 1:
                        cleaned_result = parts[1].strip()
                
                # Remove "Final Answer" artifacts
                if "**Final Answer**" in cleaned_result or "Final Answer:" in cleaned_result:
                    # Take everything before "Final Answer"
                    cleaned_result = cleaned_result.split("**Final Answer**")[0].strip()
                    cleaned_result = cleaned_result.split("Final Answer:")[0].strip()
                
                # Clean up any remaining markdown
                cleaned_result = cleaned_result.replace("**", "")
                
                # Limit length for real-time display
                if len(cleaned_result) > 300:
                    sentences = cleaned_result.split('. ')
                    cleaned_result = '. '.join(sentences[:3])
                    if not cleaned_result.endswith('.'):
                        cleaned_result += '.'
                
                if cleaned_result:
                    logger.info(f"✅ Generated progressive text summary: {cleaned_result[:80]}...")
                    return cleaned_result
                else:
                    logger.warning("Live model returned empty summary")
                    return None
            else:
                logger.error(f"Live Summary Model API error: {response.status_code}")
                logger.error(f"Response: {response.text[:500] if response.text else 'No response text'}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling Live Summary Model: {e}")
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
                    # Get text from buffered segments
                    transcript_text = ' '.join(
                        segment.get('text', '') for segment in live_recording_transcription.transcript_buffer
                    )
                    if transcript_text:
                        logger.debug(f"Got transcript from live buffer: {len(transcript_text.split())} words")
                        return transcript_text
            
            # Fallback to session storage
            try:
                from api.simple_recording_fixed import sessions
                if session_id in sessions:
                    session = sessions[session_id]
                    
                    if 'transcript' in session and session['transcript']:
                        return session['transcript']
                    
                    if 'transcription_segments' in session and session['transcription_segments']:
                        segments = session['transcription_segments']
                        return ' '.join(segment.get('text', '') for segment in segments)
            except ImportError:
                pass
            
            # Try from database as last resort
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
    
    async def _call_granite_model(self, transcript: str, agent: UnifiedMeetingAgent, interval_info: Dict) -> Optional[Dict]:
        """Call granite3.3:8b model for summary generation"""
        try:
            import requests
            
            # Build prompt using agent's system prompt
            prompt = f"""{agent.system_prompt}

MEETING PROGRESS:
- Words transcribed: {interval_info['current_word_count']}
- Progressive summary #{interval_info['total_summaries'] + 1}
- Analysis interval: {interval_info['current_interval']} words

TRANSCRIPT:
{transcript}

RESPOND WITH JSON:
{{
    "executive": "Brief 2-3 sentence summary",
    "bullets": ["Key point 1", "Key point 2", "Key point 3"],
    "actions": [{{"action": "Task description", "owner": "Person if mentioned", "priority": "high/medium/low"}}],
    "decisions": ["Important decision 1", "Decision 2"],
    "title": "Suggested meeting title"
}}"""

            # Call AI backend with proper configuration
            url = f"{self.base_url}{self.endpoint_path}"
            
            # Build payload based on backend type
            if self.backend_type == "llamacpp":
                payload = {
                    "prompt": prompt,
                    "n_predict": 800,  # Increase to get complete responses
                    "stream": False,
                    "temperature": agent.model_settings.get("temperature", 0.7),
                    "top_p": agent.model_settings.get("top_p", 0.9),
                    "top_k": agent.model_settings.get("top_k", 40)
                }
                response_key = "content"
            else:  # ollama backend
                payload = {
                    "model": agent.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": agent.model_settings.get("temperature", 0.7),
                        "num_predict": 500,
                        "top_p": agent.model_settings.get("top_p", 0.9),
                        "top_k": agent.model_settings.get("top_k", 40)
                    }
                }
                response_key = "response"
            
            start_time = time.time()
            response = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                timeout=self.ai_backend.get("timeout", 30)
            )
            
            if response.status_code == 200:
                # Get result based on backend type
                result = response.json().get(response_key, "")
                
                # Log performance metrics
                inference_time = time.time() - start_time
                tokens_generated = len(result.split()) if result else 0
                tokens_per_sec = tokens_generated / inference_time if inference_time > 0 else 0
                logger.info(f"⚡ {self.backend_type.upper()} inference completed in {inference_time:.1f}s ({tokens_per_sec:.1f} tokens/sec)")
                
                # Log raw response for debugging
                logger.info(f"Raw AI response (first 500 chars): {result[:500] if result else 'EMPTY'}")
                
                try:
                    # Use helper to extract JSON from AI response
                    json_str = self._extract_json_from_ai_response(result)
                    
                    if json_str:
                        logger.info(f"Extracted JSON string: {json_str[:200]}...")
                        parsed = json.loads(json_str)
                        
                        # Validate it has expected structure
                        if isinstance(parsed, dict):
                            logger.info(f"✅ Successfully parsed AI summary with {len(parsed.get('bullets', []))} bullet points")
                            if parsed.get('executive'):
                                logger.info(f"   Executive summary: {parsed['executive'][:100]}...")
                            if parsed.get('title'):
                                logger.info(f"   Title: {parsed['title']}")
                            return parsed
                        else:
                            logger.warning(f"Result is not a dict: {type(parsed)}")
                            raise json.JSONDecodeError("Not a dict", result, 0)
                    else:
                        logger.warning(f"No JSON found in response. Response starts with: {result[:100]}")
                        logger.warning(f"Full response for debugging: {result[:500]}")
                        raise json.JSONDecodeError("No JSON markers", result, 0)
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from model response: {e}")
                    logger.info(f"Response was: {result[:200]}...")
                    # Fallback structured response
                    return {
                        "executive": f"Meeting in progress with {interval_info['current_word_count']} words transcribed.",
                        "bullets": [
                            "Meeting is being actively recorded",
                            f"Current word count: {interval_info['current_word_count']}",
                            "Progressive analysis in progress"
                        ],
                        "actions": [],
                        "decisions": [],
                        "title": "Meeting in Progress"
                    }
            else:
                logger.error(f"Granite model error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling granite model: {e}")
            return None
    
    async def _generate_final_summary(self, session_id: str) -> Optional[Dict]:
        """Generate comprehensive final summary using Granite 3.3 8B for best quality"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return None
        
        agent = session_info['agent']
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
        
        # Use Granite 3.3 8B (port 11438) for comprehensive analysis
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
            import requests
            
            # Use Granite 3.3 8B (port 11438) for final comprehensive analysis
            url = "http://localhost:11438/completion"
            
            payload = {
                "prompt": final_prompt,
                "n_predict": 600,  # Shorter but focused
                "stream": False,
                "temperature": 0.3,  # Lower temperature for better structure
                "top_p": 0.9,
                "top_k": 40
            }
            
            start_time = time.time()
            response = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                timeout=90  # Longer timeout for final comprehensive summary
            )
            
            if response.status_code == 200:
                result = response.json().get("content", "")
                inference_time = time.time() - start_time
                logger.info(f"⚡ Final summary generated in {inference_time:.1f}s using Granite 3.3 8B")
                
                try:
                    # Use helper to extract JSON from AI response
                    json_str = self._extract_json_from_ai_response(result)
                    if json_str:
                        parsed_result = json.loads(json_str)
                        logger.info(f"✅ Comprehensive final summary generated with {len(parsed_result.get('bullets', []))} key points")
                        return parsed_result
                    else:
                        raise json.JSONDecodeError("No JSON found", result, 0)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse final summary JSON, using fallback format")
                    # Create structured fallback response
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
            # Ensure we switch back even on error
            if dual_model_support:
                self.base_url = original_url
        
        return None
    
    async def _generate_meeting_title(self, session_id: str) -> Optional[str]:
        """Generate meeting title from transcript"""
        transcript = await self._get_session_transcript(session_id)
        if not transcript:
            return None
        
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return None
        
        agent = session_info['agent']
        
        title_prompt = f"""Based on this meeting transcript, generate a concise, descriptive meeting title (4-8 words):

{transcript[:1000]}...

Title should capture the main purpose/topic. Examples:
- "Q4 Budget Planning Review"
- "Product Launch Strategy Meeting"
- "Weekly Team Standup"

RESPOND WITH ONLY THE TITLE:"""
        
        try:
            import requests
            response = await asyncio.to_thread(
                requests.post,
                "http://localhost:11437/completion",
                json={
                    "prompt": title_prompt,
                    "n_predict": 20,  # Shorter response
                    "stream": False,
                    "temperature": 0.3,  # Lower temperature
                    "top_p": 0.9,
                    "top_k": 40
                },
                timeout=15
            )
            
            if response.status_code == 200:
                title = response.json().get("content", "").strip()
                # Clean up the title
                title = title.replace('"', '').replace('\n', ' ').strip()
                return title[:100] if title else None
                
        except Exception as e:
            logger.error(f"Error generating meeting title: {e}")
        
        return None
    
    async def analyze_meeting(self, session_id: str, transcript: str) -> Dict:
        """
        Analyze a meeting transcript (called from simple_recording_db)
        This is a simpler version for final analysis after recording
        """
        try:
            from database.database import get_db_session
            from models.unified_agent import UnifiedMeetingAgent
            
            db_session = get_db_session()
            agent = UnifiedMeetingAgent.get_default_agent(db_session)
            if not agent:
                agent = UnifiedMeetingAgent.create_default_agent(db_session)
            
            # Generate comprehensive analysis
            prompt = f"""{agent.system_prompt}
            
FULL MEETING TRANSCRIPT:
{transcript}

Provide a comprehensive analysis including:
- Executive summary (2-3 sentences)
- Key discussion points (3-5 bullets)
- Action items with owners
- Important decisions
- Suggested meeting title

RESPOND WITH JSON:
{{
    "executive": "Executive summary",
    "bullets": ["Key point 1", "Key point 2"],
    "actions": [{{"action": "Task", "owner": "Person", "priority": "high"}}],
    "decisions": ["Decision 1"],
    "title": "Meeting Title"
}}"""
            
            # Use configured AI backend
            url = f"{self.base_url}{self.endpoint_path}"
            
            if self.backend_type == "llamacpp":
                payload = {
                    "prompt": prompt,
                    "n_predict": 800,
                    "temperature": 0.7,
                    "stream": False
                }
                response_key = "content"
            else:
                payload = {
                    "model": agent.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 800}
                }
                response_key = "response"
            
            import requests
            response = await asyncio.to_thread(
                requests.post, url, json=payload, timeout=30
            )
            
            if response.status_code == 200:
                result = response.json().get(response_key, "")
                logger.info(f"✅ Meeting analysis completed using {self.backend_type}")
                
                # Use helper to extract JSON from AI response
                json_str = self._extract_json_from_ai_response(result)
                if json_str:
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse extracted JSON: {e}")
                        return {}
                else:
                    logger.warning("No JSON found in AI response")
                    return {}
            
            db_session.close()
            
        except Exception as e:
            logger.error(f"Error analyzing meeting: {e}")
            
        return {}
    
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
                    "text": summary_text,  # Plain text summary
                    "word_count": interval_info['current_word_count'],
                    "interval_used": interval_info['current_interval'],
                    "next_interval": interval_info.get('next_interval', interval_info['current_interval']),
                    "model": agent.model_name,
                    "processing_time_ms": processing_time
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await websocket_callback(message)
            logger.info(f"✅ Sent text summary update via WebSocket for session {session_id}")
            
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
                    "model_size": "granite3.3:8b",
                    "sections": summary
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await websocket_callback(message)
            
        except Exception as e:
            logger.error(f"Error sending summary update: {e}")
    
    async def analyze_meeting(self, session_id: str, transcript: str) -> Dict:
        """Analyze meeting transcript with unified agent - with timeout protection"""
        try:
            # Truncate very long transcripts to avoid timeout
            if len(transcript) > 5000:
                transcript = transcript[:5000] + "... [truncated for processing]"
            
            db_session = get_db_session()
            
            # Get or create default agent
            agent = UnifiedMeetingAgent.get_default_agent(db_session)
            if not agent:
                agent = UnifiedMeetingAgent.create_default_agent(db_session)
            
            # Simplified prompt to reduce processing time
            prompt = f"""Analyze this meeting transcript and provide a brief summary:

TRANSCRIPT:
{transcript}

Provide:
1. Brief summary (2-3 sentences)
2. Key points (3-5 bullets)
3. Suggested title

RESPOND WITH JSON:
{{
    "executive": "Brief summary of the meeting",
    "bullets": ["Key point 1", "Key point 2", "Key point 3"],
    "title": "Meeting title"
}}"""

            # Call GPU llama.cpp with robust timeout handling
            try:
                analysis_result = await self._call_llamacpp_with_timeout(
                    prompt, agent.model_name, timeout=120
                )
                
                if analysis_result:
                    return {
                        "success": True,
                        "analysis": analysis_result,
                        "agent_id": str(agent.id)
                    }
                else:
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
    
    async def _call_llamacpp_with_timeout(self, prompt: str, model: str, timeout: int = 120) -> Optional[Dict]:
        """Call GPU-accelerated llama.cpp with Vulkan (Phi-4 or Granite models)"""
        try:
            import aiohttp
            
            # Use the appropriate port based on model context
            # Port 11437: Phi-4 Mini for live summaries
            # Port 11438: Granite 3.3 8B for final summaries
            port = 11437  # Default to Phi-4
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                payload = {
                    "prompt": prompt,
                    "n_predict": 500,  # Limit response length
                    "stream": False,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40
                }
                
                async with session.post(
                    f"http://localhost:{port}/completion",
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result.get("content", "")
                        
                        # Use helper to extract JSON from AI response
                        json_str = self._extract_json_from_ai_response(response_text)
                        if json_str:
                            try:
                                return json.loads(json_str)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse JSON from llama.cpp response: {response_text[:200]}")
                                return None
                        else:
                            logger.warning(f"No JSON found in llama.cpp response: {response_text[:200]}")
                            return None
                    else:
                        logger.error(f"GPU llama.cpp API error: {response.status}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.error("GPU llama.cpp request timed out")
            return None
        except Exception as e:
            logger.error(f"GPU llama.cpp call failed: {e}")
            return None
    
    async def _save_progressive_text_summary_to_db(self, session_id: str, interval_info: Dict, summary_text: str, processing_time: int):
        """Save progressive plain text summary to database"""
        try:
            from database.database import get_db_session
            from database.models import RecordingSession
            import json
            
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
                "timestamp": datetime.utcnow().isoformat(),
                "word_count_at_summary": interval_info.get('current_word_count', 0),
                "interval_used": interval_info.get('current_interval', 500),
                "processing_time_ms": processing_time,
                "text": summary_text,  # Plain text instead of structured sections
                "model": "phi-4-mini"
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
                "last_progressive_summary": datetime.utcnow().isoformat(),
                "total_progressive_summaries": len(summaries),
                "current_word_count": interval_info.get('current_word_count', 0),
                "model_used": "phi-4-mini"
            })
            session.processing_metadata = metadata
            
            db.commit()
            logger.info(f"✅ Saved progressive text summary #{len(summaries)} to database for session {session_id}")
            
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