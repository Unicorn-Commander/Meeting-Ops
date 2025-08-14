"""
Unified Agent Service
Single agent that handles all meeting tasks with granite3.3:8b
"""
import asyncio
import json
import logging
import time
from typing import Dict, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from database.database import get_db_session
from models.unified_agent import UnifiedMeetingAgent
from services.progressive_interval_manager import progressive_interval_manager, ProgressiveConfig

logger = logging.getLogger(__name__)

class UnifiedAgentService:
    """
    Simplified service for single meeting agent
    Uses granite3.3:8b for all tasks
    """
    
    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        logger.info("Unified Agent Service initialized with granite3.3:8b")
    
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
        """Generate progressive summary using granite3.3:8b"""
        session_info = self.active_sessions[session_id]
        agent = session_info['agent']
        
        start_time = time.time()
        
        try:
            # Get transcript
            transcript = await self._get_session_transcript(session_id)
            
            if not transcript or len(transcript.split()) < 10:
                logger.debug(f"Not enough content for summary (session {session_id})")
                return
            
            # Generate summary using granite3.3:8b
            summary = await self._call_granite_model(transcript, agent, interval_info)
            
            if not summary:
                logger.warning(f"Failed to generate summary for session {session_id}")
                return
            
            processing_time = int((time.time() - start_time) * 1000)
            session_info['summary_count'] += 1
            
            # Send via WebSocket
            if session_info.get('websocket_callback'):
                await self._send_summary_update(session_id, session_info, interval_info, summary, processing_time)
            
            logger.info(f"Generated progressive summary for session {session_id}")
            logger.info(f"  Word count: {interval_info['current_word_count']}")
            logger.info(f"  Interval: {interval_info['current_interval']} words")
            logger.info(f"  Processing time: {processing_time}ms")
            
        except Exception as e:
            logger.error(f"Error generating progressive summary: {e}")
    
    async def _get_session_transcript(self, session_id: str) -> str:
        """Get current transcript for a session"""
        try:
            from api.simple_recording_fixed import sessions
            if session_id in sessions:
                session = sessions[session_id]
                
                if 'transcript' in session and session['transcript']:
                    return session['transcript']
                
                if 'transcription_segments' in session and session['transcription_segments']:
                    segments = session['transcription_segments']
                    return ' '.join(segment.get('text', '') for segment in segments)
            
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

            # Call Ollama API with granite3.3:8b
            response = await asyncio.to_thread(
                requests.post,
                "http://localhost:11434/api/generate",
                json={
                    "model": agent.model_name,  # granite3.3:8b
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": agent.model_config
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                try:
                    return json.loads(result)
                except json.JSONDecodeError:
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
        """Generate comprehensive final summary"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return None
        
        agent = session_info['agent']
        transcript = await self._get_session_transcript(session_id)
        
        if not transcript:
            return None
        
        # Use enhanced prompt for final summary
        final_prompt = f"""{agent.system_prompt}

This is a FINAL COMPREHENSIVE SUMMARY of the entire meeting.

FULL MEETING TRANSCRIPT:
{transcript}

Provide a complete analysis including:
- Comprehensive executive summary
- All key discussion points
- Complete list of action items and decisions
- Final meeting title

RESPOND WITH JSON:
{{
    "executive": "Comprehensive executive summary of the entire meeting",
    "bullets": ["All key points discussed"],
    "actions": [{{"action": "Complete task list", "owner": "Responsible person", "priority": "high/medium/low"}}],
    "decisions": ["All important decisions made"],
    "title": "Descriptive meeting title"
}}"""
        
        try:
            import requests
            response = await asyncio.to_thread(
                requests.post,
                "http://localhost:11434/api/generate",
                json={
                    "model": agent.model_name,
                    "prompt": final_prompt,
                    "stream": False,
                    "format": "json",
                    "options": {**agent.model_config, "num_predict": 1000}  # Longer for final summary
                },
                timeout=60  # Longer timeout for final summary
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                return json.loads(result)
                
        except Exception as e:
            logger.error(f"Error generating final summary: {e}")
        
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
                "http://localhost:11434/api/generate",
                json={
                    "model": agent.model_name,
                    "prompt": title_prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 20}  # Lower temperature, shorter response
                },
                timeout=15
            )
            
            if response.status_code == 200:
                title = response.json().get("response", "").strip()
                # Clean up the title
                title = title.replace('"', '').replace('\n', ' ').strip()
                return title[:100] if title else None
                
        except Exception as e:
            logger.error(f"Error generating meeting title: {e}")
        
        return None
    
    async def _send_summary_update(self, session_id: str, session_info: Dict, interval_info: Dict, summary: Dict, processing_time: int):
        """Send summary update via WebSocket"""
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
                    "next_interval": interval_info['next_interval'],
                    "model_size": "granite3.3:8b",
                    "sections": summary
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await websocket_callback(message)
            
        except Exception as e:
            logger.error(f"Error sending summary update: {e}")
    
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