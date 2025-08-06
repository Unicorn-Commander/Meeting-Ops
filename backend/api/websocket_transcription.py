"""
WebSocket endpoint for live transcription streaming
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio
from typing import Dict, Set
import logging

from services.whisperx_npu_service import whisperx_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active WebSocket connections
active_connections: Dict[str, Set[WebSocket]] = {}

class TranscriptionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept WebSocket connection and add to session"""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
        logger.info(f"WebSocket connected for session {session_id}")
        
    def disconnect(self, websocket: WebSocket, session_id: str):
        """Remove WebSocket from session"""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"WebSocket disconnected for session {session_id}")
        
    async def broadcast_transcription(self, session_id: str, transcription: Dict):
        """Broadcast transcription to all connected clients for a session"""
        if session_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(transcription)
                except Exception as e:
                    logger.error(f"Error broadcasting to connection: {e}")
                    disconnected.add(connection)
            
            # Clean up disconnected connections
            for conn in disconnected:
                self.active_connections[session_id].discard(conn)

manager = TranscriptionManager()

@router.websocket("/ws/transcription/{session_id}")
async def websocket_transcription(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for live transcription streaming"""
    await manager.connect(websocket, session_id)
    
    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "message": "Connected to transcription stream",
            "session_id": session_id,
            "npu_status": whisperx_service.get_npu_status()
        })
        
        # Keep connection alive and handle messages
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "audio_chunk":
                # Process audio chunk for real-time transcription
                audio_data = message.get("audio")
                if audio_data:
                    result = whisperx_service.transcribe_stream(
                        audio_data.encode(),
                        session_id
                    )
                    if result:
                        await manager.broadcast_transcription(session_id, {
                            "type": "transcription",
                            "segment": result
                        })
                        
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        logger.info(f"Client disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, session_id)

# Function to broadcast transcription updates (can be called from other modules)
async def broadcast_transcription_update(session_id: str, segment: Dict):
    """Broadcast a transcription segment to all connected clients"""
    await manager.broadcast_transcription(session_id, {
        "type": "transcription",
        "segment": segment
    })