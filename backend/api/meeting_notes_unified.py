"""
Unified Meeting Notes API
Works with both Gemma service and our new decoupled model system
"""

import asyncio
import json
import logging
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from datetime import datetime
import redis.asyncio as redis

try:
    from database.database import get_db
except ImportError:
    # Fallback if database module is not available
    def get_db():
        return None
from services.meeting_notes_service import MeetingNotesService, MeetingNotesBuffer as NewMeetingNotesBuffer
from services.llm_service import GemmaService, MeetingNotesBuffer as GemmaMeetingNotesBuffer
try:
    from auth.dependencies import get_current_user_optional
except ImportError:
    # Fallback for testing
    def get_current_user_optional():
        return None
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meeting-notes-unified", tags=["unified-meeting-notes"])

# Global storage for notes buffers (per session)
notes_buffers: Dict[str, Any] = {}

# Initialize services
meeting_notes_service = None
gemma_service = None
redis_client = None
current_provider = "granite"  # "granite", "phi4", or "gemma"


async def get_unified_service():
    """Get the appropriate meeting notes service based on configuration"""
    global meeting_notes_service, gemma_service, redis_client, current_provider
    
    # Initialize Redis once
    if not redis_client:
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6381")
            redis_client = await redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info("Connected to Redis for caching")
        except Exception as e:
            logger.warning(f"Redis not available for caching: {e}")
            redis_client = None
    
    if current_provider == "granite":
        if not meeting_notes_service:
            # Use Granite model configuration
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
                logger.warning("Granite model not available, falling back to Phi4")
                current_provider = "phi4"
                return await get_unified_service()
        
        return meeting_notes_service
    
    elif current_provider == "phi4":
        if not meeting_notes_service:
            # Use Phi4-mini model configuration (faster, smaller model)
            model_config = {
                "provider": "ollama",
                "model_name": "phi4-mini:3.8b",
                "api_endpoint": "http://localhost:11434"
            }
            
            meeting_notes_service = MeetingNotesService(
                model_config=model_config,
                redis_client=redis_client
            )
            
            # Test connection
            if await meeting_notes_service.test_connection():
                logger.info("Meeting notes service initialized successfully with Phi4-mini model")
            else:
                logger.warning("Phi4-mini model not available, falling back to Gemma")
                current_provider = "gemma"
                return await get_unified_service()
        
        return meeting_notes_service
    
    else:  # gemma
        if not gemma_service:
            try:
                gemma_service = GemmaService(redis_client=redis_client)
                
                # Test connection (this might fail if gemma3n:e4b is not available)
                if await gemma_service.test_connection():
                    logger.info("Gemma service initialized successfully")
                else:
                    logger.warning("Gemma service connection test failed")
            except Exception as e:
                logger.error(f"Failed to initialize Gemma service: {e}")
                # Fall back to Granite
                current_provider = "granite"
                return await get_unified_service()
        
        return gemma_service


class GenerateNotesRequest(BaseModel):
    session_id: str
    transcript: str
    incremental: bool = False
    previous_notes: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    session_id: str
    query: str
    transcript: Optional[str] = None
    history: List[Dict[str, str]] = []


@router.post("/generate")
async def generate_meeting_notes(
    request: GenerateNotesRequest,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Generate meeting notes from transcript using the available model"""
    try:
        service = await get_unified_service()
        
        if hasattr(service, 'generate_incremental_notes') and request.incremental and request.previous_notes:
            # New service with incremental support
            notes = await service.generate_incremental_notes(
                request.transcript,
                request.previous_notes
            )
        else:
            # Both services support generate_meeting_notes
            notes = await service.generate_meeting_notes(request.transcript)
        
        return {
            "success": True,
            "notes": notes,
            "session_id": request.session_id,
            "provider": current_provider
        }
        
    except Exception as e:
        logger.error(f"Error generating meeting notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/meeting-notes/{session_id}")
async def meeting_notes_websocket(
    websocket: WebSocket,
    session_id: str
):
    """WebSocket endpoint for real-time meeting notes updates"""
    await websocket.accept()
    logger.info(f"Meeting notes WebSocket connected for session {session_id} using {current_provider}")
    
    # Get or create notes buffer for this session
    if session_id not in notes_buffers:
        service = await get_unified_service()
        
        if current_provider == "granite":
            notes_buffers[session_id] = NewMeetingNotesBuffer(
                session_id=session_id,
                service=service
            )
        else:  # gemma
            notes_buffers[session_id] = GemmaMeetingNotesBuffer(
                gemma_service=service,
                buffer_duration=30,
                min_words=50
            )
    
    buffer = notes_buffers[session_id]
    
    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "message": f"Connected to meeting notes service using {current_provider}",
            "provider": current_provider
        })
        
        # Main WebSocket loop
        while True:
            try:
                # Check for automatic updates
                if hasattr(buffer, 'should_update_notes') and buffer.should_update_notes():
                    await websocket.send_json({"type": "generating"})
                    
                    notes = await buffer.update_notes()
                    if notes:
                        await websocket.send_json({
                            "type": "notes_update",
                            "notes": notes,
                            "provider": current_provider,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                
                # Listen for incoming messages
                data = await websocket.receive_json()
                
                if data.get("type") == "transcript_update":
                    text = data.get("text", "")
                    if text.strip():
                        # Add to buffer
                        if hasattr(buffer, 'add_transcript'):
                            buffer.add_transcript(text)
                        elif hasattr(buffer, 'add_text'):
                            buffer.add_text(text)
                        
                        await websocket.send_json({
                            "type": "transcript_received",
                            "word_count": len(text.split())
                        })
                
                elif data.get("type") == "force_update":
                    await websocket.send_json({"type": "generating"})
                    
                    if hasattr(buffer, 'update_notes'):
                        notes = await buffer.update_notes(force=True)
                    elif hasattr(buffer, 'generate_notes'):
                        notes = await buffer.generate_notes()
                    
                    if notes:
                        await websocket.send_json({
                            "type": "notes_update",
                            "notes": notes,
                            "provider": current_provider,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
                break
                
    except Exception as e:
        logger.error(f"Meeting notes WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Service error occurred"
            })
        except:
            pass
    finally:
        # Clean up buffer
        if session_id in notes_buffers:
            if hasattr(notes_buffers[session_id], 'clear'):
                notes_buffers[session_id].clear()
        logger.info(f"Meeting notes WebSocket disconnected for session {session_id}")


@router.post("/switch-provider")
async def switch_provider(
    provider: str,
    current_user=Depends(get_current_user_optional)
):
    """Switch between Granite and Gemma providers"""
    global current_provider, meeting_notes_service, gemma_service
    
    if provider not in ["granite", "phi4", "gemma"]:
        raise HTTPException(status_code=400, detail="Provider must be 'granite', 'phi4', or 'gemma'")
    
    old_provider = current_provider
    current_provider = provider
    
    # Reset services to force re-initialization
    if provider in ["granite", "phi4"]:
        meeting_notes_service = None
    else:
        gemma_service = None
    
    # Test the new provider
    try:
        service = await get_unified_service()
        if hasattr(service, 'test_connection'):
            connected = await service.test_connection()
            if not connected:
                # Revert on failure
                current_provider = old_provider
                raise HTTPException(status_code=503, detail=f"{provider} provider is not available")
        
        return {
            "success": True,
            "provider": current_provider,
            "message": f"Switched to {provider} provider"
        }
        
    except Exception as e:
        # Revert on error
        current_provider = old_provider
        raise HTTPException(status_code=503, detail=f"Failed to switch to {provider}: {str(e)}")


@router.get("/status")
async def get_status(
    current_user=Depends(get_current_user_optional)
):
    """Get current provider status"""
    try:
        service = await get_unified_service()
        connected = False
        
        if hasattr(service, 'test_connection'):
            connected = await service.test_connection()
        
        return {
            "current_provider": current_provider,
            "connected": connected,
            "active_sessions": len(notes_buffers),
            "service_type": service.__class__.__name__
        }
        
    except Exception as e:
        return {
            "current_provider": current_provider,
            "connected": False,
            "error": str(e),
            "active_sessions": len(notes_buffers)
        }


@router.post("/test")
async def test_current_provider(
    current_user=Depends(get_current_user_optional)
):
    """Test the current provider with a sample transcript"""
    try:
        service = await get_unified_service()
        
        # Test connection
        if hasattr(service, 'test_connection'):
            connected = await service.test_connection()
            if not connected:
                return {
                    "success": False,
                    "provider": current_provider,
                    "error": "Provider connection test failed"
                }
        
        # Test generation
        test_transcript = "This is a test meeting. We discussed the quarterly budget allocation and decided that Sarah will lead the marketing campaign. The deadline is Friday."
        
        notes = await service.generate_meeting_notes(test_transcript)
        
        return {
            "success": True,
            "provider": current_provider,
            "notes": notes,
            "service_type": service.__class__.__name__
        }
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return {
            "success": False,
            "provider": current_provider,
            "error": str(e)
        }