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

@router.websocket("/ws/audio-levels")
async def websocket_audio_levels(websocket: WebSocket):
    """WebSocket endpoint for real-time audio level monitoring"""
    await websocket.accept()
    logger.info("Audio levels WebSocket connected")
    
    try:
        # Import Redis client
        import redis.asyncio as redis
        import json
        
        # Connect to Redis for audio level updates
        redis_client = await redis.from_url("redis://localhost:6379", decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("audio:levels")
        
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "message": "Connected to audio level stream"
        })
        
        # Listen for audio level updates from Redis
        async def listen_for_levels():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await websocket.send_json({
                            "type": "audio_level",
                            "level": data.get("level", 0),
                            "timestamp": data.get("timestamp"),
                            "status": data.get("status", "active")
                        })
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Error sending audio level: {e}")
                        break
        
        # Run the listening task
        listen_task = asyncio.create_task(listen_for_levels())
        
        # Keep connection alive and handle client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "keepalive"})
            except Exception:
                break
                
    except WebSocketDisconnect:
        logger.info("Audio levels WebSocket disconnected")
    except Exception as e:
        logger.error(f"Audio levels WebSocket error: {e}")
    finally:
        # Cleanup
        if 'listen_task' in locals():
            listen_task.cancel()
        if 'pubsub' in locals():
            await pubsub.unsubscribe("audio:levels")
            await pubsub.close()
        if 'redis_client' in locals():
            await redis_client.close()

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
            try:
                # Wait for messages from client with timeout
                # This allows the connection to stay open for broadcasting
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
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
            except asyncio.TimeoutError:
                # Send keepalive on timeout
                try:
                    await websocket.send_json({"type": "keepalive"})
                except:
                    break  # Connection closed
                        
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        logger.info(f"Client disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, session_id)

# Function to broadcast transcription updates (can be called from other modules)
async def broadcast_transcription_update(session_id: str, segment: Dict):
    """Broadcast a transcription segment to all connected clients"""
    logger.info(f"Broadcasting transcription update to session {session_id}: {segment.get('text', '')[:50]}...")
    await manager.broadcast_transcription(session_id, {
        "type": "transcription",
        "segment": segment
    })