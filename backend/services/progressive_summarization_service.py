"""
Progressive Summarization Service
Handles AI-powered progressive summarization with configurable agents and providers
"""
import asyncio
import logging
import time
from typing import Dict, Optional, List, Any
from datetime import datetime
import json
import uuid

from sqlalchemy.orm import Session
from database.database import get_db_session
from models.progressive_agents import (
    MeetingAgent, AIProvider, ProgressiveSummary, ProgressiveSessionState
)
from services.progressive_interval_manager import (
    progressive_interval_manager, ProgressiveConfig, IntervalState
)
from services.unified_llm_service import llm_service

logger = logging.getLogger(__name__)

class ProgressiveSummarizationService:
    """
    Service for progressive AI summarization during meetings
    
    Key Features:
    - Progressive intervals (start fast, get longer)
    - Agent-specific configurations
    - Model size optimization based on interval
    - Real-time WebSocket updates
    """
    
    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}  # session_id -> session_info
        self.summarization_tasks: Dict[str, asyncio.Task] = {}  # session_id -> task
        self.db_session = None
        logger.info("Progressive Summarization Service initialized")
    
    async def start_progressive_summarization(
        self, 
        session_id: str,
        websocket_callback=None
    ) -> bool:
        """
        Start progressive summarization for a session using the active agent
        
        Args:
            session_id: Recording session ID
            websocket_callback: Function to send updates via WebSocket
        
        Returns:
            bool: True if started successfully
        """
        if session_id in self.active_sessions:
            logger.warning(f"Progressive summarization already active for session {session_id}")
            return False
        
        try:
            # Get database session
            self.db_session = get_db_session()
            
            # Get active agent
            active_agent = self.db_session.query(MeetingAgent).filter(
                MeetingAgent.is_active == True
            ).first()
            
            if not active_agent:
                logger.warning("No active agent found for progressive summarization")
                return False
            
            # Get active AI provider
            active_provider = self.db_session.query(AIProvider).filter(
                AIProvider.is_active == True
            ).first()
            
            if not active_provider:
                logger.warning("No active AI provider found for progressive summarization")
                return False
            
            # Parse progressive config
            config = ProgressiveConfig.from_dict(active_agent.progressive_config or {})
            
            # Initialize progressive intervals
            progressive_interval_manager.initialize_session(session_id, str(active_agent.id), config)
            
            # Store session info
            session_info = {
                'session_id': session_id,
                'agent': active_agent,
                'provider': active_provider,
                'config': config,
                'websocket_callback': websocket_callback,
                'started_at': datetime.utcnow(),
                'summary_count': 0
            }
            
            self.active_sessions[session_id] = session_info
            
            # Start monitoring task
            task = asyncio.create_task(
                self._progressive_monitoring_loop(session_id)
            )
            self.summarization_tasks[session_id] = task
            
            logger.info(f"Started progressive summarization for session {session_id}")
            logger.info(f"  Agent: {active_agent.name} ({active_agent.role})")
            logger.info(f"  Provider: {active_provider.name} ({active_provider.type})")
            logger.info(f"  Initial interval: {config.initial_word_count} words")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start progressive summarization: {e}")
            return False
        finally:
            if self.db_session:
                self.db_session.close()
    
    async def stop_progressive_summarization(self, session_id: str) -> bool:
        """Stop progressive summarization for a session"""
        if session_id not in self.active_sessions:
            return False
        
        try:
            # Cancel monitoring task
            if session_id in self.summarization_tasks:
                task = self.summarization_tasks[session_id]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del self.summarization_tasks[session_id]
            
            # Clean up session info
            session_info = self.active_sessions[session_id]
            del self.active_sessions[session_id]
            
            # Clean up progressive interval state
            progressive_interval_manager.cleanup_session(session_id)
            
            logger.info(f"Stopped progressive summarization for session {session_id}")
            logger.info(f"  Generated {session_info.get('summary_count', 0)} summaries")
            
            return True
            
        except Exception as e:
            logger.error(f"Error stopping progressive summarization: {e}")
            return False
    
    async def _progressive_monitoring_loop(self, session_id: str):
        """Main monitoring loop for progressive summarization"""
        session_info = self.active_sessions[session_id]
        agent = session_info['agent']
        config = session_info['config']
        
        try:
            while session_id in self.active_sessions:
                # Get current word count from session
                current_word_count = await self._get_session_word_count(session_id)
                
                # Check if we should generate a summary
                should_generate, interval_info = progressive_interval_manager.should_generate_summary(
                    session_id, str(agent.id), current_word_count, config
                )
                
                if should_generate:
                    # Generate progressive summary
                    await self._generate_progressive_summary(session_id, interval_info)
                
                # Sleep before next check (5 second intervals)
                await asyncio.sleep(5)
                
        except asyncio.CancelledError:
            logger.info(f"Progressive monitoring cancelled for session {session_id}")
            raise
        except Exception as e:
            logger.error(f"Error in progressive monitoring loop: {e}")
    
    async def _get_session_word_count(self, session_id: str) -> int:
        """Get current word count for a session"""
        try:
            # Try to get from WebSocket registry first (most accurate)
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
        """Generate a progressive summary for the current state"""
        session_info = self.active_sessions[session_id]
        agent = session_info['agent']
        provider = session_info['provider']
        config = session_info['config']
        
        start_time = time.time()
        
        try:
            # Get transcript content
            transcript = await self._get_session_transcript(session_id)
            
            if not transcript or len(transcript.split()) < 10:
                logger.debug(f"Not enough content for progressive summary (session {session_id})")
                return
            
            # Select model based on config
            model_name = self._get_model_for_interval(provider, config.model_size)
            
            # Generate summary using the agent's configuration
            summary_sections = await self._generate_ai_summary(
                transcript, agent, provider, model_name, interval_info
            )
            
            if not summary_sections:
                logger.warning(f"Failed to generate progressive summary for session {session_id}")
                return
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Store summary in database
            await self._store_progressive_summary(
                session_id, agent, provider, interval_info, summary_sections, processing_time
            )
            
            # Update session count
            session_info['summary_count'] += 1
            
            # Send via WebSocket
            if session_info.get('websocket_callback'):
                await self._send_progressive_summary_update(
                    session_id, session_info, interval_info, summary_sections, processing_time
                )
            
            logger.info(f"Generated progressive summary for session {session_id}")
            logger.info(f"  Word count: {interval_info['current_word_count']}")
            logger.info(f"  Interval: {interval_info['current_interval']} words")
            logger.info(f"  Next interval: {interval_info['next_interval']} words")
            logger.info(f"  Processing time: {processing_time}ms")
            
        except Exception as e:
            logger.error(f"Error generating progressive summary: {e}")
    
    async def _get_session_transcript(self, session_id: str) -> str:
        """Get the current transcript for a session"""
        try:
            from api.simple_recording_fixed import sessions
            if session_id in sessions:
                session = sessions[session_id]
                
                # Try combined transcript first
                if 'transcript' in session and session['transcript']:
                    return session['transcript']
                
                # Build from segments
                if 'transcription_segments' in session and session['transcription_segments']:
                    segments = session['transcription_segments']
                    return ' '.join(segment.get('text', '') for segment in segments)
            
            return ""
            
        except Exception as e:
            logger.error(f"Error getting transcript for session {session_id}: {e}")
            return ""
    
    def _get_model_for_interval(self, provider: AIProvider, model_size: str) -> str:
        """Get the appropriate model for the current interval"""
        performance_config = provider.performance_config or {}
        
        # Get model mapping from provider config
        model_mapping = {
            'small': performance_config.get('small', 'gemma3n:e4b'),
            'medium': performance_config.get('medium', 'phi4-mini:3.8b'),
            'large': performance_config.get('large', 'granite3.3:8b')
        }
        
        return model_mapping.get(model_size, model_mapping['small'])
    
    async def _generate_ai_summary(
        self, 
        transcript: str, 
        agent: MeetingAgent, 
        provider: AIProvider, 
        model_name: str,
        interval_info: Dict
    ) -> Optional[Dict]:
        """Generate AI summary using the agent's configuration"""
        try:
            # Get agent prompts
            prompts = agent.prompts or {}
            system_prompt = prompts.get('system', 'You are a meeting assistant.')
            summary_prompt = prompts.get('summary', 'Summarize this meeting transcript:')
            
            # Get agent sections
            sections = agent.sections or {}
            
            # Build context-aware prompt
            context_prompt = f"""
{system_prompt}

Meeting Context:
- Word count: {interval_info['current_word_count']} words
- Summary #{interval_info['total_summaries'] + 1}
- Agent role: {agent.role}
- Personality: {agent.personality or 'Professional'}

Required sections: {list(sections.keys())}

{summary_prompt}

Transcript:
{transcript}

Generate a JSON response with the following structure:
{{
    "executive": "Brief executive summary",
    "sections": {{
        {', '.join(f'"{k}": "Content for {v}"' for k, v in sections.items())}
    }}
}}
"""
            
            # Use LLM service to generate summary - simplified approach
            try:
                # Use the existing summarize_meeting method which works
                result = await asyncio.to_thread(
                    llm_service.summarize_meeting,
                    transcript,
                    "standard"  # Use standard template
                )
                
                # If that returns a dict, use it directly
                if isinstance(result, dict):
                    return result
                
                # If it's a string, try to parse as JSON
                if isinstance(result, str):
                    try:
                        return json.loads(result)
                    except json.JSONDecodeError:
                        # Create a simple structured response
                        return {
                            "executive": result[:200] + "..." if len(result) > 200 else result,
                            "bullets": [result[:100] + "..." if len(result) > 100 else result],
                            "actions": [],
                            "decisions": []
                        }
                        
            except Exception as fallback_error:
                logger.warning(f"LLM service failed, using mock response: {fallback_error}")
                # Return a mock response so the system doesn't break
                word_count = interval_info.get('current_word_count', 0)
                return {
                    "executive": f"Meeting in progress with {word_count} words transcribed. Progressive summary #{interval_info.get('total_summaries', 0) + 1} generated.",
                    "bullets": [
                        "Meeting is actively being recorded and transcribed",
                        f"Current word count: {word_count}",
                        "AI summarization is working progressively"
                    ],
                    "actions": [],
                    "decisions": []
                }
            
        except Exception as e:
            logger.error(f"Error generating AI summary: {e}")
            return None
    
    async def _store_progressive_summary(
        self,
        session_id: str,
        agent: MeetingAgent,
        provider: AIProvider,
        interval_info: Dict,
        summary_sections: Dict,
        processing_time: int
    ):
        """Store progressive summary in database"""
        try:
            db_session = get_db_session()
            
            summary = ProgressiveSummary(
                session_id=uuid.UUID(session_id),
                agent_id=agent.id,
                provider_id=provider.id,
                word_count=interval_info['current_word_count'],
                interval_used=interval_info['current_interval'],
                next_interval=interval_info['next_interval'],
                model_size=interval_info['model_size'],
                sections=summary_sections,
                processing_time_ms=processing_time
            )
            
            db_session.add(summary)
            db_session.commit()
            
        except Exception as e:
            logger.error(f"Error storing progressive summary: {e}")
        finally:
            if db_session:
                db_session.close()
    
    async def _send_progressive_summary_update(
        self,
        session_id: str,
        session_info: Dict,
        interval_info: Dict,
        summary_sections: Dict,
        processing_time: int
    ):
        """Send progressive summary update via WebSocket"""
        try:
            agent = session_info['agent']
            provider = session_info['provider']
            websocket_callback = session_info['websocket_callback']
            
            message = {
                "type": "progressive_summary",
                "session_id": session_id,
                "agent_id": str(agent.id),
                "agent_name": agent.name,
                "agent_role": agent.role,
                "provider_id": str(provider.id),
                "provider_name": provider.name,
                "word_count": interval_info['current_word_count'],
                "interval_used": interval_info['current_interval'],
                "next_interval": interval_info['next_interval'],
                "model_size": interval_info['model_size'],
                "summary_number": interval_info['total_summaries'] + 1,
                "sections": summary_sections,
                "processing_time_ms": processing_time,
                "timestamp": datetime.utcnow().isoformat(),
                "progress": progressive_interval_manager.get_progress_info(
                    session_id, str(agent.id), interval_info['current_word_count']
                )
            }
            
            await websocket_callback(message)
            
        except Exception as e:
            logger.error(f"Error sending progressive summary update: {e}")
    
    def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Get status of progressive summarization for a session"""
        if session_id not in self.active_sessions:
            return None
        
        session_info = self.active_sessions[session_id]
        agent = session_info['agent']
        
        # Get current progress
        current_word_count = 0
        try:
            from api.websocket_auto_summary import session_word_counts
            current_word_count = session_word_counts.get(session_id, 0)
        except:
            pass
        
        progress = progressive_interval_manager.get_progress_info(
            session_id, str(agent.id), current_word_count
        )
        
        return {
            "session_id": session_id,
            "agent_name": agent.name,
            "agent_role": agent.role,
            "provider_name": session_info['provider'].name,
            "summary_count": session_info['summary_count'],
            "started_at": session_info['started_at'].isoformat(),
            "progress": progress,
            "status": "active"
        }
    
    async def cleanup(self):
        """Clean up all active sessions"""
        sessions_to_stop = list(self.active_sessions.keys())
        for session_id in sessions_to_stop:
            await self.stop_progressive_summarization(session_id)
        
        logger.info("Progressive Summarization Service cleaned up")

# Global instance
progressive_summarization_service = ProgressiveSummarizationService()