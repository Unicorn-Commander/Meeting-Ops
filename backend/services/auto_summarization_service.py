"""
Automatic Summarization Service
Handles backend-controlled periodic summarization during live recording
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Any
from datetime import datetime
import json

from services.system_service import SystemService
from services.unified_llm_service import llm_service

logger = logging.getLogger(__name__)


class AutoSummarizationService:
    """Service for automatic summarization during recording"""
    
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.last_summary_time: Dict[str, float] = {}
        self.last_transcript_length: Dict[str, int] = {}
        self.last_summary_word_count: Dict[str, int] = {}  # Track word count at last summary
        self.total_word_count: Dict[str, int] = {}  # Track total words processed
        self.summaries_cache: Dict[str, Dict[str, Any]] = {}
        self.summary_history: Dict[str, list] = {}  # Store all summaries for final compilation
        
    async def start_auto_summarization(
        self, 
        session_id: str,
        websocket_callback=None
    ) -> None:
        """
        Start automatic summarization for a session
        
        Args:
            session_id: Recording session ID
            websocket_callback: Async function to send updates via WebSocket
        """
        # Check if already running for this session
        if session_id in self.active_tasks:
            logger.warning(f"Auto-summarization already running for session {session_id}")
            return
        
        # Create and store the task
        task = asyncio.create_task(
            self._summarization_loop(session_id, websocket_callback)
        )
        self.active_tasks[session_id] = task
        logger.info(f"Started auto-summarization for session {session_id}")
        
    async def stop_auto_summarization(self, session_id: str) -> None:
        """Stop automatic summarization for a session"""
        if session_id in self.active_tasks:
            task = self.active_tasks[session_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.active_tasks[session_id]
            
            # Clean up tracking data
            self.last_summary_time.pop(session_id, None)
            self.last_transcript_length.pop(session_id, None)
            
            logger.info(f"Stopped auto-summarization for session {session_id}")
    
    async def _summarization_loop(
        self, 
        session_id: str,
        websocket_callback=None
    ) -> None:
        """
        Main loop for automatic summarization
        
        Checks settings and generates summaries based on configured trigger mode
        """
        try:
            while True:
                # Load current settings
                settings = SystemService.load_settings()
                
                # Check if live summarization is enabled
                if not settings.enableLiveSummarization:
                    logger.info(f"Live summarization disabled for session {session_id}")
                    await asyncio.sleep(10)  # Check settings every 10 seconds
                    continue
                
                # Determine if we should generate a summary
                should_generate = False
                trigger_reason = ""
                next_update_value = None
                
                if settings.summaryTriggerMode == "word_count":
                    # Word count based triggering
                    current_word_count = await self._get_current_word_count(session_id)
                    last_summary_words = self.last_summary_word_count.get(session_id, 0)
                    word_diff = current_word_count - last_summary_words
                    
                    if word_diff >= settings.summaryWordCountInterval:
                        should_generate = True
                        trigger_reason = f"word_count ({word_diff} new words)"
                        next_update_value = f"in {settings.summaryWordCountInterval} words"
                        
                else:  # time mode
                    # Time-based triggering (legacy mode)
                    current_time = time.time()
                    last_time = self.last_summary_time.get(session_id, 0)
                    
                    if current_time - last_time >= settings.summaryUpdateInterval:
                        should_generate = True
                        trigger_reason = f"time ({settings.summaryUpdateInterval}s elapsed)"
                        next_update_value = f"in {settings.summaryUpdateInterval} seconds"
                
                if should_generate:
                    # Generate summary
                    summary = await self._generate_summary(session_id)
                    
                    if summary:
                        # Cache the summary
                        self.summaries_cache[session_id] = summary
                        
                        # Store in history for final summary
                        if session_id not in self.summary_history:
                            self.summary_history[session_id] = []
                        self.summary_history[session_id].append(summary)
                        
                        # Update tracking based on mode
                        if settings.summaryTriggerMode == "word_count":
                            current_words = await self._get_current_word_count(session_id)
                            self.last_summary_word_count[session_id] = current_words
                        else:
                            self.last_summary_time[session_id] = time.time()
                        
                        # Send via WebSocket if callback provided
                        if websocket_callback:
                            await websocket_callback({
                                "type": "auto_summary",
                                "timestamp": datetime.utcnow().isoformat(),
                                "summary": summary,
                                "trigger_mode": settings.summaryTriggerMode,
                                "trigger_reason": trigger_reason,
                                "next_update": next_update_value,
                                "word_count": self.total_word_count.get(session_id, 0)
                            })
                        
                        logger.info(f"Generated auto-summary for session {session_id} (trigger: {trigger_reason})")
                
                # Sleep for a short time before checking again
                await asyncio.sleep(5)  # Check every 5 seconds
                
        except asyncio.CancelledError:
            logger.info(f"Summarization loop cancelled for session {session_id}")
            raise
        except Exception as e:
            logger.error(f"Error in summarization loop for session {session_id}: {e}")
            # Clean up on error
            self.active_tasks.pop(session_id, None)
    
    async def _generate_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate a summary for the current transcript
        
        Returns summary data or None if transcript hasn't changed significantly
        """
        try:
            # Get the current transcript from live transcription buffer
            transcript_text = ""
            try:
                from services.live_recording_transcription import live_recording_transcription
                if (hasattr(live_recording_transcription, 'session_id') and
                    live_recording_transcription.session_id == session_id and
                    live_recording_transcription.transcript_buffer):
                    for segment in live_recording_transcription.transcript_buffer:
                        text = segment.get("text", "").strip()
                        if text:
                            transcript_text += text + " "
            except Exception:
                pass

            if not transcript_text:
                logger.warning(f"No transcript available for session {session_id}")
                return None
            
            # Check if transcript has changed significantly
            current_length = len(transcript_text)
            last_length = self.last_transcript_length.get(session_id, 0)
            
            # Only generate if we have new content (at least 100 chars difference)
            if current_length - last_length < 100:
                logger.debug(f"Not enough new content for session {session_id}")
                return None
            
            # Update tracking
            self.last_transcript_length[session_id] = current_length
            
            # Generate summary using LLM service
            summary_data = {
                "generated_at": datetime.utcnow().isoformat(),
                "transcript_length": current_length,
                "summary": "Meeting in progress...",
                "key_points": [],
                "action_items": [],
                "topics": [],
                "sentiment": "neutral"
            }
            
            # Only generate AI summary if we have enough content
            if current_length > 200:
                try:
                    if hasattr(llm_service, 'summarize_meeting'):
                        ai_summary = await asyncio.to_thread(
                            llm_service.summarize_meeting,
                            transcript_text
                        )
                        if ai_summary:
                            summary_data.update(ai_summary)
                    else:
                        # Basic extraction without AI
                        sentences = [s.strip() for s in transcript_text.split('.') if len(s.strip()) > 20]
                        summary_data["key_points"] = sentences[:5] if sentences else []
                        summary_data["summary"] = f"Meeting ongoing with {len(sentences)} key points discussed."
                        
                except Exception as e:
                    logger.error(f"Error generating AI summary: {e}")
                    # Continue with basic summary
            
            return summary_data
            
        except Exception as e:
            logger.error(f"Error generating summary for session {session_id}: {e}")
            return None
    
    def get_cached_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the last cached summary for a session"""
        return self.summaries_cache.get(session_id)
    
    def is_running(self, session_id: str) -> bool:
        """Check if auto-summarization is running for a session"""
        return session_id in self.active_tasks
    
    def get_status(self, session_id: str) -> Dict[str, Any]:
        """Get status of auto-summarization for a session"""
        settings = SystemService.load_settings()
        
        return {
            "enabled": settings.enableLiveSummarization,
            "running": self.is_running(session_id),
            "interval": settings.summaryUpdateInterval,
            "last_summary_time": self.last_summary_time.get(session_id),
            "cached_summary": self.summaries_cache.get(session_id) is not None
        }
    
    async def force_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Force generate a summary immediately, regardless of interval"""
        summary = await self._generate_summary(session_id)
        if summary:
            self.summaries_cache[session_id] = summary
            self.last_summary_time[session_id] = time.time()
        return summary
    
    async def _get_current_word_count(self, session_id: str) -> int:
        """Get the current word count for a session's transcript"""
        try:
            # First try to get word count from WebSocket tracking (most accurate for live)
            try:
                from api.websocket_auto_summary import session_word_counts
                if session_id in session_word_counts:
                    word_count = session_word_counts[session_id]
                    self.total_word_count[session_id] = word_count
                    return word_count
            except ImportError:
                pass
            
            # Fallback to live transcription buffer
            try:
                from services.live_recording_transcription import live_recording_transcription
                if (hasattr(live_recording_transcription, 'session_id') and
                    live_recording_transcription.session_id == session_id and
                    live_recording_transcription.transcript_buffer):
                    total = sum(len(seg.get('text', '').split()) for seg in live_recording_transcription.transcript_buffer)
                    self.total_word_count[session_id] = total
                    return total
            except Exception:
                pass

            return 0

        except Exception as e:
            logger.debug(f"Could not get word count for session {session_id}: {e}")
            return 0
    
    async def generate_final_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate a comprehensive final summary when recording stops
        This is separate from the periodic summaries during recording
        """
        try:
            settings = SystemService.load_settings()
            
            if not settings.enableFinalSummary:
                logger.info(f"Final summary disabled for session {session_id}")
                return None
            
            # Get the full transcript from live transcription buffer
            full_transcript = ""
            try:
                from services.live_recording_transcription import live_recording_transcription
                if (hasattr(live_recording_transcription, 'session_id') and
                    live_recording_transcription.session_id == session_id and
                    live_recording_transcription.transcript_buffer):
                    for segment in live_recording_transcription.transcript_buffer:
                        text = segment.get("text", "").strip()
                        if text:
                            full_transcript += text + " "
            except Exception:
                pass

            if len(full_transcript) < 50:
                logger.info(f"Not enough content for final summary in session {session_id}")
                return None

            # Generate comprehensive final summary
            final_summary = {
                "type": "final",
                "generated_at": datetime.utcnow().isoformat(),
                "total_words": len(full_transcript.split()),
                "periodic_summaries_count": len(self.summary_history.get(session_id, [])),
                "summary": "Complete meeting summary...",
                "key_points": [],
                "action_items": [],
                "decisions": [],
                "topics": [],
                "participants": [],
                "sentiment": "neutral",
                "duration_seconds": 0
            }
            
            # Generate comprehensive AI summary for the full transcript
            try:
                if hasattr(llm_service, 'generate_final_summary'):
                    # Use specialized final summary method if available
                    ai_summary = await asyncio.to_thread(
                        llm_service.generate_final_summary,
                        full_transcript,
                        self.summary_history.get(session_id, [])
                    )
                elif hasattr(llm_service, 'summarize_meeting'):
                    # Fallback to regular summarize
                    ai_summary = await asyncio.to_thread(
                        llm_service.summarize_meeting,
                        full_transcript
                    )
                else:
                    ai_summary = None
                
                if ai_summary:
                    final_summary.update(ai_summary)
                    final_summary["summary"] = f"[FINAL SUMMARY] {ai_summary.get('summary', 'Complete meeting transcript processed.')}"
                else:
                    # Basic extraction without AI
                    sentences = [s.strip() for s in full_transcript.split('.') if len(s.strip()) > 20]
                    final_summary["key_points"] = sentences[:10] if sentences else []
                    final_summary["summary"] = f"[FINAL SUMMARY] Meeting completed with {len(sentences)} discussion points."
                    
            except Exception as e:
                logger.error(f"Error generating AI final summary: {e}")
                final_summary["summary"] = "[FINAL SUMMARY] Meeting completed. Full transcript available."
            
            # Store final summary
            sessions[session_id]["final_summary"] = final_summary
            
            # Clean up history for this session
            self.summary_history.pop(session_id, None)
            self.last_summary_word_count.pop(session_id, None)
            self.total_word_count.pop(session_id, None)
            
            logger.info(f"Generated final summary for session {session_id}")
            return final_summary
            
        except Exception as e:
            logger.error(f"Error generating final summary for session {session_id}: {e}")
            return None
    
    async def cleanup(self):
        """Clean up all active tasks"""
        tasks_to_cancel = list(self.active_tasks.keys())
        for session_id in tasks_to_cancel:
            await self.stop_auto_summarization(session_id)
        
        self.summaries_cache.clear()
        self.summary_history.clear()
        logger.info("Auto-summarization service cleaned up")


# Singleton instance
auto_summarization_service = AutoSummarizationService()