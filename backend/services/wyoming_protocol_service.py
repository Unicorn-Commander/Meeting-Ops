"""
Wyoming Protocol Service for Home Assistant Satellite Integration
Provides support for ESP32 satellite microphones and remote activation
"""
import asyncio
import json
import logging
import struct
import wave
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol
import threading

logger = logging.getLogger(__name__)

class WyomingProtocolService:
    """
    Service for handling Wyoming Protocol communication with Home Assistant satellites
    
    Wyoming Protocol is used by Home Assistant for:
    - Remote satellite microphones (ESP32 based)
    - Wake word detection
    - Voice activity detection
    - Remote activation/deactivation
    """
    
    def __init__(self):
        self.server = None
        self.clients: Dict[str, WebSocketServerProtocol] = {}
        self.active_satellites: Dict[str, Dict[str, Any]] = {}
        self.callback_handlers: Dict[str, List[Callable]] = {
            'audio_chunk': [],
            'wake_word_detected': [],
            'activation_toggle': [],
            'gesture_detected': [],
            'satellite_connected': [],
            'satellite_disconnected': []
        }
        self.is_running = False
        self.port = 10700  # Default Wyoming Protocol port
        
        # Wake word configuration
        self.wake_words = ['unicorn', 'commander', 'meeting', 'start recording']
        self.wake_word_threshold = 0.8
        
        # Protocol constants
        self.MESSAGE_TYPES = {
            'audio_chunk': 'audio-chunk',
            'audio_start': 'audio-start', 
            'audio_stop': 'audio-stop',
            'wake_word': 'wake-word-detection',
            'vad': 'voice-activity-detection',
            'info': 'info',
            'error': 'error',
            'ping': 'ping',
            'pong': 'pong'
        }
    
    async def start_server(self, host: str = '0.0.0.0', port: int = 10700):
        """Start Wyoming Protocol WebSocket server"""
        try:
            self.port = port
            self.server = await websockets.serve(
                self.handle_client,
                host,
                port,
                ping_interval=30,
                ping_timeout=10
            )
            self.is_running = True
            logger.info(f"🎙️ Wyoming Protocol server started on {host}:{port}")
            
            # Keep server running
            await self.server.wait_closed()
            
        except Exception as e:
            logger.error(f"❌ Failed to start Wyoming Protocol server: {e}")
            self.is_running = False
    
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle incoming Wyoming Protocol client connections"""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        
        try:
            # Register client
            self.clients[client_id] = websocket
            logger.info(f"🔗 Wyoming satellite connected: {client_id}")
            
            # Send info message
            await self.send_info(websocket)
            
            # Initialize satellite
            satellite_info = {
                'id': client_id,
                'connected_at': datetime.now(),
                'audio_format': {'rate': 16000, 'width': 2, 'channels': 1},
                'capabilities': ['audio', 'wake_word', 'vad'],
                'status': 'active',
                'last_activity': datetime.now()
            }
            self.active_satellites[client_id] = satellite_info
            
            # Notify handlers
            await self._trigger_callback('satellite_connected', satellite_info)
            
            # Handle messages
            async for message in websocket:
                try:
                    if isinstance(message, bytes):
                        await self.handle_binary_message(client_id, message)
                    else:
                        await self.handle_text_message(client_id, message)
                        
                    # Update last activity
                    self.active_satellites[client_id]['last_activity'] = datetime.now()
                    
                except Exception as e:
                    logger.error(f"Error handling message from {client_id}: {e}")
                    await self.send_error(websocket, str(e))
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"🔌 Wyoming satellite disconnected: {client_id}")
        except Exception as e:
            logger.error(f"❌ Error handling Wyoming client {client_id}: {e}")
        finally:
            # Cleanup
            if client_id in self.clients:
                del self.clients[client_id]
            if client_id in self.active_satellites:
                satellite_info = self.active_satellites[client_id]
                del self.active_satellites[client_id]
                await self._trigger_callback('satellite_disconnected', satellite_info)
    
    async def handle_text_message(self, client_id: str, message: str):
        """Handle text-based Wyoming Protocol messages"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == self.MESSAGE_TYPES['wake_word']:
                await self.handle_wake_word_detection(client_id, data)
            elif msg_type == self.MESSAGE_TYPES['vad']:
                await self.handle_voice_activity(client_id, data)
            elif msg_type == self.MESSAGE_TYPES['audio_start']:
                await self.handle_audio_start(client_id, data)
            elif msg_type == self.MESSAGE_TYPES['audio_stop']:
                await self.handle_audio_stop(client_id, data)
            elif msg_type == self.MESSAGE_TYPES['ping']:
                await self.send_pong(self.clients[client_id])
            elif msg_type == self.MESSAGE_TYPES['info']:
                await self.handle_satellite_info(client_id, data)
            else:
                logger.warning(f"Unknown message type from {client_id}: {msg_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from {client_id}: {e}")
            await self.send_error(self.clients[client_id], "Invalid JSON format")
    
    async def handle_binary_message(self, client_id: str, message: bytes):
        """Handle binary audio data from satellites"""
        try:
            # Wyoming Protocol audio format: 16kHz, 16-bit, mono PCM
            # Convert to numpy array for processing
            import numpy as np
            
            audio_data = np.frombuffer(message, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Create audio chunk data
            chunk_data = {
                'satellite_id': client_id,
                'audio_data': audio_data,
                'sample_rate': 16000,
                'channels': 1,
                'timestamp': datetime.now(),
                'size_bytes': len(message)
            }
            
            # Update satellite status
            if client_id in self.active_satellites:
                self.active_satellites[client_id]['status'] = 'recording'
                self.active_satellites[client_id]['last_audio'] = datetime.now()
            
            # Trigger audio chunk callback
            await self._trigger_callback('audio_chunk', chunk_data)
            
        except Exception as e:
            logger.error(f"Error processing audio from {client_id}: {e}")
    
    async def handle_wake_word_detection(self, client_id: str, data: Dict[str, Any]):
        """Handle wake word detection from satellite"""
        wake_word = data.get('wake_word', {})
        
        wake_word_data = {
            'satellite_id': client_id,
            'wake_word': wake_word.get('word', ''),
            'confidence': wake_word.get('confidence', 0.0),
            'timestamp': datetime.now(),
            'audio_seconds': wake_word.get('audio_seconds', 0)
        }
        
        logger.info(f"🎯 Wake word detected from {client_id}: {wake_word_data['wake_word']} "
                   f"(confidence: {wake_word_data['confidence']:.2f})")
        
        # Check if confidence meets threshold
        if wake_word_data['confidence'] >= self.wake_word_threshold:
            await self._trigger_callback('wake_word_detected', wake_word_data)
        
    async def handle_voice_activity(self, client_id: str, data: Dict[str, Any]):
        """Handle voice activity detection"""
        vad_data = {
            'satellite_id': client_id,
            'is_speech': data.get('is_speech', False),
            'probability': data.get('probability', 0.0),
            'timestamp': datetime.now()
        }
        
        # Update satellite status
        if client_id in self.active_satellites:
            self.active_satellites[client_id]['voice_active'] = vad_data['is_speech']
    
    async def handle_audio_start(self, client_id: str, data: Dict[str, Any]):
        """Handle audio stream start notification"""
        logger.info(f"🎤 Audio stream started from satellite {client_id}")
        
        if client_id in self.active_satellites:
            self.active_satellites[client_id]['status'] = 'streaming'
    
    async def handle_audio_stop(self, client_id: str, data: Dict[str, Any]):
        """Handle audio stream stop notification"""
        logger.info(f"🔇 Audio stream stopped from satellite {client_id}")
        
        if client_id in self.active_satellites:
            self.active_satellites[client_id]['status'] = 'active'
    
    async def handle_satellite_info(self, client_id: str, data: Dict[str, Any]):
        """Handle satellite information update"""
        if client_id in self.active_satellites:
            satellite = self.active_satellites[client_id]
            
            # Update satellite capabilities and info
            satellite.update({
                'name': data.get('name', client_id),
                'version': data.get('version', 'unknown'),
                'capabilities': data.get('capabilities', []),
                'hardware': data.get('hardware', {}),
                'audio_format': data.get('audio_format', satellite.get('audio_format', {}))
            })
            
            logger.info(f"📋 Updated satellite info for {client_id}: {data.get('name', 'Unknown')}")
    
    async def send_info(self, websocket: WebSocketServerProtocol):
        """Send server info to satellite"""
        info_message = {
            'type': self.MESSAGE_TYPES['info'],
            'server': {
                'name': 'Unicorn Commander Meeting Ops',
                'version': '1.0',
                'capabilities': ['transcription', 'speaker_diarization', 'npu_acceleration'],
                'supported_formats': [
                    {'rate': 16000, 'width': 2, 'channels': 1}
                ]
            },
            'timestamp': datetime.now().isoformat()
        }
        
        await websocket.send(json.dumps(info_message))
    
    async def send_pong(self, websocket: WebSocketServerProtocol):
        """Send pong response"""
        pong_message = {
            'type': self.MESSAGE_TYPES['pong'],
            'timestamp': datetime.now().isoformat()
        }
        
        await websocket.send(json.dumps(pong_message))
    
    async def send_error(self, websocket: WebSocketServerProtocol, error_msg: str):
        """Send error message to satellite"""
        error_message = {
            'type': self.MESSAGE_TYPES['error'],
            'error': error_msg,
            'timestamp': datetime.now().isoformat()
        }
        
        await websocket.send(json.dumps(error_message))
    
    async def broadcast_activation_command(self, command: str, satellite_id: Optional[str] = None):
        """Send activation command to satellites"""
        activation_message = {
            'type': 'activation',
            'command': command,  # 'start', 'stop', 'pause'
            'timestamp': datetime.now().isoformat()
        }
        
        if satellite_id and satellite_id in self.clients:
            # Send to specific satellite
            await self.clients[satellite_id].send(json.dumps(activation_message))
        else:
            # Broadcast to all satellites
            for websocket in self.clients.values():
                try:
                    await websocket.send(json.dumps(activation_message))
                except Exception as e:
                    logger.error(f"Error sending activation command: {e}")
    
    def register_callback(self, event_type: str, callback: Callable):
        """Register callback for Wyoming Protocol events"""
        if event_type in self.callback_handlers:
            self.callback_handlers[event_type].append(callback)
        else:
            logger.warning(f"Unknown event type: {event_type}")
    
    async def _trigger_callback(self, event_type: str, data: Any):
        """Trigger registered callbacks for an event"""
        for callback in self.callback_handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Error in callback for {event_type}: {e}")
    
    def get_satellite_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all connected satellites"""
        return {
            satellite_id: {
                'id': satellite['id'],
                'status': satellite['status'],
                'connected_at': satellite['connected_at'].isoformat(),
                'last_activity': satellite['last_activity'].isoformat(),
                'capabilities': satellite.get('capabilities', []),
                'name': satellite.get('name', satellite_id),
                'hardware': satellite.get('hardware', {}),
                'voice_active': satellite.get('voice_active', False)
            }
            for satellite_id, satellite in self.active_satellites.items()
        }
    
    async def stop_server(self):
        """Stop Wyoming Protocol server"""
        self.is_running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("🛑 Wyoming Protocol server stopped")

# Wake word detection using lightweight model
class WakeWordDetector:
    """Lightweight wake word detection for satellite microphones"""
    
    def __init__(self):
        self.is_initialized = False
        self.model = None
        self.wake_words = ['unicorn', 'commander', 'meeting', 'start recording']
        
    def initialize(self):
        """Initialize wake word detection model"""
        try:
            # Use a lightweight model for wake word detection
            # This could be Porcupine, OpenWakeWord, or a custom NPU model
            
            # For now, use simple keyword matching
            # In production, you'd use a proper wake word model
            self.is_initialized = True
            logger.info("✅ Wake word detector initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize wake word detector: {e}")
            return False
    
    def detect_wake_word(self, audio_data: bytes) -> Optional[Dict[str, Any]]:
        """Detect wake words in audio data"""
        if not self.is_initialized:
            return None
            
        try:
            # Simple implementation - in production use proper wake word detection
            # This is just a placeholder for the actual implementation
            
            # Convert audio to text using fast transcription
            # Check for wake words
            # Return detection result
            
            return None  # Placeholder
            
        except Exception as e:
            logger.error(f"Error in wake word detection: {e}")
            return None

# Gesture recognition for hands-free control
class GestureRecognizer:
    """NPU-accelerated gesture recognition for hands-free meeting control"""
    
    def __init__(self):
        self.is_initialized = False
        self.gesture_models = {}
        self.supported_gestures = [
            'wave_to_start',
            'thumbs_up',
            'thumbs_down', 
            'stop_gesture',
            'pause_gesture'
        ]
    
    def initialize(self):
        """Initialize gesture recognition models"""
        try:
            # Load NPU-optimized gesture recognition models
            # This would use the same NPU infrastructure we built for transcription
            
            self.is_initialized = True
            logger.info("✅ Gesture recognizer initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize gesture recognizer: {e}")
            return False
    
    def detect_gesture(self, image_data: bytes) -> Optional[Dict[str, Any]]:
        """Detect gestures in camera image data"""
        if not self.is_initialized:
            return None
            
        try:
            # Process image through NPU gesture models
            # Return detected gesture with confidence
            
            return None  # Placeholder
            
        except Exception as e:
            logger.error(f"Error in gesture recognition: {e}")
            return None

# Global instances
wyoming_service = WyomingProtocolService()
wake_word_detector = WakeWordDetector()
gesture_recognizer = GestureRecognizer()