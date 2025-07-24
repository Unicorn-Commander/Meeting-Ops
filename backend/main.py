from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import tempfile
import logging
import asyncio
import json
import base64
import numpy as np
import io
import wave
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session as DBSession
from contextlib import asynccontextmanager

from services.transcription_service import transcription_service
transcriber = transcription_service  # Alias for compatibility
from services.stt_model_manager import stt_model_manager
from stt_engine.speaker_diarization import SpeakerDiarizer
from database.database import init_database, get_db
from services.session_manager import session_manager
from services.settings_manager import settings_manager
from services.audio_input_service import audio_input_service, SOUNDDEVICE_AVAILABLE
from services.audio_recording_service import audio_recording_service
from services.audio_session_manager import AudioSessionManager
from services.audio_input_service_v2 import AudioInputServiceV2
from services.file_storage_service import file_storage_service
from services.pdf_export_service import pdf_export_service
from services.llm_summarization_service import llm_summarization_service
from services.email_service import email_service
from services.wyoming_protocol_service import wyoming_service, wake_word_detector, gesture_recognizer
from services.calendar_integration_service import calendar_service
from services.webhook_service import webhook_service, WebhookEndpoint, notify_session_created, notify_session_started, notify_session_stopped
from routes.files import router as files_router
from auth.routes import router as auth_router
from auth.dependencies import get_current_user, require_permission
# from auth.models import User  # Commented out - using auth module instead
from auth.service import AuthService
from auth.config import auth_config
from database.models import AudioFile
from routers.ai_models import router as ai_models_router
from api.recording_v2 import router as recording_v2_router
from api.stt_models import router as stt_models_router
from api.performance_metrics import router as performance_metrics_router
from api.model_benchmarking import router as model_benchmarking_router
from api.search import router as search_router
from api.intelligence import router as intelligence_router
from api.network import router as network_router
# from middleware.auth_recovery import AuthRecoveryMiddleware, SessionRecoveryMiddleware  # Temporarily commented

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for API requests
class SessionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    meeting_type: Optional[str] = None

class SessionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class TranscriptionCreate(BaseModel):
    text: str
    confidence: Optional[float] = 0.0
    speaker_id: Optional[str] = None

class EmailSummaryRequest(BaseModel):
    recipients: List[str]
    cc_recipients: Optional[List[str]] = None
    bcc_recipients: Optional[List[str]] = None
    include_pdf: bool = True
    include_audio: bool = False
    summary_style: str = "executive"

class CalendarConfigRequest(BaseModel):
    provider: str  # "microsoft365" or "google"
    tenant_id: Optional[str] = None  # For Microsoft 365
    client_id: Optional[str] = None  # For Microsoft 365
    client_secret: Optional[str] = None  # For Microsoft 365
    service_account_key: Optional[Dict[str, str]] = None  # For Google

class MeetingCreateRequest(BaseModel):
    title: str
    start_time: str  # ISO format
    end_time: str    # ISO format
    attendees: List[str]
    location: Optional[str] = None
    description: Optional[str] = ""

class RoomLocationRequest(BaseModel):
    device_location: str
    room_name: str
    capacity: int
    equipment: List[str]

class WebhookEndpointRequest(BaseModel):
    name: str
    url: str
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    active: bool = True
    headers: Optional[Dict[str, str]] = None
    retry_count: int = 3
    timeout: int = 30

class WebhookEndpointUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    active: Optional[bool] = None
    headers: Optional[Dict[str, str]] = None
    retry_count: Optional[int] = None
    timeout: Optional[int] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 LIFESPAN STARTUP CALLED!")
    print(f"🎤 Audio service check at startup:")
    print(f"   use_sounddevice: {audio_input_service.use_sounddevice}")
    print(f"   SOUNDDEVICE_AVAILABLE: {SOUNDDEVICE_AVAILABLE if 'SOUNDDEVICE_AVAILABLE' in globals() else 'not imported'}")
    await startup_handler()
    yield
    # Shutdown
    print("🛑 LIFESPAN SHUTDOWN CALLED!")
    await shutdown_handler()

app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add authentication recovery middleware (temporarily disabled for debugging)
# app.add_middleware(AuthRecoveryMiddleware, secret_key=auth_config.SECRET_KEY)
# app.add_middleware(SessionRecoveryMiddleware)

# Initialize the diarizer globally (transcription service is already initialized)
diarizer = SpeakerDiarizer()

# Store active WebSocket connections
active_connections: Dict[str, WebSocket] = {}
audio_buffers: Dict[str, List[bytes]] = {}

class AudioStreamManager:
    """Manages real-time audio streaming and transcription"""
    
    def __init__(self):
        self.buffer_size = 16000 * 3  # 3 seconds of audio at 16kHz
        self.overlap_size = 16000 * 0.5  # 0.5 seconds overlap
        self.sessions: Dict[str, dict] = {}
    
    def create_session(self, session_id: str):
        """Create a new audio streaming session"""
        self.sessions[session_id] = {
            'buffer': np.array([], dtype=np.float32),
            'transcript': [],
            'last_transcribed_length': 0,
            'started_at': datetime.now(),
            'speaker_timeline': [],
            'active_speakers': {}
        }
        logger.info(f"Created new streaming session: {session_id}")
    
    def add_audio_chunk(self, session_id: str, audio_data: np.ndarray):
        """Add audio chunk to session buffer"""
        if session_id not in self.sessions:
            self.create_session(session_id)
        
        session = self.sessions[session_id]
        session['buffer'] = np.concatenate([session['buffer'], audio_data])
        
        # Check if we have enough audio to transcribe
        if len(session['buffer']) >= self.buffer_size:
            return self.process_buffer(session_id)
        
        return None
    
    def process_buffer(self, session_id: str):
        """Process audio buffer and return transcription"""
        if session_id not in self.sessions:
            return None
            
        session = self.sessions[session_id]
        buffer = session['buffer']
        
        if len(buffer) < self.buffer_size:
            return None
        
        # Extract audio chunk for transcription
        audio_chunk = buffer[:self.buffer_size]
        
        # Keep overlap for context
        session['buffer'] = buffer[self.buffer_size - self.overlap_size:]
        
        try:
            # Create temporary audio file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                # Write audio data as WAV file
                with wave.open(tmp_file.name, 'wb') as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(16000)  # 16kHz
                    
                    # Convert float32 to int16
                    audio_int16 = (audio_chunk * 32767).astype(np.int16)
                    wav_file.writeframes(audio_int16.tobytes())
                
                # Transcribe the audio using the unified transcription service
                transcription_result = transcription_service.process_audio_file(tmp_file.name)
                result = transcription_result.to_dict() if transcription_result else {"text": "", "confidence": 0.0}
                
                # Add transcription metadata from current service
                if transcription_result:
                    model_info = transcription_service.get_current_model_info()
                    result.update({
                        "model_used": model_info.get("model_id", "unknown"),
                        "model_name": model_info.get("name", "Unknown"),
                        "engine_type": model_info.get("engine_type", "Unknown"),
                        "npu_accelerated": "npu" in model_info.get("model_id", "").lower()
                    })
                
                # Perform speaker diarization if available
                speaker_info = None
                if diarizer.is_ready:
                    try:
                        speaker_result = diarizer.diarize_audio_chunk(audio_chunk)
                        if speaker_result.get('success'):
                            speaker_info = speaker_result
                            session['speaker_timeline'].extend(speaker_result.get('timeline', []))
                    except Exception as e:
                        logger.warning(f"Speaker diarization failed: {e}")
                
                # Clean up
                os.unlink(tmp_file.name)
                
                # Process transcription result
                current_time = datetime.now()
                transcription = {
                    'text': result.get('text', ''),
                    'timestamp': current_time.isoformat(),
                    'confidence': result.get('confidence', 0.0),
                    'start_time': result.get('start_time'),
                    'end_time': result.get('end_time'),
                    'speaker_id': result.get('speaker_id') or (speaker_info.get('primary_speaker') if speaker_info else None),
                    'language': result.get('language', 'en'),
                    'segments': result.get('segments', []),
                    'speaker_info': speaker_info,
                    'model_used': transcription_service.current_model_id
                }
                
                session['transcript'].append(transcription)
                return transcription
                
        except Exception as e:
            logger.error(f"Error processing audio buffer for session {session_id}: {e}")
            return None
    
    def get_session_transcript(self, session_id: str):
        """Get full transcript for a session"""
        if session_id not in self.sessions:
            return []
        return self.sessions[session_id]['transcript']
    
    def close_session(self, session_id: str):
        """Close and clean up a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Closed streaming session: {session_id}")

# Initialize audio stream manager
stream_manager = AudioStreamManager()

# Include routers
app.include_router(auth_router)
app.include_router(files_router)
app.include_router(ai_models_router)
app.include_router(recording_v2_router)
app.include_router(stt_models_router)
app.include_router(performance_metrics_router)
app.include_router(model_benchmarking_router)
app.include_router(search_router)
app.include_router(intelligence_router)
app.include_router(network_router)

async def startup_handler():
    print("🚀 STARTUP EVENT CALLED!")  # Simple print to bypass any logger issues
    logger.info("Application startup: Initializing services...")
    
    try:
        # Initialize database
        init_database()
        print("✅ Database initialized")
        
        # Initialize services in parallel
        await asyncio.gather(
            diarizer.initialize(),
            # Add other async initializations here if needed
        )
        print("✅ Services initialized")
        
        logger.info("✅ Core services initialized.")
    except Exception as e:
        print(f"❌ Startup error: {e}")
        logger.error(f"Startup initialization failed: {e}")
        return
    
    # Initialize audio input service with settings
    logger.info("🔧 Initializing audio input service...")
    audio_settings = settings_manager.get_all_settings().get('audio', {})
    audio_device = audio_settings.get('input_source', {}).get('value', 'default')
    sample_rate = audio_settings.get('sample_rate', {}).get('value', 16000)
    channels = audio_settings.get('channels', {}).get('value', 1)
    
    logger.info(f"🎤 Audio settings: device={audio_device}, rate={sample_rate}, channels={channels}")
    
    if audio_input_service.initialize(audio_device, sample_rate, channels):
        logger.info("✅ Audio input service initialized successfully")
    else:
        logger.error("❌ Failed to initialize audio input service")
    
    # CRITICAL: Register audio callbacks for recording pipeline
    logger.info("🎧 Registering critical audio callbacks...")
    
    def handle_audio_data_global(sess_id: str, audio_bytes: bytes):
        """Global audio data handler for all recording sessions"""
        try:
            # Save audio to file
            audio_recording_service.write_audio_chunk(sess_id, audio_bytes)
            
            # Process with transcription service (with error handling)
            try:
                transcription_result = transcription_service.process_audio_chunk(audio_bytes, session_id=sess_id)
                
                if transcription_result:
                    # Get current model info for enhanced metadata
                    model_info = transcription_service.get_current_model_info()
                    
                    # Convert to dict for stream manager compatibility
                    transcription = transcription_result.to_dict()
                    transcription.update({
                        'npu_accelerated': model_info.get('npu_accelerated', False),
                        'model_name': model_info.get('model_name', 'unknown'),
                        'processing_time': model_info.get('processing_time', 0.0),
                        'confidence_score': model_info.get('confidence_score', 0.0)
                    })
                    
                    # Add to stream manager for real-time processing
                    stream_manager.add_transcription(sess_id, transcription)
                    
                    # Store in database via session manager
                    session_manager.add_transcription(
                        sess_id,
                        transcription['text'],
                        transcription['start_time'],
                        transcription['end_time'],
                        transcription.get('confidence_score', 0.0),
                        transcription.get('speaker_id'),
                        transcription.get('npu_accelerated', False),
                        transcription.get('model_name', 'unknown'),
                        transcription.get('processing_time', 0.0)
                    )
                    
                    logger.info(f"📝 Transcription: {transcription['text'][:50]}...")
            except Exception as transcription_error:
                logger.warning(f"Transcription service error (audio still saved): {transcription_error}")
        
        except Exception as e:
            logger.error(f"Error in audio data handler: {e}")
    
    def handle_audio_level_global(level: float):
        """Global audio level handler"""
        try:
            # Broadcast to WebSocket connections
            if hasattr(stream_manager, 'broadcast'):
                asyncio.create_task(
                    stream_manager.broadcast(
                        json.dumps({
                            "type": "audio_level",
                            "level": level
                        })
                    )
                )
        except Exception as e:
            logger.error(f"Error in audio level handler: {e}")
    
    def handle_audio_chunk_global(sess_id: str, chunk_audio_bytes: bytes):
        """Global audio chunk handler for 10-second buffered transcription"""
        try:
            logger.info(f"📝 Processing 10-second audio chunk: {len(chunk_audio_bytes)} bytes for session {sess_id}")
            
            # Process with transcription service for the chunk
            try:
                transcription_result = transcription_service.process_audio_chunk(chunk_audio_bytes, session_id=sess_id)
                
                if transcription_result:
                    logger.info(f"✅ Transcription result: {transcription_result.text[:100]}...")
                    
                    # Get current model info for enhanced metadata
                    model_info = transcription_service.get_current_model_info()
                    
                    # Convert to dict for stream manager compatibility
                    transcription = transcription_result.to_dict()
                    transcription.update({
                        'model_info': model_info,
                        'chunk_size': len(chunk_audio_bytes),
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    
                    # Send to active WebSocket connections
                    if sess_id in active_connections:
                        async def send_transcription():
                            try:
                                await active_connections[sess_id].send_text(json.dumps({
                                    "type": "transcription",
                                    "text": transcription.get("text", ""),
                                    "speaker_id": transcription.get("speaker_id"),
                                    "speaker_name": transcription.get("speaker_name"),
                                    "timestamp": transcription.get("timestamp"),
                                    "confidence": transcription.get("confidence", 0.95),
                                    "processing_time": transcription.get("processing_time"),
                                    "npu_accelerated": transcription.get("npu_accelerated", False)
                                }))
                                logger.info(f"🎯 Transcription sent to WebSocket for session: {sess_id}")
                            except Exception as ws_error:
                                logger.error(f"Failed to send transcription via WebSocket: {ws_error}")
                        
                        asyncio.create_task(send_transcription())
                    else:
                        logger.debug(f"No WebSocket connection for session: {sess_id}")
                else:
                    logger.debug(f"No transcription result for chunk in session: {sess_id}")
                    
            except Exception as transcription_error:
                logger.error(f"Chunk transcription error for session {sess_id}: {transcription_error}")
                
        except Exception as e:
            logger.error(f"Error in chunk audio handler for session {sess_id}: {e}")

    # Register the persistent callbacks
    try:
        audio_input_service.register_callback('audio_data', handle_audio_data_global)
        audio_input_service.register_callback('audio_chunk', handle_audio_chunk_global)
        audio_input_service.register_callback('audio_level', handle_audio_level_global)
        logger.info("✅ Audio callbacks registered globally")
    except Exception as callback_error:
        logger.error(f"❌ Failed to register audio callbacks: {callback_error}")
    
    logger.info("🚀 Server startup completed successfully!")
    
    # Create initial admin user if none exists
    from sqlalchemy.orm import Session
    from database.database import SessionLocal
    db: Session = SessionLocal()
    try:
        # Check if any users exist
        user_count = db.query(User).count()
        if user_count == 0:
            logger.info("Creating initial admin user...")
            admin_user = AuthService.create_user(
                db,
                email="admin@unicorn-commander.local",
                username="admin",
                password="Changeme123!",  # IMPORTANT: Change this in production!
                full_name="System Administrator",
                role="admin"
            )
            admin_user.is_superuser = True
            admin_user.is_verified = True
            db.commit()
            logger.info("✅ Created initial admin user. Username: admin, Password: Changeme123!")
            logger.warning("⚠️  IMPORTANT: Change the admin password immediately!")
    except Exception as e:
        logger.error(f"Error creating initial admin user: {e}")
    finally:
        db.close()
    # Transcription service is auto-initialized and ready to use
    logger.info(f"✅ Transcription service ready with model: {transcription_service.current_model_id}")
    
    # Initialize audio input service with settings
    logger.info("🔧 Initializing audio input service...")
    audio_settings = settings_manager.get_all_settings().get('audio', {})
    audio_device = audio_settings.get('input_source', {}).get('value', 'default')
    sample_rate = audio_settings.get('sample_rate', {}).get('value', 16000)
    channels = audio_settings.get('channels', {}).get('value', 1)
    
    logger.info(f"🎤 Audio settings: device={audio_device}, rate={sample_rate}, channels={channels}")
    
    if audio_input_service.initialize(audio_device, sample_rate, channels):
        logger.info("✅ Audio input service initialized successfully")
    else:
        logger.error("❌ Failed to initialize audio input service")
    
    # Initialize Wyoming Protocol service for Home Assistant satellites
    logger.info("🎙️ Initializing Wyoming Protocol service...")
    wake_word_detector.initialize()
    gesture_recognizer.initialize()
    
    # Register Wyoming Protocol callbacks
    def handle_satellite_audio(chunk_data):
        """Handle audio from Wyoming satellites"""
        session_id = chunk_data.get('satellite_id', 'satellite_session')
        audio_data = chunk_data.get('audio_data')
        
        # Process audio through transcription pipeline
        if audio_data is not None:
            transcription = stream_manager.add_audio_chunk(session_id, audio_data)
            if transcription:
                logger.info(f"🎯 Satellite transcription: {transcription['text']}")
    
    def handle_wake_word(wake_word_data):
        """Handle wake word detection from satellites"""
        logger.info(f"🎯 Wake word detected: {wake_word_data['wake_word']} from {wake_word_data['satellite_id']}")
        # Automatically start recording when wake word is detected
        asyncio.create_task(auto_start_recording_from_wake_word(wake_word_data))
    
    def handle_satellite_connected(satellite_info):
        """Handle satellite connection"""
        logger.info(f"🔗 Satellite connected: {satellite_info['id']}")
    
    wyoming_service.register_callback('audio_chunk', handle_satellite_audio)
    wyoming_service.register_callback('wake_word_detected', handle_wake_word)
    wyoming_service.register_callback('satellite_connected', handle_satellite_connected)
    
    # Start Wyoming Protocol server in background
    async def start_wyoming_server():
        try:
            await wyoming_service.start_server(host='0.0.0.0', port=10700)
        except Exception as e:
            logger.error(f"❌ Failed to start Wyoming Protocol server: {e}")
    
    asyncio.create_task(start_wyoming_server())
    logger.info("✅ Wyoming Protocol service initialized")
    
    # CRITICAL: Always register audio callbacks, regardless of other service failures
    logger.info("🎧 Registering critical audio callbacks...")
    
    def handle_audio_data_global(sess_id: str, audio_bytes: bytes):
        """Global audio data handler for all recording sessions"""
        try:
            # Save audio to file
            audio_recording_service.write_audio_chunk(sess_id, audio_bytes)
            
            # Convert audio bytes to numpy array
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Process directly with transcription service (with error handling)
            try:
                transcription_result = transcription_service.process_audio_chunk(audio_bytes, session_id=sess_id)
                
                if transcription_result:
                    # Get current model info for enhanced metadata
                    model_info = transcription_service.get_current_model_info()
                    
                    # Convert to dict for stream manager compatibility
                    transcription = transcription_result.to_dict()
                    transcription.update({
                        'npu_accelerated': model_info.get('npu_accelerated', False),
                        'model_name': model_info.get('model_name', 'unknown'),
                        'processing_time': model_info.get('processing_time', 0.0),
                        'confidence_score': model_info.get('confidence_score', 0.0)
                    })
                    
                    # Add to stream manager for real-time processing
                    stream_manager.add_transcription(sess_id, transcription)
                    
                    # Store in database via session manager
                    session_manager.add_transcription(
                        sess_id,
                        transcription['text'],
                        transcription['start_time'],
                        transcription['end_time'],
                        transcription.get('confidence_score', 0.0),
                        transcription.get('speaker_id'),
                        transcription.get('npu_accelerated', False),
                        transcription.get('model_name', 'unknown'),
                        transcription.get('processing_time', 0.0)
                    )
                    
                    logger.info(f"📝 Transcription: {transcription['text'][:50]}...")
            except Exception as transcription_error:
                logger.warning(f"Transcription service error (audio still saved): {transcription_error}")
        
        except Exception as e:
            logger.error(f"Error in audio data handler: {e}")
    
    def handle_audio_level_global(level: float):
        """Global audio level handler"""
        try:
            # Broadcast to WebSocket connections
            if hasattr(stream_manager, 'broadcast'):
                asyncio.create_task(
                    stream_manager.broadcast(
                        json.dumps({
                            "type": "audio_level",
                            "level": level
                        })
                    )
                )
        except Exception as e:
            logger.error(f"Error in audio level handler: {e}")
    
    def handle_audio_chunk_global_v2(sess_id: str, chunk_audio_bytes: bytes):
        """Global audio chunk handler for 10-second buffered transcription (v2)"""
        try:
            logger.info(f"📝 Processing 10-second audio chunk: {len(chunk_audio_bytes)} bytes for session {sess_id}")
            
            # Process with transcription service for the chunk
            try:
                transcription_result = transcription_service.process_audio_chunk(chunk_audio_bytes, session_id=sess_id)
                
                if transcription_result:
                    logger.info(f"✅ Transcription result: {transcription_result.text[:100]}...")
                    
                    # Get current model info for enhanced metadata
                    model_info = transcription_service.get_current_model_info()
                    
                    # Convert to dict for stream manager compatibility
                    transcription = transcription_result.to_dict()
                    transcription.update({
                        'model_info': model_info,
                        'chunk_size': len(chunk_audio_bytes),
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    
                    # Send to active WebSocket connections
                    if sess_id in active_connections:
                        async def send_transcription():
                            try:
                                await active_connections[sess_id].send_text(json.dumps({
                                    "type": "transcription",
                                    "text": transcription.get("text", ""),
                                    "speaker_id": transcription.get("speaker_id"),
                                    "speaker_name": transcription.get("speaker_name"),
                                    "timestamp": transcription.get("timestamp"),
                                    "confidence": transcription.get("confidence", 0.95),
                                    "processing_time": transcription.get("processing_time"),
                                    "npu_accelerated": transcription.get("npu_accelerated", False)
                                }))
                                logger.info(f"🎯 Transcription sent to WebSocket for session: {sess_id}")
                            except Exception as ws_error:
                                logger.error(f"Failed to send transcription via WebSocket: {ws_error}")
                        
                        asyncio.create_task(send_transcription())
                    else:
                        logger.debug(f"No WebSocket connection for session: {sess_id}")
                else:
                    logger.debug(f"No transcription result for chunk in session: {sess_id}")
                    
            except Exception as transcription_error:
                logger.error(f"Chunk transcription error for session {sess_id}: {transcription_error}")
                
        except Exception as e:
            logger.error(f"Error in chunk audio handler for session {sess_id}: {e}")

    # Register the persistent callbacks
    try:
        audio_input_service.register_callback('audio_data', handle_audio_data_global)
        audio_input_service.register_callback('audio_chunk', handle_audio_chunk_global_v2)
        audio_input_service.register_callback('audio_level', handle_audio_level_global)
        logger.info("✅ Audio callbacks registered globally")
    except Exception as callback_error:
        logger.error(f"❌ Failed to register audio callbacks: {callback_error}")
    
    logger.info("🚀 Server startup completed successfully!")

async def auto_start_recording_from_wake_word(wake_word_data):
    """Automatically start recording when wake word is detected"""
    try:
        # Create a new session for wake word activation
        session = session_manager.create_session(
            name=f"Wake Word Session - {wake_word_data['wake_word']}",
            description=f"Started by wake word: {wake_word_data['wake_word']} "
                       f"from satellite {wake_word_data['satellite_id']}",
            meeting_type='wake_word_activated'
        )
        
        # Start recording
        session = session_manager.update_session_status(session.session_id, "active")
        stream_manager.create_session(session.session_id)
        
        logger.info(f"🎙️ Auto-started recording session {session.session_id} via wake word")
        
        # Broadcast activation to all satellites
        await wyoming_service.broadcast_activation_command('start')
        
    except Exception as e:
        logger.error(f"❌ Error auto-starting recording from wake word: {e}")

async def shutdown_handler():
    logger.info("Application shutdown: Cleaning up resources...")
    audio_recording_service.stop_all_recordings()
    audio_input_service.cleanup()
    
    # Stop Wyoming Protocol server
    if wyoming_service.is_running:
        await wyoming_service.stop_server()

@app.get("/")
def read_root():
    return {"Hello": "World", "transcriber_ready": transcriber.is_ready}

@app.post("/transcribe/")
async def transcribe_audio(audio_file: UploadFile = File(...)):
    if not transcriber.is_ready:
        return JSONResponse(status_code=503, content={
            "message": "Transcription service not ready. Please wait for initialization."
        })

    try:
        # Save the uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            contents = await audio_file.read()
            tmp_file.write(contents)
            tmp_file_path = tmp_file.name
        
        logger.info(f"Received audio file: {audio_file.filename}, saved to {tmp_file_path}")

        # Transcribe the audio
        transcription_result = transcriber.transcribe_audio(tmp_file_path)

        # Clean up the temporary file
        os.unlink(tmp_file_path)

        return JSONResponse(status_code=200, content={
            "filename": audio_file.filename,
            "transcription": transcription_result
        })
    except Exception as e:
        logger.error(f"Error during transcription: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={
            "message": f"An error occurred during transcription: {str(e)}"
        })

@app.websocket("/ws/stream/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time audio streaming"""
    await websocket.accept()
    active_connections[session_id] = websocket
    
    logger.info(f"New WebSocket connection established for session: {session_id}")
    
    # Send initial status
    await websocket.send_text(json.dumps({
        "type": "status",
        "message": "Connected to Unicorn Commander: Meeting Ops",
        "session_id": session_id,
        "transcriber_ready": transcriber.is_ready,
        "npu_available": ("npu" in (transcriber.current_model_id or "").lower()) if transcriber.is_ready else False,
        "speaker_diarization_ready": diarizer.is_ready
    }))
    
    try:
        while True:
            # Receive audio data
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "audio_chunk":
                # Decode base64 audio data
                audio_data = base64.b64decode(message["audio_data"])
                
                # Convert to numpy array (assuming 16-bit PCM)
                audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32767.0
                
                # Decode base64 audio data
                decoded_audio_data = base64.b64decode(message["audio_data"])
                
                # Process audio chunk with unified transcription service
                try:
                    transcription_result = transcription_service.process_audio_chunk(decoded_audio_data, session_id=session_id)
                    logger.info(f"Transcription result: {transcription_result}")
                except Exception as e:
                    logger.error(f"Error during transcription_service.process_audio_chunk: {e}", exc_info=True)
                    await websocket.send_text(json.dumps({"type": "error", "message": f"Transcription error: {e}"}))
                    continue
                
                if transcription_result:
                    try:
                        # Get enhanced transcription data
                        model_info = transcription_service.get_current_model_info()
                        transcription = transcription_result.to_dict()
                        transcription.update({
                            "model_used": model_info.get("model_id", "unknown"),
                            "engine_type": model_info.get("engine_type", "Unknown"),
                            "npu_accelerated": "npu" in model_info.get("model_id", "").lower(),
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        # Add to stream manager for session tracking
                        if session_id in stream_manager.sessions:
                            stream_manager.sessions[session_id]['transcript'].append(transcription)
                        
                        # Send transcription result with enhanced metadata
                        await websocket.send_text(json.dumps({
                            "type": "transcription",
                            "data": transcription
                        }))
                        
                        logger.info(f"Sent transcription for session {session_id}: {transcription['text']}")
                    except Exception as e:
                        logger.error(f"Error processing transcription result or sending to WebSocket: {e}", exc_info=True)
                        await websocket.send_text(json.dumps({"type": "error", "message": f"Result processing error: {e}"}))
                        continue
                
                # Send audio level feedback
                audio_level = np.max(np.abs(audio_array))
                await websocket.send_text(json.dumps({
                    "type": "audio_level",
                    "level": float(audio_level)
                }))
                
            elif message["type"] == "get_transcript":
                # Send full transcript
                transcript = stream_manager.get_session_transcript(session_id)
                await websocket.send_text(json.dumps({
                    "type": "full_transcript",
                    "transcript": transcript
                }))
                
            elif message["type"] == "ping":
                # Respond to ping
                await websocket.send_text(json.dumps({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }))
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
        if session_id in active_connections:
            del active_connections[session_id]
        stream_manager.close_session(session_id)
    except Exception as e:
        logger.error(f"Error in WebSocket connection {session_id}: {e}")
        if session_id in active_connections:
            del active_connections[session_id]
        stream_manager.close_session(session_id)

@app.get("/api/status")
async def get_status():
    """Get system status"""
    try:
        # Check if NPU is available by looking at current model
        npu_available = False
        system_info = {
            "onnx_whisper_ready": transcriber.is_ready,
            "npu_available": False,
            "onnx_providers": [],
            "model_path": getattr(transcriber, 'current_model_id', None)
        }
        
        if transcriber.is_ready and hasattr(transcriber, 'current_model_id') and transcriber.current_model_id:
            # Check if current model supports NPU
            if "npu" in transcriber.current_model_id.lower():
                npu_available = True
                system_info["npu_available"] = True
        
        return {
            "transcriber_ready": transcriber.is_ready,
            "npu_available": npu_available,
            "speaker_diarization_ready": diarizer.is_ready if diarizer else False,
            "active_sessions": len(active_connections),
            "system_info": system_info,
            "diarizer_info": diarizer.get_status() if hasattr(diarizer, 'get_status') else None
        }
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}")
        # Return a minimal status response
        return {
            "transcriber_ready": False,
            "npu_available": False,
            "speaker_diarization_ready": False,
            "active_sessions": 0,
            "system_info": {
                "onnx_whisper_ready": False,
                "npu_available": False,
                "onnx_providers": [],
                "model_path": None
            },
            "diarizer_info": None
        }

@app.get("/api/sessions")
async def get_sessions():
    """Get active sessions"""
    sessions = []
    for session_id in stream_manager.sessions:
        session = stream_manager.sessions[session_id]
        sessions.append({
            "session_id": session_id,
            "started_at": session['started_at'].isoformat(),
            "transcript_length": len(session['transcript']),
            "connected": session_id in active_connections
        })
    return {"sessions": sessions}

@app.get("/api/sessions/{session_id}/transcript")
async def get_session_transcript(session_id: str):
    """Get transcript for a specific session"""
    transcript = stream_manager.get_session_transcript(session_id)
    return {"session_id": session_id, "transcript": transcript}

# === NEW SESSION MANAGEMENT ENDPOINTS ===

@app.post("/api/recording-sessions")
async def create_recording_session(
    session_data: SessionCreate
):
    """Create a new recording session"""
    try:
        session = session_manager.create_session(
            name=session_data.name,
            description=session_data.description,
            meeting_type=session_data.meeting_type
        )
        
        # Send webhook notification
        try:
            await notify_session_created(session.to_dict())
        except Exception as e:
            logger.warning(f"Failed to send session created webhook: {e}")
        
        return {"success": True, "session": session.to_dict()}
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recording-sessions")
async def get_recording_sessions(
    limit: int = 50,
    offset: int = 0,
    status: str = None,
):
    """Get list of recording sessions"""
    try:
        sessions = session_manager.get_sessions(limit=limit, offset=offset, status=status)
        return {
            "sessions": [session.to_dict() for session in sessions],
            "total": len(sessions),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recording-sessions/{session_id}")
async def get_recording_session(
    session_id: str,
):
    """Get a specific recording session with transcriptions and speakers"""
    try:
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        transcriptions = session_manager.get_session_transcriptions(session_id)
        speakers = session_manager.get_session_speakers(session_id)
        
        return {
            "session": session.to_dict(),
            "transcriptions": [t.to_dict() for t in transcriptions],
            "speakers": [s.to_dict() for s in speakers]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/recording-sessions/{session_id}")
async def update_recording_session(
    session_id: str,
    session_data: SessionUpdate,
):
    """Update a recording session"""
    try:
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Update session status if provided
        if session_data.status:
            session = session_manager.update_session_status(session_id, session_data.status)
        
        return {"success": True, "session": session.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/recording-sessions/{session_id}")
async def delete_recording_session(
    session_id: str,
):
    """Delete a recording session"""
    try:
        success = session_manager.delete_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {"success": True, "message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recording-sessions/{session_id}/start")
async def start_recording_session(
    session_id: str,
):
    """Start recording for a session"""
    try:
        session = session_manager.update_session_status(session_id, "active")
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Create WebSocket audio stream session
        stream_manager.create_session(session_id)
        
        # Send webhook notification
        try:
            await notify_session_started(session.to_dict())
        except Exception as e:
            logger.warning(f"Failed to send session started webhook: {e}")
        
        # Get audio file path
        audio_file_path = await file_storage_service.save_audio_stream(
            session_id=session_id,
            format="wav"
        )
        
        # Ensure audio service is initialized
        if not audio_input_service.is_recording:
            print("🔧 Initializing audio service...")
            audio_settings = settings_manager.get_all_settings().get('audio', {})
            # Extract values from settings objects
            input_source = audio_settings.get('input_source', {})
            audio_device = input_source.get('value', 'default') if isinstance(input_source, dict) else input_source
            
            sample_rate_setting = audio_settings.get('sample_rate', {})
            sample_rate = sample_rate_setting.get('value', 16000) if isinstance(sample_rate_setting, dict) else sample_rate_setting
            
            channels_setting = audio_settings.get('channels', {})
            channels = channels_setting.get('value', 1) if isinstance(channels_setting, dict) else channels_setting
            
            if audio_input_service.initialize(audio_device, sample_rate, channels):
                print("✅ Audio service initialized in recording endpoint")
            else:
                print("❌ Failed to initialize audio service")
        
        # Start audio recording to file
        audio_recording_service.start_recording(
            session_id=session_id,
            file_path=audio_file_path,
            sample_rate=audio_input_service.sample_rate,
            channels=audio_input_service.channels
        )
        
        # FALLBACK: Register audio callbacks if not already registered
        logger.info(f"🔍 Checking callbacks: {hasattr(audio_input_service, '_callbacks_registered')}")
        print(f"🔍 Checking callbacks: {hasattr(audio_input_service, '_callbacks_registered')}")
        
        # Always register callbacks to ensure they work
        # if not hasattr(audio_input_service, '_callbacks_registered'):
        if True:  # Force registration every time for now
            logger.info("🔧 Registering audio callbacks (fallback)")
            print("🔧 FALLBACK REGISTRATION STARTING")
            
            def handle_audio_data_fallback(sess_id: str, audio_bytes: bytes):
                """Fallback audio data handler"""
                try:
                    # Save audio to file
                    audio_recording_service.write_audio_chunk(sess_id, audio_bytes)
                    
                    # Process with transcription service (with error handling)
                    try:
                        transcription_result = transcription_service.process_audio_chunk(audio_bytes, session_id=sess_id)
                        
                        if transcription_result:
                            logger.info(f"📝 Live transcription: {transcription_result.text[:50]}...")
                            
                            # Store in database via session manager
                            session_manager.add_transcription(
                                sess_id,
                                transcription_result.text,
                                transcription_result.start_time or 0,
                                transcription_result.end_time or 0,
                                transcription_result.confidence,
                                transcription_result.speaker_id,
                                False,  # npu_accelerated
                                'whisper',  # model_name
                                0.0  # processing_time
                            )
                    except Exception as transcription_error:
                        logger.warning(f"Transcription error: {transcription_error}")
                
                except Exception as e:
                    logger.error(f"Audio data handler error: {e}")
            
            def handle_audio_level_fallback(level: float):
                """Fallback audio level handler"""
                pass  # Just ignore for now
            
            def handle_audio_chunk_fallback(sess_id: str, chunk_audio_bytes: bytes):
                """Fallback audio chunk handler for 10-second buffered transcription"""
                try:
                    logger.info(f"📝 FALLBACK: Processing 10-second audio chunk: {len(chunk_audio_bytes)} bytes for session {sess_id}")
                    
                    # Process with transcription service for the chunk
                    try:
                        transcription_result = transcription_service.process_audio_chunk(chunk_audio_bytes, session_id=sess_id)
                        
                        if transcription_result:
                            logger.info(f"✅ FALLBACK transcription result: {transcription_result.text[:100]}...")
                            
                            # Store in database via session manager
                            session_manager.add_transcription(
                                sess_id,
                                transcription_result.text,
                                transcription_result.confidence,
                                transcription_result.speaker_id
                            )
                            
                            logger.info(f"🎯 FALLBACK: Chunk transcription saved for session: {sess_id}")
                        else:
                            logger.debug(f"No transcription result for fallback chunk in session: {sess_id}")
                            
                    except Exception as transcription_error:
                        logger.error(f"FALLBACK chunk transcription error for session {sess_id}: {transcription_error}")
                        
                except Exception as e:
                    logger.error(f"Error in fallback chunk audio handler for session {sess_id}: {e}")
            
            # Register fallback callbacks
            audio_input_service.register_callback('audio_data', handle_audio_data_fallback)
            audio_input_service.register_callback('audio_chunk', handle_audio_chunk_fallback)
            audio_input_service.register_callback('audio_level', handle_audio_level_fallback)
            audio_input_service._callbacks_registered = True
            logger.info("✅ Fallback audio callbacks registered")
            print("✅ FALLBACK CALLBACKS REGISTERED!")
        
        # Start hardware recording
        if audio_input_service.start_recording(session_id):
            logger.info(f"🎙️ Started hardware recording for session: {session_id}")
        else:
            logger.warning(f"⚠️ Failed to start hardware recording for session: {session_id}")
        
        return {"success": True, "session": session.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting recording for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recording-sessions/{session_id}/stop")
async def stop_recording_session(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """Stop recording for a session"""
    try:
        session = session_manager.update_session_status(session_id, "completed")
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Stop hardware recording
        audio_input_service.stop_recording()
        
        # Stop file recording and get file info
        recording_info = audio_recording_service.stop_recording(session_id)
        
        if recording_info:
            # Save audio file metadata to database
            file_info = file_storage_service.get_file_info(recording_info['file_path'])
            
            if file_info:
                audio_file = AudioFile(
                    file_id=hashlib.md5(f"{session_id}_{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12],
                    session_id=session_id,
                    user_id=current_user.id,
                    filename=file_info['filename'],
                    file_path=recording_info['file_path'],
                    file_size=file_info['size'],
                    file_format=file_info['format'] or 'wav',
                    mime_type=file_info['mime_type'],
                    duration_seconds=recording_info['duration_seconds'],
                    sample_rate=audio_input_service.sample_rate,
                    channels=audio_input_service.channels
                )
                db.add(audio_file)
                db.commit()
                
                logger.info(f"📁 Saved audio file: {file_info['filename']} ({file_info['size']} bytes)")
        
        # Close stream manager session
        stream_manager.close_session(session_id)
        
        logger.info(f"⏹️ Stopped recording for session: {session_id}")
        
        # Send webhook notification
        try:
            await notify_session_stopped(session.to_dict())
        except Exception as e:
            logger.warning(f"Failed to send session stopped webhook: {e}")
        
        return {"success": True, "session": session.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping recording for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recording-sessions/{session_id}/pause")
async def pause_recording_session(
    session_id: str,
):
    """Pause recording for a session"""
    try:
        session = session_manager.update_session_status(session_id, "paused")
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # TODO: Pause actual hardware recording here
        logger.info(f"⏸️ Pausing recording for session: {session_id}")
        
        return {"success": True, "session": session.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing recording for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recording-sessions/{session_id}/export")
async def export_recording_session(
    session_id: str,
    format: str = "json",
    include_summary: bool = True,
    include_speakers: bool = True,
    include_timestamps: bool = True,
    include_confidence: bool = False,
):
    """Export session data in specified format"""
    try:
        if format not in ["json", "txt", "pdf"]:
            raise HTTPException(status_code=400, detail="Format must be 'json', 'txt', or 'pdf'")
        
        if format == "pdf":
            # Get session data for PDF export
            session = session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            transcriptions = session_manager.get_session_transcriptions(session_id)
            speakers = session_manager.get_session_speakers(session_id)
            
            # Generate PDF
            pdf_filename = f"meeting_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf_path = os.path.join("/tmp", pdf_filename)
            
            success = pdf_export_service.generate_session_pdf(
                session_data=session.to_dict(),
                transcriptions=[t.to_dict() for t in transcriptions],
                speakers=[s.to_dict() for s in speakers],
                output_path=pdf_path,
                include_summary=include_summary,
                include_speakers=include_speakers,
                include_timestamps=include_timestamps,
                include_confidence=include_confidence
            )
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to generate PDF")
            
            # Return file response
            from fastapi.responses import FileResponse
            return FileResponse(
                path=pdf_path,
                filename=pdf_filename,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={pdf_filename}"}
            )
        else:
            # Handle JSON and TXT exports as before
            export_data = session_manager.export_session(session_id, format)
            if not export_data:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return export_data
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recording-sessions/{session_id}/transcriptions")
async def add_transcription_to_session(session_id: str, transcription_data: TranscriptionCreate):
    """Add a transcription to a session"""
    try:
        transcription = session_manager.add_transcription(
            session_id=session_id,
            text=transcription_data.text,
            confidence=transcription_data.confidence,
            speaker_id=transcription_data.speaker_id
        )
        
        if not transcription:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {"success": True, "transcription": transcription.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding transcription to session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session-stats")
async def get_session_statistics():
    """Get overall session statistics"""
    try:
        stats = session_manager.get_session_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting session stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === SETTINGS API ENDPOINTS ===

@app.get("/api/settings")
async def get_all_settings(
    current_user= Depends(require_permission("settings.read"))
):
    """Get all application settings"""
    try:
        settings = settings_manager.get_all_settings()
        return {"settings": settings}
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/{category}")
async def get_category_settings(category: str):
    """Get settings for a specific category"""
    try:
        all_settings = settings_manager.get_all_settings()
        if category not in all_settings:
            raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
        
        return {"category": category, "settings": all_settings[category]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting category settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/{category}")
async def update_category_settings(
    category: str,
    settings: Dict[str, Any],
    current_user= Depends(require_permission("settings.update"))
):
    """Update settings for a specific category"""
    try:
        success = settings_manager.update_category_settings(category, settings)
        if success:
            return {"success": True, "message": f"Settings updated for category: {category}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update settings")
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/export")
async def export_settings():
    """Export all settings for backup"""
    try:
        export_data = settings_manager.export_settings()
        return export_data
    except Exception as e:
        logger.error(f"Error exporting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/import")
async def import_settings(settings_data: Dict[str, Any]):
    """Import settings from backup"""
    try:
        success = settings_manager.import_settings(settings_data)
        if success:
            return {"success": True, "message": "Settings imported successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to import settings")
    except Exception as e:
        logger.error(f"Error importing settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio-devices")
async def get_audio_devices():
    """Get list of available audio input devices"""
    try:
        devices = settings_manager.get_audio_devices()
        return {"devices": devices}
    except Exception as e:
        logger.error(f"Error getting audio devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system-info")
async def get_system_info():
    """Get system information"""
    try:
        info = settings_manager.get_system_info()
        return info
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio-level")
async def get_audio_level():
    """Get current audio input level"""
    return {
        "level": audio_input_service.get_audio_level(),
        "is_recording": audio_input_service.is_recording
    }

@app.get("/api/debug/audio-status")
async def debug_audio_status():
    """Debug endpoint to check audio service status"""
    return {
        "instance_id": getattr(audio_input_service, 'instance_id', 'unknown'),
        "is_recording": audio_input_service.is_recording,
        "use_sounddevice": audio_input_service.use_sounddevice,
        "device_index": audio_input_service.device_index,
        "sample_rate": audio_input_service.sample_rate,
        "channels": audio_input_service.channels,
        "callbacks": list(audio_input_service.callbacks.keys()),
        "has_stream": audio_input_service.sd_stream is not None or audio_input_service.stream is not None,
        "audio_queue_size": audio_input_service.audio_queue.qsize()
    }

@app.post("/api/recording-sessions/{session_id}/summary")
async def generate_session_summary(
    session_id: str,
    summary_style: str = "executive",
    focus_areas: Optional[List[str]] = None,
    current_user= Depends(require_permission("session.read"))
):
    """Generate AI-powered comprehensive summary for a session"""
    try:
        # Get session data
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        transcriptions = session_manager.get_session_transcriptions(session_id)
        speakers = session_manager.get_session_speakers(session_id)
        
        # Generate comprehensive summary
        summary = await llm_summarization_service.generate_comprehensive_summary(
            session_data=session.to_dict(),
            transcriptions=[t.to_dict() for t in transcriptions],
            speakers=[s.to_dict() for s in speakers],
            summary_style=summary_style,
            focus_areas=focus_areas or []
        )
        
        return {
            "session_id": session_id,
            "summary": summary,
            "generated_at": datetime.now().isoformat(),
            "style": summary_style,
            "focus_areas": focus_areas
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating summary for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recording-sessions/{session_id}/email-summary")
async def email_session_summary(
    session_id: str,
    email_request: EmailSummaryRequest,
    current_user= Depends(require_permission("session.read"))
):
    """Email meeting summary to specified recipients"""
    try:
        if not email_service.is_configured():
            raise HTTPException(
                status_code=503, 
                detail="Email service not configured. Please set SMTP settings."
            )
        
        # Get session data
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        transcriptions = session_manager.get_session_transcriptions(session_id)
        speakers = session_manager.get_session_speakers(session_id)
        
        # Generate comprehensive summary
        summary = await llm_summarization_service.generate_comprehensive_summary(
            session_data=session.to_dict(),
            transcriptions=[t.to_dict() for t in transcriptions],
            speakers=[s.to_dict() for s in speakers],
            summary_style=email_request.summary_style
        )
        
        # Send email
        success = await email_service.send_meeting_summary(
            recipients=email_request.recipients,
            session_data=session.to_dict(),
            summary_data=summary,
            include_pdf=email_request.include_pdf,
            include_audio=email_request.include_audio,
            cc_recipients=email_request.cc_recipients,
            bcc_recipients=email_request.bcc_recipients
        )
        
        if success:
            return {
                "success": True,
                "message": f"Meeting summary sent to {len(email_request.recipients)} recipients",
                "recipients": email_request.recipients
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email summary for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email/test")
async def send_test_email(
    recipient: str,
    current_user= Depends(require_permission("settings.update"))
):
    """Send test email to verify configuration"""
    try:
        if not email_service.is_configured():
            raise HTTPException(
                status_code=503,
                detail="Email service not configured. Please set SMTP settings."
            )
        
        success = await email_service.send_test_email(recipient)
        
        if success:
            return {"success": True, "message": f"Test email sent to {recipient}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send test email")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/email/status")
async def get_email_status(
    current_user= Depends(require_permission("settings.read"))
):
    """Get email service configuration status"""
    return {
        "configured": email_service.is_configured(),
        "smtp_host": email_service.smtp_host,
        "smtp_port": email_service.smtp_port,
        "from_email": email_service.from_email,
        "from_name": email_service.from_name,
        "smtp_use_tls": email_service.smtp_use_tls
    }

@app.get("/api/wyoming/satellites")
async def get_wyoming_satellites(
    current_user= Depends(require_permission("settings.read"))
):
    """Get status of all connected Wyoming Protocol satellites"""
    return {
        "satellites": wyoming_service.get_satellite_status(),
        "server_running": wyoming_service.is_running,
        "server_port": wyoming_service.port
    }

@app.post("/api/wyoming/broadcast/{command}")
async def broadcast_wyoming_command(
    command: str,
    satellite_id: Optional[str] = None,
    current_user= Depends(require_permission("session.update"))
):
    """Send command to Wyoming Protocol satellites"""
    try:
        if command not in ['start', 'stop', 'pause']:
            raise HTTPException(status_code=400, detail="Invalid command. Must be 'start', 'stop', or 'pause'")
        
        await wyoming_service.broadcast_activation_command(command, satellite_id)
        
        return {
            "success": True,
            "message": f"Command '{command}' sent to {'all satellites' if not satellite_id else f'satellite {satellite_id}'}",
            "command": command,
            "target": satellite_id or "all"
        }
        
    except Exception as e:
        logger.error(f"Error broadcasting Wyoming command: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/wyoming/wake-word/configure")
async def configure_wake_words(
    wake_words: List[str],
    threshold: float = 0.8,
    current_user= Depends(require_permission("settings.update"))
):
    """Configure wake words and detection threshold"""
    try:
        if not wake_words:
            raise HTTPException(status_code=400, detail="At least one wake word is required")
        
        if not 0.1 <= threshold <= 1.0:
            raise HTTPException(status_code=400, detail="Threshold must be between 0.1 and 1.0")
        
        wyoming_service.wake_words = wake_words
        wyoming_service.wake_word_threshold = threshold
        
        return {
            "success": True,
            "message": "Wake words configured successfully",
            "wake_words": wake_words,
            "threshold": threshold
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error configuring wake words: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/wyoming/wake-word/status")
async def get_wake_word_status(
    current_user= Depends(require_permission("settings.read"))
):
    """Get wake word detection configuration and status"""
    return {
        "wake_words": wyoming_service.wake_words,
        "threshold": wyoming_service.wake_word_threshold,
        "detector_ready": wake_word_detector.is_initialized,
        "gesture_recognition_ready": gesture_recognizer.is_initialized
    }

@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """Get real-time performance metrics for the PerformanceMonitor component"""
    import psutil
    import time
    
    try:
        # Calculate NPU metrics
        npu_enabled = ("npu" in (transcriber.current_model_id or "").lower()) if transcriber.is_ready else False
        npu_info = transcriber.get_system_info() if transcriber.is_ready else {}
        
        # Get session statistics
        session_stats = session_manager.get_session_stats()
        active_sessions = len(active_connections)
        
        # Get recent transcription performance
        recent_rtf = 0.08  # Default RTF for NPU
        tokens_per_second = 4789 if npu_enabled else 22
        words_per_minute = tokens_per_second * 60 * 0.75  # Approx words per token
        
        # Calculate system resources
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # NPU specific metrics (mock data for now, replace with real NPU monitoring)
        npu_utilization = 45 if npu_enabled else 0
        npu_power = 8.5 if npu_enabled else 0
        npu_temperature = 65 if npu_enabled else 0
        npu_memory = 512 if npu_enabled else 0
        npu_tops = 50 if npu_enabled else 0
        
        metrics = {
            "transcription": {
                "rtf": recent_rtf,
                "tokensPerSecond": tokens_per_second,
                "wordsPerMinute": int(words_per_minute),
                "processingTime": recent_rtf * 1000,  # Convert to ms
                "audioProcessed": session_stats.get('total_duration', 0)
            },
            "npu": {
                "enabled": npu_enabled,
                "utilizationPercent": npu_utilization,
                "powerWatts": npu_power,
                "temperature": npu_temperature,
                "memoryUsedMB": npu_memory,
                "computeTOPS": npu_tops
            },
            "system": {
                "cpuPercent": cpu_percent,
                "memoryUsedGB": round(memory.used / (1024**3), 1),
                "memoryTotalGB": round(memory.total / (1024**3), 1),
                "diskUsedGB": round(disk.used / (1024**3), 1),
                "diskTotalGB": round(disk.total / (1024**3), 1)
            },
            "session": {
                "activeCount": active_sessions,
                "totalProcessed": session_stats.get('total_sessions', 0),
                "averageRTF": recent_rtf,
                "totalHoursProcessed": round(session_stats.get('total_duration', 0) / 3600, 1)
            }
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        # Return safe defaults
        return {
            "transcription": {
                "rtf": 0.08,
                "tokensPerSecond": 0,
                "wordsPerMinute": 0,
                "processingTime": 0,
                "audioProcessed": 0
            },
            "npu": {
                "enabled": False,
                "utilizationPercent": 0,
                "powerWatts": 0,
                "temperature": 0,
                "memoryUsedMB": 0,
                "computeTOPS": 0
            },
            "system": {
                "cpuPercent": 0,
                "memoryUsedGB": 0,
                "memoryTotalGB": 16,
                "diskUsedGB": 0,
                "diskTotalGB": 500
            },
            "session": {
                "activeCount": 0,
                "totalProcessed": 0,
                "averageRTF": 0,
                "totalHoursProcessed": 0
            }
        }

# Calendar Integration Endpoints

@app.post("/api/calendar/configure")
async def configure_calendar_integration(
    config: CalendarConfigRequest,
    current_user= Depends(require_permission("admin"))
):
    """Configure Microsoft 365 or Google Workspace calendar integration"""
    try:
        if config.provider == "microsoft365":
            if not all([config.tenant_id, config.client_id, config.client_secret]):
                raise HTTPException(status_code=400, detail="Microsoft 365 requires tenant_id, client_id, and client_secret")
            
            calendar_service.configure_microsoft_365(
                config.tenant_id, config.client_id, config.client_secret
            )
            
            # Test authentication
            auth_success = await calendar_service.microsoft_service.authenticate()
            if not auth_success:
                raise HTTPException(status_code=400, detail="Failed to authenticate with Microsoft 365")
            
        elif config.provider == "google":
            if not config.service_account_key:
                raise HTTPException(status_code=400, detail="Google Workspace requires service_account_key")
            
            calendar_service.configure_google_workspace(config.service_account_key)
            
            # Test authentication
            auth_success = await calendar_service.google_service.authenticate()
            if not auth_success:
                raise HTTPException(status_code=400, detail="Failed to authenticate with Google Workspace")
                
        else:
            raise HTTPException(status_code=400, detail="Provider must be 'microsoft365' or 'google'")
        
        return {
            "status": "success",
            "provider": config.provider,
            "message": f"{config.provider} calendar integration configured successfully"
        }
        
    except Exception as e:
        logger.error(f"Calendar configuration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calendar/room/configure")
async def configure_room_location(
    room_config: RoomLocationRequest,
    current_user= Depends(require_permission("admin"))
):
    """Configure this device's room location and capabilities"""
    try:
        calendar_service.configure_room_location(
            room_config.device_location,
            room_config.room_name,
            room_config.capacity,
            room_config.equipment
        )
        
        return {
            "status": "success",
            "room_location": room_config.device_location,
            "room_name": room_config.room_name,
            "capacity": room_config.capacity,
            "equipment": room_config.equipment
        }
        
    except Exception as e:
        logger.error(f"Room configuration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calendar/room/status")
async def get_room_availability_status(
    current_user= Depends(get_current_user)
):
    """Get current room availability and meeting status"""
    try:
        status = await calendar_service.get_room_availability_status()
        return status
        
    except Exception as e:
        logger.error(f"Room status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calendar/meeting/schedule")
async def schedule_meeting(
    meeting: MeetingCreateRequest,
):
    """Schedule a new meeting with automatic conflict detection"""
    try:
        from datetime import datetime
        
        # Parse ISO datetime strings
        start_time = datetime.fromisoformat(meeting.start_time.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(meeting.end_time.replace('Z', '+00:00'))
        
        # Schedule the meeting
        meeting_id = await calendar_service.schedule_meeting(
            meeting.title,
            start_time,
            end_time,
            meeting.attendees,
            meeting.location,
            meeting.description
        )
        
        if not meeting_id:
            # Check for conflicts
            conflicts = await calendar_service.check_conflicts(meeting.attendees, start_time, end_time)
            if conflicts:
                return {
                    "status": "conflict",
                    "conflicts": conflicts,
                    "message": "Meeting conflicts detected with attendees"
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to create meeting")
        
        return {
            "status": "success",
            "meeting_id": meeting_id,
            "title": meeting.title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "attendees": meeting.attendees
        }
        
    except Exception as e:
        logger.error(f"Meeting scheduling error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calendar/availability/{user_email}")
async def get_user_availability(
    user_email: str,
    start_time: str,
    end_time: str,
    current_user= Depends(get_current_user)
):
    """Get user's calendar availability for a time period"""
    try:
        from datetime import datetime
        
        # Parse datetime parameters
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        events = await calendar_service.get_user_availability(user_email, start_dt, end_dt)
        
        return {
            "user_email": user_email,
            "start_time": start_time,
            "end_time": end_time,
            "events": [
                {
                    "id": event.id,
                    "title": event.title,
                    "start_time": event.start_time.isoformat(),
                    "end_time": event.end_time.isoformat(),
                    "location": event.location,
                    "status": event.status
                }
                for event in events
            ]
        }
        
    except Exception as e:
        logger.error(f"Availability check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calendar/meeting/suggest-times")
async def suggest_meeting_times(
    attendees: List[str],
    duration_minutes: int,
    preferred_start: str,
    preferred_end: str,
    current_user= Depends(get_current_user)
):
    """Suggest available meeting times for all attendees"""
    try:
        from datetime import datetime, timedelta
        
        # Parse datetime parameters
        start_dt = datetime.fromisoformat(preferred_start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(preferred_end.replace('Z', '+00:00'))
        
        suggestions = await calendar_service.suggest_meeting_times(
            attendees, duration_minutes, start_dt, end_dt
        )
        
        return {
            "attendees": attendees,
            "duration_minutes": duration_minutes,
            "preferred_window": {
                "start": preferred_start,
                "end": preferred_end
            },
            "suggestions": [
                {
                    "start_time": suggestion.isoformat(),
                    "end_time": (suggestion + timedelta(minutes=duration_minutes)).isoformat()
                }
                for suggestion in suggestions
            ]
        }
        
    except Exception as e:
        logger.error(f"Meeting suggestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calendar/conflicts/check")
async def check_meeting_conflicts(
    attendees: List[str],
    start_time: str,
    end_time: str,
    current_user= Depends(get_current_user)
):
    """Check for calendar conflicts with proposed meeting time"""
    try:
        from datetime import datetime
        
        # Parse datetime parameters
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        conflicts = await calendar_service.check_conflicts(attendees, start_dt, end_dt)
        
        return {
            "has_conflicts": len(conflicts) > 0,
            "conflicts": conflicts,
            "meeting_time": {
                "start": start_time,
                "end": end_time
            },
            "attendees": attendees
        }
        
    except Exception as e:
        logger.error(f"Conflict check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calendar/status")
async def get_calendar_integration_status(
    current_user= Depends(get_current_user)
):
    """Get status of calendar integration services"""
    try:
        status = {
            "microsoft365": {
                "configured": calendar_service.microsoft_service is not None,
                "authenticated": False
            },
            "google": {
                "configured": calendar_service.google_service is not None,
                "authenticated": False
            },
            "room_configured": len(calendar_service.room_locations) > 0,
            "room_locations": calendar_service.room_locations
        }
        
        # Test authentication status
        if calendar_service.microsoft_service:
            try:
                await calendar_service.microsoft_service._ensure_authenticated()
                status["microsoft365"]["authenticated"] = True
            except:
                pass
                
        if calendar_service.google_service:
            try:
                await calendar_service.google_service._ensure_authenticated()
                status["google"]["authenticated"] = True
            except:
                pass
        
        return status
        
    except Exception as e:
        logger.error(f"Calendar status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# LLM Service Endpoints

@app.get("/api/llm/status")
async def get_llm_status(current_user= Depends(require_permission("session.read"))):
    """Get status of available LLM providers"""
    try:
        return llm_summarization_service.get_status()
    except Exception as e:
        logger.error(f"LLM status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/llm/test")
async def test_llm_service(
    test_prompt: str = "Summarize this brief test: This is a test meeting transcript. The team discussed project status and made decisions about next steps.",
    provider: str = "auto",
    current_user= Depends(require_permission("session.read"))
):
    """Test LLM service with a simple prompt"""
    try:
        # For testing, we'll use a simple executive summary generation
        mock_session_data = {
            "meeting_type": "test",
            "duration_seconds": 300,
            "speakers": [{"speaker_id": "test_speaker_1"}]
        }
        
        result = await llm_summarization_service._generate_executive_summary(
            transcript=test_prompt,
            session_data=mock_session_data,
            style="executive"
        )
        
        return {
            "success": True,
            "provider_used": provider,
            "result": result,
            "available_providers": llm_summarization_service.get_available_providers()
        }
    except Exception as e:
        logger.error(f"LLM test error: {e}")
        return {
            "success": False,
            "error": str(e),
            "available_providers": llm_summarization_service.get_available_providers()
        }

# Webhook Management Endpoints

@app.post("/api/webhooks")
async def create_webhook_endpoint(
    webhook: WebhookEndpointRequest,
    current_user= Depends(require_permission("admin"))
):
    """Create a new webhook endpoint"""
    try:
        import uuid
        
        endpoint = WebhookEndpoint(
            id=str(uuid.uuid4()),
            name=webhook.name,
            url=webhook.url,
            secret=webhook.secret,
            events=webhook.events,
            active=webhook.active,
            headers=webhook.headers or {},
            retry_count=webhook.retry_count,
            timeout=webhook.timeout
        )
        
        success = webhook_service.add_endpoint(endpoint)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create webhook endpoint")
        
        return {
            "status": "success",
            "endpoint": {
                "id": endpoint.id,
                "name": endpoint.name,
                "url": endpoint.url,
                "events": endpoint.events,
                "active": endpoint.active
            }
        }
        
    except Exception as e:
        logger.error(f"Webhook creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/webhooks")
async def get_webhook_endpoints(
    current_user= Depends(get_current_user)
):
    """Get all webhook endpoints"""
    try:
        endpoints = webhook_service.get_endpoints()
        
        return {
            "endpoints": [
                {
                    "id": endpoint.id,
                    "name": endpoint.name,
                    "url": endpoint.url,
                    "events": endpoint.events,
                    "active": endpoint.active,
                    "retry_count": endpoint.retry_count,
                    "timeout": endpoint.timeout
                }
                for endpoint in endpoints
            ],
            "available_events": list(webhook_service.EVENT_TYPES.keys()),
            "event_descriptions": webhook_service.EVENT_TYPES
        }
        
    except Exception as e:
        logger.error(f"Webhook list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/webhooks/{endpoint_id}")
async def get_webhook_endpoint(
    endpoint_id: str,
    current_user= Depends(get_current_user)
):
    """Get specific webhook endpoint"""
    try:
        endpoint = webhook_service.get_endpoint(endpoint_id)
        if not endpoint:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")
        
        stats = webhook_service.get_endpoint_stats(endpoint_id)
        
        return {
            "endpoint": {
                "id": endpoint.id,
                "name": endpoint.name,
                "url": endpoint.url,
                "events": endpoint.events,
                "active": endpoint.active,
                "retry_count": endpoint.retry_count,
                "timeout": endpoint.timeout,
                "headers": endpoint.headers
            },
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/webhooks/{endpoint_id}")
async def update_webhook_endpoint(
    endpoint_id: str,
    updates: WebhookEndpointUpdate,
    current_user= Depends(require_permission("admin"))
):
    """Update webhook endpoint configuration"""
    try:
        update_dict = {k: v for k, v in updates.dict().items() if v is not None}
        
        success = webhook_service.update_endpoint(endpoint_id, update_dict)
        if not success:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")
        
        endpoint = webhook_service.get_endpoint(endpoint_id)
        
        return {
            "status": "success",
            "endpoint": {
                "id": endpoint.id,
                "name": endpoint.name,
                "url": endpoint.url,
                "events": endpoint.events,
                "active": endpoint.active
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/webhooks/{endpoint_id}")
async def delete_webhook_endpoint(
    endpoint_id: str,
    current_user= Depends(require_permission("admin"))
):
    """Delete webhook endpoint"""
    try:
        success = webhook_service.remove_endpoint(endpoint_id)
        if not success:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")
        
        return {"status": "success", "message": "Webhook endpoint deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/webhooks/{endpoint_id}/test")
async def test_webhook_endpoint(
    endpoint_id: str,
    current_user= Depends(require_permission("admin"))
):
    """Test webhook endpoint with a test event"""
    try:
        result = await webhook_service.test_endpoint(endpoint_id)
        
        return {
            "test_result": result,
            "success": result.get('success', False),
            "message": "Test webhook sent" if result.get('success') else "Test webhook failed"
        }
        
    except Exception as e:
        logger.error(f"Webhook test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/webhooks/events/log")
async def get_webhook_event_log(
    limit: int = 100,
    event_type: Optional[str] = None,
    current_user= Depends(get_current_user)
):
    """Get recent webhook events"""
    try:
        events = webhook_service.get_event_log(limit, event_type)
        
        return {
            "events": [
                {
                    "event_type": event.event_type,
                    "event_id": event.event_id,
                    "timestamp": event.timestamp.isoformat(),
                    "session_id": event.session_id,
                    "data": event.data
                }
                for event in events
            ],
            "total": len(events),
            "available_types": list(webhook_service.EVENT_TYPES.keys())
        }
        
    except Exception as e:
        logger.error(f"Webhook event log error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/webhooks/stats")
async def get_webhook_stats(
    current_user= Depends(get_current_user)
):
    """Get webhook system statistics"""
    try:
        endpoints = webhook_service.get_endpoints()
        event_log = webhook_service.get_event_log()
        
        stats = {
            "total_endpoints": len(endpoints),
            "active_endpoints": len([e for e in endpoints if e.active]),
            "total_events_sent": len(event_log),
            "recent_events": len([e for e in event_log if (datetime.now() - e.timestamp).seconds < 3600]),
            "event_types": list(webhook_service.EVENT_TYPES.keys()),
            "endpoint_stats": [
                webhook_service.get_endpoint_stats(endpoint.id)
                for endpoint in endpoints
            ]
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Webhook stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Enhanced Recording Session - Transcription Service Integration

@app.post("/api/recording-sessions/{session_id}/switch-model")
async def switch_model(
    session_id: str,
    model_id: str,
    current_user= Depends(require_permission("session.update"))
):
    """Switch transcription model during an active session"""
    try:
        # Verify session exists
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Only allow model switching for active sessions
        if session.status != "active":
            raise HTTPException(status_code=400, detail="Can only switch models during active recording")
        
        # Switch the transcription model
        success = transcription_service.switch_model(model_id)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to switch to model {model_id}")
        
        # Get updated model info
        model_info = transcription_service.get_current_model_info()
        
        # Log the model switch for this session
        logger.info(f"🔄 Switched transcription model to {model_id} for session {session_id}")
        
        # Notify WebSocket clients about the model change
        if session_id in active_connections:
            asyncio.create_task(
                active_connections[session_id].send_text(
                    json.dumps({
                        "type": "model_changed",
                        "model_info": model_info,
                        "timestamp": datetime.now().isoformat()
                    })
                )
            )
        
        return {
            "success": True,
            "session_id": session_id,
            "new_model": model_id,
            "model_info": model_info,
            "message": f"Successfully switched to {model_info.get('name', model_id)}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching model for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recording-sessions/{session_id}/transcription-models")
async def get_session_transcription_models(
    session_id: str,
    current_user= Depends(require_permission("session.read"))
):
    """Get available transcription models and current model for a session"""
    try:
        # Verify session exists
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get current model info
        current_model_info = transcription_service.get_current_model_info()
        
        # Get available models
        available_models = transcription_service.get_available_models()
        
        # Get session transcription statistics
        transcriptions = session_manager.get_session_transcriptions(session_id)
        model_usage = {}
        for transcription in transcriptions:
            model = transcription.model_used or "unknown"
            if model not in model_usage:
                model_usage[model] = {"count": 0, "total_confidence": 0.0}
            model_usage[model]["count"] += 1
            model_usage[model]["total_confidence"] += transcription.confidence
        
        # Calculate average confidence per model
        for model, stats in model_usage.items():
            if stats["count"] > 0:
                stats["average_confidence"] = stats["total_confidence"] / stats["count"]
            else:
                stats["average_confidence"] = 0.0
        
        return {
            "session_id": session_id,
            "current_model": current_model_info,
            "available_models": available_models,
            "session_status": session.status,
            "can_switch_model": session.status == "active",
            "model_usage_statistics": model_usage,
            "total_transcriptions": len(transcriptions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcription models for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))