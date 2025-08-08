from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer
import asyncio
import json
import logging
from typing import Dict, Set
from datetime import datetime, timedelta
import queue
import threading
import time

from services.transcription_service import transcription_service
from services.audio_level_monitor import AudioLevelMonitor
from services.session_manager import SessionManager
from auth.models import User
from auth.dependencies import get_current_user as get_current_user_from_token

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

class AlwaysOnTranscriptionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.transcription_service = None
        self.audio_monitor = None
        self.session_manager = None
        self.is_running = False
        self.transcription_queue = queue.Queue()
        self.recording_sessions: Dict[str, str] = {}  # user_id -> session_id
        
    async def initialize(self):
        """Initialize services"""
        try:
            self.transcription_service = transcription_service  # Use singleton
            self.audio_monitor = AudioLevelMonitor()
            self.session_manager = SessionManager()
            
            # Start background transcription processing
            if not self.is_running:
                self.is_running = True
                threading.Thread(target=self._transcription_worker, daemon=True).start()
                threading.Thread(target=self._audio_monitoring_worker, daemon=True).start()
                
            logger.info("✅ Always-on transcription manager initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize always-on transcription: {e}")
    
    def _transcription_worker(self):
        """Background worker for continuous transcription"""
        import sounddevice as sd
        import numpy as np
        
        chunk_duration = 2  # 2-second chunks
        sample_rate = 16000
        chunk_size = int(sample_rate * chunk_duration)
        
        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio callback status: {status}")
            
            # Convert to float32 and check for speech
            audio_data = indata[:, 0].astype(np.float32)
            
            # Simple VAD - check if audio level is above threshold
            audio_level = np.sqrt(np.mean(audio_data ** 2))
            if audio_level > 0.001:  # Adjustable threshold
                # Queue for transcription
                self.transcription_queue.put({
                    'audio': audio_data.copy(),
                    'timestamp': datetime.now().isoformat(),
                    'sample_rate': sample_rate
                })
        
        try:
            # Start continuous audio stream
            with sd.InputStream(
                channels=1,
                samplerate=sample_rate,
                blocksize=chunk_size,
                callback=audio_callback,
                dtype=np.float32
            ):
                logger.info("🎤 Always-on audio stream started")
                while self.is_running:
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"❌ Audio stream error: {e}")
    
    def _audio_monitoring_worker(self):
        """Process transcription queue"""
        while self.is_running:
            try:
                if not self.transcription_queue.empty():
                    audio_data = self.transcription_queue.get(timeout=1)
                    
                    # Transcribe audio chunk
                    if self.transcription_service and self.transcription_service.is_ready():
                        try:
                            result = self.transcription_service.transcribe_chunk(
                                audio_data['audio'],
                                audio_data['sample_rate']
                            )
                            
                            if result and result.get('text', '').strip():
                                # Broadcast to all connected clients
                                asyncio.create_task(self._broadcast_transcription({
                                    'type': 'transcription',
                                    'data': {
                                        'id': f"always_on_{int(time.time() * 1000)}",
                                        'text': result['text'],
                                        'timestamp': audio_data['timestamp'],
                                        'confidence': result.get('confidence', 0.0),
                                        'speaker': result.get('speaker', 'SPEAKER_01')
                                    }
                                }))
                                
                        except Exception as e:
                            logger.error(f"❌ Transcription error: {e}")
                            
                else:
                    time.sleep(0.1)  # Short sleep if queue empty
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"❌ Transcription worker error: {e}")
                time.sleep(1)
    
    async def _broadcast_transcription(self, message: dict):
        """Broadcast transcription to all connected clients"""
        if not self.active_connections:
            return
            
        disconnected = []
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send to {user_id}: {e}")
                disconnected.append(user_id)
        
        # Clean up disconnected clients
        for user_id in disconnected:
            self.active_connections.pop(user_id, None)
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Connect user to always-on transcription"""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        
        # Send connection confirmation
        await websocket.send_text(json.dumps({
            'type': 'status',
            'connected': True,
            'model': 'whisper-npu' if self.transcription_service and self.transcription_service.is_ready() else 'offline'
        }))
        
        logger.info(f"✅ User {user_id} connected to always-on transcription")
    
    def disconnect(self, user_id: str):
        """Disconnect user"""
        self.active_connections.pop(user_id, None)
        # Stop any active recording for this user
        if user_id in self.recording_sessions:
            session_id = self.recording_sessions.pop(user_id)
            logger.info(f"📹 Stopped recording session {session_id} for disconnected user {user_id}")
    
    async def start_recording_session(self, user_id: str, session_data: dict):
        """Start recording session for user"""
        try:
            if self.session_manager:
                session = await self.session_manager.create_session(
                    user_id=int(user_id),
                    title=session_data.get('title', f'Always-On Recording {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'),
                    is_realtime=True
                )
                
                self.recording_sessions[user_id] = session.id
                
                # Notify client
                if user_id in self.active_connections:
                    await self.active_connections[user_id].send_text(json.dumps({
                        'type': 'recording_started',
                        'session_id': session.id,
                        'title': session.title
                    }))
                
                logger.info(f"📹 Started recording session {session.id} for user {user_id}")
                return session.id
                
        except Exception as e:
            logger.error(f"❌ Failed to start recording session: {e}")
            return None
    
    async def stop_recording_session(self, user_id: str):
        """Stop recording session for user"""
        try:
            if user_id in self.recording_sessions:
                session_id = self.recording_sessions.pop(user_id)
                
                if self.session_manager:
                    await self.session_manager.stop_session(session_id)
                
                # Notify client
                if user_id in self.active_connections:
                    await self.active_connections[user_id].send_text(json.dumps({
                        'type': 'recording_stopped',
                        'session_id': session_id
                    }))
                
                logger.info(f"📹 Stopped recording session {session_id} for user {user_id}")
                return session_id
                
        except Exception as e:
            logger.error(f"❌ Failed to stop recording session: {e}")
            return None

# Global manager instance
always_on_manager = AlwaysOnTranscriptionManager()

@router.on_event("startup")
async def startup_event():
    await always_on_manager.initialize()

@router.websocket("/ws/transcription/always-on")
async def always_on_transcription_websocket(
    websocket: WebSocket,
    token: str = None
):
    """Always-on live transcription WebSocket endpoint"""
    try:
        # Authenticate user
        if not token:
            await websocket.close(code=4001, reason="Missing authentication token")
            return
        
        try:
            user = get_current_user_from_token(token)
            user_id = str(user.id)
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            await websocket.close(code=4001, reason="Invalid authentication token")
            return
        
        # Connect user
        await always_on_manager.connect(websocket, user_id)
        
        try:
            while True:
                # Listen for client messages (recording start/stop commands)
                try:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    
                    if message.get('type') == 'start_recording':
                        await always_on_manager.start_recording_session(
                            user_id, 
                            message.get('data', {})
                        )
                    elif message.get('type') == 'stop_recording':
                        await always_on_manager.stop_recording_session(user_id)
                    
                except asyncio.TimeoutError:
                    # Keep connection alive
                    continue
                    
        except WebSocketDisconnect:
            logger.info(f"User {user_id} disconnected from always-on transcription")
        finally:
            always_on_manager.disconnect(user_id)
            
    except Exception as e:
        logger.error(f"❌ Always-on transcription WebSocket error: {e}")
        try:
            await websocket.close(code=4000, reason="Internal server error")
        except:
            pass

@router.get("/api/always-on/status")
async def get_always_on_status(current_user: User = Depends(get_current_user_from_token)):
    """Get always-on transcription status"""
    return {
        'enabled': always_on_manager.is_running,
        'active_connections': len(always_on_manager.active_connections),
        'transcription_ready': always_on_manager.transcription_service and always_on_manager.transcription_service.is_ready(),
        'recording_sessions': len(always_on_manager.recording_sessions)
    }

@router.post("/api/always-on/toggle")
async def toggle_always_on(current_user: User = Depends(get_current_user_from_token)):
    """Toggle always-on transcription"""
    try:
        if always_on_manager.is_running:
            always_on_manager.is_running = False
            return {'enabled': False, 'message': 'Always-on transcription stopped'}
        else:
            await always_on_manager.initialize()
            return {'enabled': True, 'message': 'Always-on transcription started'}
            
    except Exception as e:
        logger.error(f"❌ Failed to toggle always-on transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))