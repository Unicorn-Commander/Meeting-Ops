"""
Transcription Loop Router - API endpoints for continuous transcription
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import json
import asyncio
import logging

from services.transcription_loop_service import transcription_loop_service

router = APIRouter(prefix="/api/transcription-loop", tags=["transcription-loop"])
logger = logging.getLogger(__name__)

class SaveMeetingRequest(BaseModel):
    """Request to save current buffer as a meeting"""
    name: str
    description: Optional[str] = ""
    save_audio: bool = False  # Audio is optional!

class AudioRecordingMode(BaseModel):
    """Set audio recording mode"""
    mode: str = "off"  # off, ram, disk, both

@router.get("/status")
async def get_loop_status():
    """
    Get current transcription loop status
    Shows if it's running, buffer size, etc.
    """
    return transcription_loop_service.get_status()

@router.post("/start")
async def start_transcription_loop():
    """
    Start continuous transcription loop
    - Always transcribes to Redis buffer
    - Audio recording is OFF by default
    - Circular buffer keeps last 60 minutes
    """
    result = await transcription_loop_service.start_continuous_transcription()
    return result

@router.post("/stop")
async def stop_transcription_loop():
    """
    Stop the transcription loop
    Note: This doesn't save anything, just stops listening
    """
    transcription_loop_service.is_transcribing = False
    return {
        "status": "stopped",
        "message": "Transcription loop stopped. Buffer data still available."
    }

@router.post("/save-meeting")
async def save_meeting(request: SaveMeetingRequest):
    """
    Save current buffer as a meeting
    This is the main action - converts temporary buffer to permanent record
    
    - Saves all transcripts from buffer to PostgreSQL
    - Optionally saves audio if it was being recorded
    - Clears the buffer after saving
    """
    result = await transcription_loop_service.save_current_buffer_as_meeting(
        meeting_name=request.name,
        save_audio=request.save_audio
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@router.get("/preview/{minutes}")
async def get_buffer_preview(minutes: int = 5):
    """
    Preview the last N minutes of transcription
    Useful for checking what's in the buffer before saving
    """
    if minutes < 1 or minutes > 60:
        raise HTTPException(status_code=400, detail="Minutes must be between 1 and 60")
    
    return await transcription_loop_service.get_buffer_preview(minutes)

@router.post("/audio-recording")
async def set_audio_recording_mode(request: AudioRecordingMode):
    """
    Set audio recording mode
    
    Modes:
    - "off": No audio recording (default) - transcription only
    - "ram": Audio in RAM buffer only - no disk writes, no SSD wear!
    - "disk": Traditional disk recording
    - "both": RAM buffer + disk backup
    
    Benefits of RAM mode:
    - No disk wear
    - Super fast access
    - Automatic cleanup (circular buffer)
    - Still saves to MKV when you hit "Save Meeting"
    """
    result = await transcription_loop_service.set_audio_recording(request.mode)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@router.get("/stats")
async def get_transcription_stats():
    """
    Get statistics about the transcription buffer
    """
    status = transcription_loop_service.get_status()
    
    # Calculate approximate storage savings
    avg_transcript_size_kb = 3  # 3KB per minute of transcript
    avg_audio_size_mb_wav = 5.3  # 5.3MB per minute of WAV audio
    avg_audio_size_mb_mkv = 0.24  # ~0.24MB per minute with Opus in MKV
    avg_audio_ram_compressed = 0.15  # ~0.15MB per minute compressed in RAM
    
    buffer_minutes = status.get("buffer_duration_minutes", 60)
    audio_mode = status.get("audio_mode", "off")
    
    # Calculate sizes based on mode
    storage_info = {
        "transcript_only_size_kb": buffer_minutes * avg_transcript_size_kb,
        "audio_wav_size_mb": buffer_minutes * avg_audio_size_mb_wav,
        "audio_mkv_size_mb": buffer_minutes * avg_audio_size_mb_mkv,
        "audio_ram_compressed_mb": buffer_minutes * avg_audio_ram_compressed
    }
    
    # Add mode-specific info
    if audio_mode == "off":
        storage_info["current_usage"] = "Transcripts only (minimal)"
        storage_info["storage_savings"] = "1700x less than WAV audio"
    elif audio_mode == "ram":
        storage_info["current_usage"] = f"~{status.get('audio_ram_usage_mb', 0):.1f}MB in RAM"
        storage_info["storage_savings"] = "No disk usage! RAM only"
        storage_info["max_ram_mb"] = status.get("audio_ram_limit_mb", 320)
    elif audio_mode == "disk":
        storage_info["current_usage"] = "Writing to disk"
        storage_info["storage_savings"] = "22x less with MKV vs WAV"
    
    return {
        "buffer_status": status,
        "storage_comparison": storage_info,
        "audio_modes": {
            "off": "Transcription only - 1700x storage savings",
            "ram": "Audio in RAM - No disk wear, auto-cleanup",
            "disk": "Traditional recording - Use MKV for 22x savings",
            "both": "RAM + Disk backup - Best reliability"
        },
        "current_mode": "transcription_first",
        "audio_mode": audio_mode
    }

@router.post("/clear-buffer")
async def clear_transcription_buffer():
    """
    Clear the transcription buffer
    Warning: This deletes all unsaved transcriptions!
    """
    # Clear Redis buffer
    from redis import Redis
    redis_client = Redis.from_url("redis://localhost:6379")
    redis_client.delete("transcript:buffer")
    redis_client.delete("transcript:metadata")
    redis_client.delete("audio:buffer")
    
    return {
        "status": "cleared",
        "message": "Transcription buffer cleared successfully"
    }

@router.websocket("/ws")
async def transcription_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time transcription updates"""
    await websocket.accept()
    logger.info("WebSocket client connected for transcription updates")
    
    try:
        # Send initial status (get_status is not async)
        status = transcription_loop_service.get_status()
        await websocket.send_json({
            "type": "status",
            "data": status
        })
        
        # Get Redis connection for monitoring buffer
        from redis import Redis
        redis_client = Redis.from_url("redis://localhost:6379", decode_responses=True)
        last_index = 0
        
        while True:
            # Check for new transcriptions in Redis buffer
            try:
                # Get buffer length
                buffer_len = redis_client.llen("transcript:buffer")
                
                if buffer_len > last_index:
                    # Get new items
                    new_items = redis_client.lrange("transcript:buffer", last_index, buffer_len - 1)
                    
                    for item_str in new_items:
                        try:
                            item = json.loads(item_str)
                            await websocket.send_json({
                                "type": "transcription",
                                "segment": {
                                    "text": item.get("text", ""),
                                    "timestamp": item.get("timestamp", ""),
                                    "confidence": item.get("confidence", 0.95),
                                    "speaker": item.get("speaker", "SPEAKER_00")
                                }
                            })
                        except json.JSONDecodeError:
                            pass
                    
                    last_index = buffer_len
            except Exception as e:
                logger.debug(f"Redis read error: {e}")
            
            # Handle client messages (ping/pong)
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass  # No message received, continue
            except:
                pass  # Invalid message, ignore
            
            # Small delay to prevent CPU spinning
            await asyncio.sleep(0.5)
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()