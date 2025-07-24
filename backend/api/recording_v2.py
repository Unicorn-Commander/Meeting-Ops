"""
Improved Recording API with better error handling and session management
"""
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session as DBSession
from typing import Optional, Dict
import logging
import asyncio
from datetime import datetime

from database.database import get_db
from auth.models import User
from database.models import Session as RecordingSession
from auth.dependencies import get_current_user, require_permission
from services.audio_session_manager import AudioSessionManager
from services.session_manager import SessionManager
from services.transcription_service import TranscriptionService
from services.audio_recording_service import AudioRecordingService
from services.file_storage_service import FileStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/recording", tags=["recording_v2"])

# Service instances
audio_session_manager = AudioSessionManager()
session_manager = SessionManager()
transcription_service = TranscriptionService()
audio_recording_service = AudioRecordingService()
file_storage_service = FileStorageService()

# Active WebSocket connections
active_connections: Dict[str, WebSocket] = {}

# Session state tracking
session_states: Dict[str, dict] = {}


class RecordingError(Exception):
    """Custom exception for recording errors"""
    pass


async def cleanup_session(session_id: str, error: Optional[str] = None):
    """Clean up a session after error or completion"""
    try:
        # Stop audio session
        audio_session_manager.stop_session(session_id)
        
        # Stop file recording
        audio_recording_service.stop_recording(session_id)
        
        # Update session status
        if error:
            session_manager.update_session_status(session_id, "failed")
            logger.error(f"Session {session_id} failed: {error}")
        else:
            session_manager.update_session_status(session_id, "completed")
            
        # Remove from active connections
        if session_id in active_connections:
            try:
                await active_connections[session_id].close()
            except:
                pass
            del active_connections[session_id]
            
        # Remove session state
        if session_id in session_states:
            del session_states[session_id]
            
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")


@router.post("/sessions/{session_id}/start")
async def start_recording_v2(
    session_id: str,
    current_user: User = Depends(require_permission("session.update")),
    db: DBSession = Depends(get_db)
):
    """Start recording with improved error handling"""
    try:
        # Check if session exists
        session = db.query(RecordingSession).filter_by(session_id=session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        # Check if already recording
        if session_id in session_states:
            if session_states[session_id].get('status') == 'recording':
                return {"success": True, "message": "Already recording", "session": session.to_dict()}
                
        # Initialize session state
        session_states[session_id] = {
            'status': 'starting',
            'start_time': datetime.utcnow(),
            'error_count': 0,
            'user_id': current_user.id
        }
        
        # Create audio session
        audio_session = audio_session_manager.create_session(session_id)
        if not audio_session:
            raise RecordingError("Failed to create audio session")
            
        # Start file recording
        audio_file_path = await file_storage_service.save_audio_stream(
            session_id=session_id,
            format="wav"
        )
        
        success = audio_recording_service.start_recording(
            file_path=audio_file_path,
            sample_rate=16000,
            channels=1
        )
        
        if not success:
            raise RecordingError("Failed to start audio recording")
            
        # Register callbacks
        def handle_audio_data(sess_id: str, audio_bytes: bytes):
            try:
                # Write to file
                audio_recording_service.write_audio_chunk(sess_id, audio_bytes)
                
                # Process for transcription
                if transcription_service.is_ready:
                    result = transcription_service.process_audio_chunk(audio_bytes)
                    if result:
                        # Store transcription
                        session_manager.add_transcription(
                            session_id=sess_id,
                            text=result.get('text', ''),
                            confidence=result.get('confidence', 0.0),
                            speaker_id=result.get('speaker_id')
                        )
                        
                        # Send to WebSocket if connected
                        if sess_id in active_connections:
                            asyncio.create_task(send_transcription(sess_id, result))
                            
            except Exception as e:
                logger.error(f"Error handling audio data: {e}")
                session_states[sess_id]['error_count'] += 1
                
        def handle_session_error(sess_id: str, error_msg: str):
            logger.error(f"Session {sess_id} error: {error_msg}")
            asyncio.create_task(cleanup_session(sess_id, error_msg))
            
        def handle_session_timeout(sess_id: str):
            logger.warning(f"Session {sess_id} timeout")
            asyncio.create_task(cleanup_session(sess_id, "Session timeout"))
            
        # Register callbacks
        audio_session_manager.register_session_callback(session_id, 'audio_data', handle_audio_data)
        audio_session_manager.register_global_callback('session_error', handle_session_error)
        audio_session_manager.register_global_callback('session_timeout', handle_session_timeout)
        
        # Update session status
        session = session_manager.update_session_status(session_id, "active")
        session_states[session_id]['status'] = 'recording'
        
        logger.info(f"Started recording for session {session_id}")
        
        return {
            "success": True,
            "session": session.to_dict(),
            "audio_file": audio_file_path
        }
        
    except RecordingError as e:
        await cleanup_session(session_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        logger.error(f"Unexpected error starting recording: {e}")
        await cleanup_session(session_id, str(e))
        raise HTTPException(status_code=500, detail="Failed to start recording")


@router.post("/sessions/{session_id}/stop")
async def stop_recording_v2(
    session_id: str,
    current_user: User = Depends(require_permission("session.update")),
    db: DBSession = Depends(get_db)
):
    """Stop recording with proper cleanup"""
    try:
        # Check session state
        if session_id not in session_states:
            return {"success": True, "message": "Session not active"}
            
        session_state = session_states[session_id]
        
        # Check ownership
        if session_state['user_id'] != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Not authorized to stop this session")
            
        # Clean up session
        await cleanup_session(session_id)
        
        # Get final session data
        session = db.query(RecordingSession).filter_by(session_id=session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        return {
            "success": True,
            "session": session.to_dict(),
            "duration": (datetime.utcnow() - session_state['start_time']).total_seconds()
        }
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error stopping recording: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop recording")


@router.get("/sessions/{session_id}/status")
async def get_recording_status(
    session_id: str,
    current_user: User = Depends(require_permission("session.read"))
):
    """Get detailed recording status"""
    try:
        # Get session state
        if session_id not in session_states:
            return {
                "active": False,
                "status": "not_recording"
            }
            
        state = session_states[session_id]
        
        # Get audio session info
        audio_info = audio_session_manager.get_session_info(session_id)
        
        return {
            "active": True,
            "status": state['status'],
            "start_time": state['start_time'].isoformat(),
            "duration": (datetime.utcnow() - state['start_time']).total_seconds(),
            "error_count": state['error_count'],
            "audio_info": audio_info
        }
        
    except Exception as e:
        logger.error(f"Error getting recording status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")


@router.websocket("/sessions/{session_id}/stream")
async def websocket_stream_v2(
    websocket: WebSocket,
    session_id: str,
    token: Optional[str] = None
):
    """WebSocket endpoint with authentication"""
    try:
        # Verify token
        if not token:
            await websocket.close(code=4001, reason="Authentication required")
            return
            
        # Verify JWT token
        try:
            from auth.utils import decode_token
            from auth.service import AuthService
            
            payload = decode_token(token)
            if not payload or payload.get("type") != "access":
                await websocket.close(code=4001, reason="Invalid token")
                return
            
            user_id = payload.get("sub")
            if not user_id:
                await websocket.close(code=4001, reason="Invalid user")
                return
            
            # Get user from database
            user = AuthService.get_user_by_id(db, int(user_id))
            if not user or not user.is_active:
                await websocket.close(code=4001, reason="User not found or inactive")
                return
                
        except Exception as e:
            logger.error(f"WebSocket authentication failed: {e}")
            await websocket.close(code=4001, reason="Authentication failed")
            return
        
        await websocket.accept()
        active_connections[session_id] = websocket
        
        # Update session state with authenticated user
        if session_id in session_states:
            session_states[session_id]['user_id'] = user.id
            session_states[session_id]['username'] = user.username
        
        logger.info(f"WebSocket connected for session {session_id} by user {user.username}")
        
        # Send initial status
        if session_id in session_states:
            await websocket.send_json({
                "type": "status",
                "data": {
                    "recording": True,
                    "start_time": session_states[session_id]['start_time'].isoformat()
                }
            })
            
        # Keep connection alive
        try:
            while True:
                # Wait for client messages (mainly ping/pong)
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
                    
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for session {session_id}")
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        
    finally:
        if session_id in active_connections:
            del active_connections[session_id]


async def send_transcription(session_id: str, transcription: dict):
    """Send transcription to WebSocket client"""
    if session_id in active_connections:
        try:
            await active_connections[session_id].send_json({
                "type": "transcription",
                "data": transcription
            })
        except Exception as e:
            logger.error(f"Error sending transcription: {e}")


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "services": {
            "audio_sessions": len(audio_session_manager.get_active_sessions()),
            "websocket_connections": len(active_connections),
            "active_recordings": len(session_states),
            "transcription_ready": transcription_service.is_ready
        }
    }