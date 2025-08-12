"""
API endpoints for AI-powered meeting notes generation
"""

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime
import redis.asyncio as redis

from database.database import get_db
from services.meeting_notes_service import MeetingNotesService, MeetingNotesBuffer
from auth.dependencies import get_current_user_optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meeting-notes", tags=["meeting-notes"])

# Global storage for notes buffers (per session)
notes_buffers: Dict[str, MeetingNotesBuffer] = {}

# Initialize services
meeting_notes_service = None
redis_client = None


async def get_meeting_notes_service():
    """Get or create meeting notes service instance"""
    global meeting_notes_service
    if not meeting_notes_service:
        try:
            # Try to connect to Redis for caching
            global redis_client
            redis_client = await redis.from_url("redis://localhost:6379", decode_responses=True)
            await redis_client.ping()
            logger.info("Connected to Redis for caching")
        except Exception as e:
            logger.warning(f"Redis not available for caching: {e}")
            redis_client = None
        
        # Use Granite model configuration (available in our Ollama container)
        model_config = {
            "provider": "ollama",
            "model_name": "granite3.3:8b",
            "api_endpoint": "http://localhost:11434"
        }
        
        meeting_notes_service = MeetingNotesService(
            model_config=model_config,
            redis_client=redis_client
        )
        
        # Test connection
        if await meeting_notes_service.test_connection():
            logger.info("Meeting notes service initialized successfully with Granite model")
        else:
            logger.warning("Meeting notes service connection test failed - notes generation may not work")
    
    return meeting_notes_service


class GenerateNotesRequest(BaseModel):
    session_id: str
    transcript: str
    incremental: bool = False
    previous_notes: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    session_id: str
    query: str
    transcript: str
    history: Optional[list] = None


@router.post("/generate")
async def generate_meeting_notes(
    request: GenerateNotesRequest,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Generate meeting notes from transcript"""
    try:
        service = await get_meeting_notes_service()
        
        if request.incremental and request.previous_notes:
            notes = await service.generate_incremental_notes(
                request.transcript,
                request.previous_notes
            )
        else:
            notes = await service.generate_meeting_notes(request.transcript)
        
        # Store in database if needed
        # TODO: Add database storage for notes
        
        return {
            "success": True,
            "notes": notes,
            "session_id": request.session_id
        }
        
    except Exception as e:
        logger.error(f"Error generating meeting notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def chat_with_meeting(
    request: ChatRequest,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Chat about a specific meeting"""
    try:
        service = await get_meeting_notes_service()
        
        # For now, return a simple response - chat functionality can be added later
        response = f"Chat functionality coming soon. You asked: {request.query}"
        
        return {
            "success": True,
            "response": response,
            "session_id": request.session_id
        }
        
    except Exception as e:
        logger.error(f"Error in meeting chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/meeting-notes/{session_id}")
async def meeting_notes_websocket(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time meeting notes updates"""
    await websocket.accept()
    logger.info(f"Meeting notes WebSocket connected for session {session_id}")
    
    # Get or create notes buffer for this session
    if session_id not in notes_buffers:
        service = await get_meeting_notes_service()
        notes_buffers[session_id] = MeetingNotesBuffer(
            session_id=session_id,
            service=service
        )
    
    buffer = notes_buffers[session_id]
    
    try:
        # Subscribe to Redis for transcript updates
        if redis_client:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(f"transcription:{session_id}")
            
            # Listen for transcript updates
            async def listen_for_transcripts():
                async for message in pubsub.listen():
                    if message['type'] == 'message':
                        try:
                            data = json.loads(message['data'])
                            
                            # Add segment to buffer
                            segment = {
                                'text': data.get('text', ''),
                                'speaker': data.get('speaker'),
                                'timestamp': data.get('timestamp')
                            }
                            
                            # Check if we should generate notes
                            notes = await buffer.add_segment(segment)
                            
                            if notes:
                                # Send notes update to client
                                await websocket.send_json({
                                    'type': 'notes_update',
                                    'notes': notes
                                })
                                logger.info(f"Sent notes update for session {session_id}")
                            
                        except Exception as e:
                            logger.error(f"Error processing transcript: {e}")
            
            # Start listening in background
            asyncio.create_task(listen_for_transcripts())
        
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages
                data = await websocket.receive_json()
                
                if data.get('type') == 'request_update':
                    # Force generate notes
                    await websocket.send_json({
                        'type': 'generating',
                        'message': 'Generating notes...'
                    })
                    
                    notes = await buffer.force_generation()
                    if notes:
                        await websocket.send_json({
                            'type': 'notes_update',
                            'notes': notes
                        })
                
                elif data.get('type') == 'add_segment':
                    # Manually add a segment
                    segment = data.get('segment', {})
                    notes = await buffer.add_segment(segment)
                    
                    if notes:
                        await websocket.send_json({
                            'type': 'notes_update',
                            'notes': notes
                        })
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_json({
                    'type': 'error',
                    'message': str(e)
                })
                
    except Exception as e:
        logger.error(f"Meeting notes WebSocket error: {e}")
        try:
            await websocket.send_json({
                'type': 'error',
                'message': 'Internal server error'
            })
        except:
            pass
    finally:
        # Cleanup
        if redis_client and 'pubsub' in locals():
            await pubsub.unsubscribe()
            await pubsub.close()
        
        logger.info(f"Meeting notes WebSocket disconnected for session {session_id}")


@router.get("/sessions/{session_id}")
async def get_session_notes(
    session_id: str,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Get the latest notes for a session"""
    try:
        # Check if we have notes in buffer
        if session_id in notes_buffers:
            buffer = notes_buffers[session_id]
            if buffer.current_notes:
                return {
                    "success": True,
                    "notes": buffer.current_notes,
                    "session_id": session_id
                }
        
        # TODO: Check database for stored notes
        
        return {
            "success": False,
            "message": "No notes available for this session",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error getting session notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def clear_session_notes(
    session_id: str,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Clear notes buffer for a session"""
    try:
        if session_id in notes_buffers:
            del notes_buffers[session_id]
            logger.info(f"Cleared notes buffer for session {session_id}")
        
        return {
            "success": True,
            "message": "Notes buffer cleared",
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error clearing session notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-gemma")
async def test_gemma_connection(
    current_user=Depends(get_current_user_optional)
):
    """Test connection to Gemma service"""
    try:
        service = await get_meeting_notes_service()
        connected = await service.test_connection()
        
        if connected:
            # Try a simple generation
            test_transcript = "This is a test meeting. We discussed testing the AI system."
            notes = await service.generate_meeting_notes(test_transcript)
            
            return {
                "success": True,
                "connected": True,
                "test_notes": notes,
                "message": "Gemma service is working correctly"
            }
        else:
            return {
                "success": False,
                "connected": False,
                "message": "Could not connect to Gemma service"
            }
            
    except Exception as e:
        logger.error(f"Error testing Gemma connection: {e}")
        return {
            "success": False,
            "connected": False,
            "error": str(e),
            "message": "Gemma service test failed"
        }