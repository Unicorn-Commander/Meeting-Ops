"""
Audio Session Manager - Handles per-session audio recording with proper cleanup
"""
import logging
import threading
from typing import Dict, Callable, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import queue
import time

logger = logging.getLogger(__name__)

@dataclass
class AudioSession:
    """Represents an active audio recording session"""
    session_id: str
    start_time: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    audio_queue: queue.Queue = field(default_factory=queue.Queue)
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    processing_thread: Optional[threading.Thread] = None
    error_count: int = 0
    last_audio_time: float = field(default_factory=time.time)


class AudioSessionManager:
    """Manages multiple concurrent audio recording sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, AudioSession] = {}
        self.lock = threading.Lock()
        self.global_callbacks: Dict[str, Set[Callable]] = {
            'audio_data': set(),
            'audio_level': set(),
            'session_error': set(),
            'session_timeout': set()
        }
        
    def create_session(self, session_id: str) -> AudioSession:
        """Create a new audio session"""
        with self.lock:
            if session_id in self.sessions:
                logger.warning(f"Session {session_id} already exists")
                return self.sessions[session_id]
                
            session = AudioSession(session_id=session_id)
            self.sessions[session_id] = session
            
            # Start processing thread for this session
            session.processing_thread = threading.Thread(
                target=self._process_session_audio,
                args=(session,),
                daemon=True,
                name=f"audio-session-{session_id}"
            )
            session.processing_thread.start()
            
            logger.info(f"Created audio session: {session_id}")
            return session
            
    def stop_session(self, session_id: str) -> bool:
        """Stop and cleanup a session"""
        with self.lock:
            if session_id not in self.sessions:
                logger.warning(f"Session {session_id} not found")
                return False
                
            session = self.sessions[session_id]
            session.is_active = False
            
            # Clear the queue
            while not session.audio_queue.empty():
                try:
                    session.audio_queue.get_nowait()
                except:
                    pass
                    
            # Wait for processing thread to finish (with timeout)
            if session.processing_thread and session.processing_thread.is_alive():
                session.processing_thread.join(timeout=2.0)
                
            # Remove session
            del self.sessions[session_id]
            logger.info(f"Stopped audio session: {session_id}")
            return True
            
    def add_audio_data(self, session_id: str, audio_data: bytes) -> bool:
        """Add audio data to a session's queue"""
        with self.lock:
            if session_id not in self.sessions:
                logger.error(f"Session {session_id} not found")
                return False
                
            session = self.sessions[session_id]
            if not session.is_active:
                logger.warning(f"Session {session_id} is not active")
                return False
                
            try:
                session.audio_queue.put(audio_data, timeout=0.1)
                session.last_audio_time = time.time()
                return True
            except queue.Full:
                logger.error(f"Audio queue full for session {session_id}")
                session.error_count += 1
                self._trigger_session_error(session_id, "Audio queue overflow")
                return False
                
    def register_session_callback(self, session_id: str, event_type: str, callback: Callable):
        """Register a callback for a specific session"""
        with self.lock:
            if session_id not in self.sessions:
                logger.error(f"Session {session_id} not found")
                return
                
            session = self.sessions[session_id]
            session.callbacks[event_type] = callback
            logger.info(f"Registered {event_type} callback for session {session_id}")
            
    def register_global_callback(self, event_type: str, callback: Callable):
        """Register a global callback for all sessions"""
        if event_type in self.global_callbacks:
            self.global_callbacks[event_type].add(callback)
            logger.info(f"Registered global {event_type} callback")
            
    def unregister_global_callback(self, event_type: str, callback: Callable):
        """Unregister a global callback"""
        if event_type in self.global_callbacks:
            self.global_callbacks[event_type].discard(callback)
            
    def _process_session_audio(self, session: AudioSession):
        """Process audio data for a specific session"""
        logger.info(f"Started audio processing for session {session.session_id}")
        
        while session.is_active:
            try:
                # Check for timeout
                if time.time() - session.last_audio_time > 30.0:
                    logger.warning(f"Session {session.session_id} timeout - no audio for 30s")
                    self._trigger_session_timeout(session.session_id)
                    break
                    
                # Get audio data with timeout
                try:
                    audio_data = session.audio_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                    
                # Process audio data
                # Session-specific callbacks
                if 'audio_data' in session.callbacks:
                    try:
                        session.callbacks['audio_data'](session.session_id, audio_data)
                    except Exception as e:
                        logger.error(f"Session callback error: {e}")
                        session.error_count += 1
                        
                # Global callbacks
                for callback in self.global_callbacks['audio_data']:
                    try:
                        callback(session.session_id, audio_data)
                    except Exception as e:
                        logger.error(f"Global callback error: {e}")
                        
            except Exception as e:
                logger.error(f"Error processing audio for session {session.session_id}: {e}")
                session.error_count += 1
                
                if session.error_count > 10:
                    logger.error(f"Too many errors for session {session.session_id}, stopping")
                    self._trigger_session_error(session.session_id, "Too many processing errors")
                    break
                    
        logger.info(f"Stopped audio processing for session {session.session_id}")
        
    def _trigger_session_error(self, session_id: str, error_msg: str):
        """Trigger error callbacks for a session"""
        for callback in self.global_callbacks['session_error']:
            try:
                callback(session_id, error_msg)
            except Exception as e:
                logger.error(f"Error callback failed: {e}")
                
    def _trigger_session_timeout(self, session_id: str):
        """Trigger timeout callbacks for a session"""
        for callback in self.global_callbacks['session_timeout']:
            try:
                callback(session_id)
            except Exception as e:
                logger.error(f"Timeout callback failed: {e}")
                
    def get_active_sessions(self) -> list:
        """Get list of active session IDs"""
        with self.lock:
            return list(self.sessions.keys())
            
    def get_session_info(self, session_id: str) -> Optional[dict]:
        """Get information about a session"""
        with self.lock:
            if session_id not in self.sessions:
                return None
                
            session = self.sessions[session_id]
            return {
                'session_id': session.session_id,
                'start_time': session.start_time.isoformat(),
                'is_active': session.is_active,
                'error_count': session.error_count,
                'queue_size': session.audio_queue.qsize(),
                'last_audio_time': datetime.fromtimestamp(session.last_audio_time).isoformat()
            }
            
    def stop_all_sessions(self):
        """Stop all active sessions"""
        with self.lock:
            session_ids = list(self.sessions.keys())
            
        for session_id in session_ids:
            self.stop_session(session_id)
            
        logger.info("Stopped all audio sessions")