"""
Enhanced WebSocket endpoint with automatic summarization
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
import json
import asyncio
from typing import Dict, Set, Optional, List
import logging
from datetime import datetime

from services.whisperx_npu_service import whisperx_service
from services.auto_summarization_service import auto_summarization_service
from services.unified_agent_service import unified_agent_service
from services.system_service import SystemService
from services.websocket_registry import websocket_registry

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active WebSocket connections for auto-summary endpoint
active_connections: Dict[str, Set[WebSocket]] = {}
# Track word counts for each session
session_word_counts: Dict[str, int] = {}


async def broadcast_progressive_summary(session_id: str, summary_data: Dict):
    """
    Broadcast progressive summary to all connected clients for a session
    """
    if session_id not in active_connections:
        logger.debug(f"No active connections for session {session_id}")
        return
    
    # Don't wrap if already a properly formatted message
    if isinstance(summary_data, dict) and summary_data.get("type") == "progressive_summary":
        message = summary_data  # Already formatted correctly
    else:
        # Legacy format - wrap it
        message = {
            "type": "progressive_summary",
            "session_id": session_id,
            "data": summary_data,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # Send to all connected clients for this session
    disconnected = set()
    for websocket in active_connections[session_id]:
        try:
            await websocket.send_json(message)
            logger.info(f"📡 Broadcast progressive summary to client for session {session_id}")
        except Exception as e:
            logger.debug(f"Failed to send to client: {e}")
            disconnected.add(websocket)
    
    # Clean up disconnected clients
    for ws in disconnected:
        active_connections[session_id].discard(ws)


@router.websocket("/ws/transcription-auto/{session_id}")
async def websocket_with_auto_summary(websocket: WebSocket, session_id: str):
    """
    Enhanced WebSocket endpoint that handles:
    1. Live transcription streaming
    2. Automatic periodic summarization (backend-controlled)
    3. Settings-based enable/disable of summarization
    """
    await websocket.accept()
    
    # Add to active connections
    if session_id not in active_connections:
        active_connections[session_id] = set()
    active_connections[session_id].add(websocket)
    
    logger.info(f"WebSocket connected for session {session_id} with auto-summary")
    
    # Callback function to send summaries via WebSocket
    async def send_summary_update(summary_data: Dict):
        try:
            await websocket.send_json(summary_data)
        except Exception as e:
            logger.error(f"Error sending summary update: {e}")
    
    try:
        # Send initial connection message
        settings = SystemService.load_settings()
        await websocket.send_json({
            "type": "connection",
            "message": "Connected to enhanced transcription stream",
            "session_id": session_id,
            "features": {
                "live_transcription": True,
                "auto_summarization": settings.enableLiveSummarization,
                "summary_trigger_mode": settings.summaryTriggerMode if settings.enableLiveSummarization else None,
                "summary_interval": settings.summaryUpdateInterval if settings.summaryTriggerMode == "time" else None,
                "summary_word_interval": settings.summaryWordCountInterval if settings.summaryTriggerMode == "word_count" else None,
                "final_summary_enabled": settings.enableFinalSummary
            }
        })
        
        # Start automatic summarization if enabled
        if settings.enableLiveSummarization:
            # Use unified agent service (simplified system)
            agent_started = await unified_agent_service.start_meeting_analysis(
                session_id,
                websocket_callback=send_summary_update
            )
            
            if agent_started:
                # Send progressive status
                await websocket.send_json({
                    "type": "progressive_summary_status",
                    "enabled": True,
                    "mode": "progressive",
                    "message": "Progressive AI summarization enabled"
                })
            else:
                # Fallback to legacy auto-summarization
                await auto_summarization_service.start_auto_summarization(
                    session_id,
                    websocket_callback=send_summary_update
                )
                
                # Send legacy status
                await websocket.send_json({
                    "type": "auto_summary_status",
                    "enabled": True,
                    "interval": settings.summaryUpdateInterval,
                    "message": f"Automatic summarization enabled (every {settings.summaryUpdateInterval} seconds)"
                })
        else:
            await websocket.send_json({
                "type": "auto_summary_status",
                "enabled": False,
                "message": "Automatic summarization is disabled"
            })
        
        # Main WebSocket loop
        while True:
            try:
                # Wait for messages from client
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data) if data != "ping" else {"type": "ping"}
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
                elif message.get("type") == "request_summary":
                    # Manual summary request
                    summary = await auto_summarization_service.force_summary(session_id)
                    if summary:
                        await websocket.send_json({
                            "type": "manual_summary",
                            "summary": summary,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    else:
                        await websocket.send_json({
                            "type": "summary_error",
                            "message": "Not enough content for summary"
                        })
                        
                elif message.get("type") == "toggle_auto_summary":
                    # Toggle auto-summarization on/off for this session
                    enabled = message.get("enabled", True)
                    
                    if enabled:
                        await auto_summarization_service.start_auto_summarization(
                            session_id,
                            websocket_callback=send_summary_update
                        )
                        await websocket.send_json({
                            "type": "auto_summary_status",
                            "enabled": True,
                            "message": "Auto-summarization enabled"
                        })
                    else:
                        await auto_summarization_service.stop_auto_summarization(session_id)
                        await websocket.send_json({
                            "type": "auto_summary_status",
                            "enabled": False,
                            "message": "Auto-summarization disabled"
                        })
                        
                elif message.get("type") == "get_status":
                    # Get current agent status
                    agent_status = unified_agent_service.get_agent_status()
                    if agent_status:
                        await websocket.send_json({
                            "type": "agent_status_response",
                            "status": agent_status
                        })
                    else:
                        # Fallback to legacy status
                        status = auto_summarization_service.get_status(session_id)
                        await websocket.send_json({
                            "type": "status_response",
                            "status": status
                        })
                    
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({
                    "type": "keepalive",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        # Clean up
        if session_id in active_connections:
            active_connections[session_id].discard(websocket)
            if not active_connections[session_id]:
                del active_connections[session_id]
        
        # Stop meeting analysis and get final summary
        final_results = await unified_agent_service.stop_meeting_analysis(session_id)
        
        # Also stop legacy auto-summarization service
        await auto_summarization_service.stop_auto_summarization(session_id)
        
        # Send final summary if available
        if final_results and final_results.get("final_summary"):
            try:
                await websocket.send_json({
                    "type": "final_summary",
                    "summary": final_results["final_summary"],
                    "meeting_title": final_results.get("meeting_title"),
                    "summary_count": final_results.get("summary_count", 0)
                })
            except Exception as e:
                logger.error(f"Error sending final summary: {e}")


async def broadcast_transcription_segment(session_id: str, segment: Dict):
    """
    Broadcast transcription segment to all connected clients
    This is called by the transcription service when new segments are available
    """
    # Store segment in session for auto-summarization
    try:
        from api.simple_recording_fixed import sessions
        if session_id in sessions:
            if "transcription_segments" not in sessions[session_id]:
                sessions[session_id]["transcription_segments"] = []
            sessions[session_id]["transcription_segments"].append(segment)
            
            # Also update the combined transcript
            if "transcript" not in sessions[session_id]:
                sessions[session_id]["transcript"] = ""
            sessions[session_id]["transcript"] += segment.get("text", "") + " "
    except Exception as e:
        logger.debug(f"Could not store segment in session: {e}")
    
    if session_id in active_connections:
        disconnected = set()
        
        # Calculate word count for the segment
        segment_text = segment.get("text", "")
        word_count = len(segment_text.split())
        
        # Update session word count
        if session_id not in session_word_counts:
            session_word_counts[session_id] = 0
        session_word_counts[session_id] += word_count
        
        for websocket in active_connections[session_id]:
            try:
                await websocket.send_json({
                    "type": "transcription",
                    "segment": segment,
                    "timestamp": datetime.utcnow().isoformat(),
                    "word_count": session_word_counts[session_id],  # Total words so far
                    "segment_word_count": word_count  # Words in this segment
                })
            except Exception as e:
                logger.error(f"Error broadcasting to websocket: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected websockets
        for ws in disconnected:
            active_connections[session_id].discard(ws)
    
    logger.debug(f"Broadcast transcription to {len(active_connections.get(session_id, []))} clients for session {session_id}")


@router.post("/api/auto-summary/control/{session_id}")
async def control_auto_summarization(
    session_id: str,
    action: str,
    enabled: Optional[bool] = None
):
    """
    REST endpoint to control auto-summarization
    
    Actions:
    - start: Start auto-summarization
    - stop: Stop auto-summarization
    - status: Get current status
    - force: Force generate a summary now
    """
    try:
        if action == "start":
            await auto_summarization_service.start_auto_summarization(session_id)
            return {"status": "started", "session_id": session_id}
            
        elif action == "stop":
            await auto_summarization_service.stop_auto_summarization(session_id)
            return {"status": "stopped", "session_id": session_id}
            
        elif action == "status":
            status = auto_summarization_service.get_status(session_id)
            return {"status": "success", "data": status}
            
        elif action == "force":
            summary = await auto_summarization_service.force_summary(session_id)
            if summary:
                return {"status": "success", "summary": summary}
            else:
                raise HTTPException(status_code=400, detail="Not enough content for summary")
                
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
            
    except Exception as e:
        logger.error(f"Error controlling auto-summarization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/auto-summary/settings")
async def get_auto_summary_settings():
    """Get current auto-summarization settings"""
    settings = SystemService.load_settings()
    return {
        "enableLiveSummarization": settings.enableLiveSummarization,
        "summaryTriggerMode": settings.summaryTriggerMode,
        "summaryUpdateInterval": settings.summaryUpdateInterval,
        "summaryWordCountInterval": settings.summaryWordCountInterval,
        "enableAutoSummary": settings.enableAutoSummary,
        "enableFinalSummary": settings.enableFinalSummary
    }


@router.put("/api/auto-summary/settings")
async def update_auto_summary_settings(
    enableLiveSummarization: Optional[bool] = None,
    summaryTriggerMode: Optional[str] = None,
    summaryUpdateInterval: Optional[int] = None,
    summaryWordCountInterval: Optional[int] = None,
    enableFinalSummary: Optional[bool] = None
):
    """Update auto-summarization settings"""
    try:
        settings = SystemService.load_settings()
        
        if enableLiveSummarization is not None:
            settings.enableLiveSummarization = enableLiveSummarization
        
        if summaryTriggerMode is not None:
            if summaryTriggerMode not in ["time", "word_count"]:
                raise HTTPException(status_code=400, detail="Invalid trigger mode. Must be 'time' or 'word_count'")
            settings.summaryTriggerMode = summaryTriggerMode
            
        if summaryUpdateInterval is not None:
            if summaryUpdateInterval < 10:
                raise HTTPException(status_code=400, detail="Time interval must be at least 10 seconds")
            if summaryUpdateInterval > 600:
                raise HTTPException(status_code=400, detail="Time interval cannot exceed 600 seconds")
            settings.summaryUpdateInterval = summaryUpdateInterval
        
        if summaryWordCountInterval is not None:
            if summaryWordCountInterval < 100:
                raise HTTPException(status_code=400, detail="Word count interval must be at least 100 words")
            if summaryWordCountInterval > 5000:
                raise HTTPException(status_code=400, detail="Word count interval cannot exceed 5000 words")
            settings.summaryWordCountInterval = summaryWordCountInterval
        
        if enableFinalSummary is not None:
            settings.enableFinalSummary = enableFinalSummary
        
        # Save settings
        SystemService.save_settings(settings)
        
        return {
            "status": "success",
            "settings": {
                "enableLiveSummarization": settings.enableLiveSummarization,
                "summaryTriggerMode": settings.summaryTriggerMode,
                "summaryUpdateInterval": settings.summaryUpdateInterval,
                "summaryWordCountInterval": settings.summaryWordCountInterval,
                "enableFinalSummary": settings.enableFinalSummary
            }
        }
        
    except Exception as e:
        logger.error(f"Error updating auto-summary settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Register the broadcast function with the registry when module loads
websocket_registry.register_broadcaster("auto_summary", broadcast_transcription_segment)
logger.info("Registered auto-summary WebSocket broadcaster with registry")