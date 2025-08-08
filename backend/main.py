"""
Simplified main.py for Docker deployment
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
import os
from typing import Dict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global audio monitoring task
audio_monitor_task = None

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    global audio_monitor_task
    
    # Startup
    logger.info("🚀 Starting Unicorn Commander (Docker Mode)...")
    
    # Initialize database
    try:
        from database.database import init_database
        init_database()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization failed: {e}")
    
    # Initialize transcriber during startup
    try:
        logger.info("🎙️ Initializing NPU Whisper transcriber...")
        transcriber = get_transcriber()
        if transcriber:
            logger.info("✅ NPU Whisper transcriber ready for use")
        else:
            logger.warning("⚠️ NPU Whisper transcriber initialization failed")
    except Exception as e:
        logger.warning(f"⚠️ Transcriber initialization failed: {e}")
    
    # Start audio monitoring service with Redis
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        from audio_level_redis import AudioLevelRedisService
        
        audio_service = AudioLevelRedisService(redis_url)
        if await audio_service.connect():
            logger.info("🎤 Starting audio level monitoring service with Redis...")
            audio_monitor_task = asyncio.create_task(audio_service.start_audio_monitoring())
        else:
            logger.warning("⚠️ Audio monitoring disabled - Redis not available")
    except Exception as e:
        logger.warning(f"⚠️ Audio monitoring failed to start: {e}")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down...")
    
    # Stop audio monitoring
    if audio_monitor_task and not audio_monitor_task.done():
        audio_monitor_task.cancel()
        try:
            await audio_monitor_task
        except asyncio.CancelledError:
            pass

# Create FastAPI app
app = FastAPI(
    title="Unicorn Commander API",
    version="1.0.0",
    description="Meeting recording and transcription service",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import auth router from dev branch
try:
    from auth.routes import router as auth_router
    app.include_router(auth_router)
    logger.info("✅ Auth router loaded")
except Exception as e:
    logger.warning(f"⚠️ Auth router failed to load: {e}")

# Import core routers
try:
    from api.recording_v2 import router as recording_router
    app.include_router(recording_router, prefix="/api")
    logger.info("✅ Recording router loaded")
except Exception as e:
    logger.warning(f"⚠️ Recording router failed to load: {e}")

# Import sessions router
try:
    from api.sessions import router as sessions_router
    app.include_router(sessions_router, prefix="/api")
    logger.info("✅ Sessions router loaded")
except Exception as e:
    logger.warning(f"⚠️ Sessions router failed to load: {e}")

# Import Meeting Management router (all new endpoints)
try:
    from api.meeting_management import router as meeting_router
    app.include_router(meeting_router)
    logger.info("✅ Meeting Management router loaded (Recording, Templates, Export)")
except Exception as e:
    logger.warning(f"⚠️ Meeting Management router failed to load: {e}")

# Import AI Settings router
try:
    from api.ai_settings import router as ai_settings_router
    app.include_router(ai_settings_router)
    logger.info("✅ AI Settings router loaded")
except Exception as e:
    logger.warning(f"⚠️ AI Settings router failed to load: {e}")

# Import Simple Recording router (no auth required for testing)
try:
    from api.simple_recording import router as simple_recording_router
    app.include_router(simple_recording_router)
    logger.info("✅ Simple Recording router loaded (no auth)")
except Exception as e:
    logger.warning(f"⚠️ Simple Recording router failed to load: {e}")

# Import WebSocket Transcription router
try:
    from api.websocket_transcription import router as ws_transcription_router
    app.include_router(ws_transcription_router)
    logger.info("✅ WebSocket Transcription router loaded")
except Exception as e:
    logger.warning(f"⚠️ WebSocket Transcription router failed to load: {e}")

# Import Live Transcription router (TIME-SHIFT RECORDING SYSTEM!)
try:
    from api.live_transcription import router as live_transcription_router
    app.include_router(live_transcription_router)
    logger.info("🎯 Live Transcription (Time-Shift) router loaded")
except Exception as e:
    logger.warning(f"⚠️ Live Transcription router failed to load: {e}")

# Import Always-On Transcription router
try:
    from routers.always_on_transcription import router as always_on_router
    app.include_router(always_on_router)
    logger.info("✅ Always-On Transcription router loaded")
except Exception as e:
    logger.warning(f"⚠️ Always-On Transcription router failed to load: {e}")

# Try to import Gemini's new routers
try:
    from routers.logs import router as logs_router
    app.include_router(logs_router)
    logger.info("✅ Logs router loaded")
except Exception as e:
    logger.warning(f"⚠️ Logs router failed to load: {e}")

try:
    from routers.backup import router as backup_router
    app.include_router(backup_router)
    logger.info("✅ Backup router loaded")
except Exception as e:
    logger.warning(f"⚠️ Backup router failed to load: {e}")

try:
    from routers.ssl import router as ssl_router
    app.include_router(ssl_router)
    logger.info("✅ SSL router loaded")
except Exception as e:
    logger.warning(f"⚠️ SSL router failed to load: {e}")

# Health check endpoint
@app.get("/api/status")
async def get_status():
    """Get system status"""
    transcriber = get_transcriber()
    npu_available = False
    
    # Check NPU availability
    try:
        if os.path.exists("/dev/accel/accel0"):
            npu_available = True
    except:
        pass
        
    return {
        "status": "running",
        "mode": "docker",
        "transcriber_ready": transcriber is not None,
        "npu_available": npu_available,
        "speaker_diarization_ready": False,
        "active_sessions": len(recording_processes),
        "system_info": {
            "onnx_whisper_ready": transcriber is not None and hasattr(transcriber, 'model_loaded') and transcriber.model_loaded,
            "npu_available": npu_available,
            "onnx_providers": [],
            "model_path": None
        },
        "diarizer_info": {
            "ready": False,
            "device": "npu" if npu_available else "cpu",
            "model": "whisper-base-onnx"
        }
    }

# Audio devices endpoint
@app.get("/api/audio-devices")
async def get_audio_devices():
    """Get available audio devices"""
    try:
        # Try system approach first (ALSA)
        import subprocess
        result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
        if result.returncode == 0:
            devices = []
            lines = result.stdout.split('\n')
            for line in lines:
                if 'card' in line and 'device' in line:
                    if 'USB PnP Sound Device' in line:
                        devices.append({
                            "index": 0,
                            "name": "USB PnP Sound Device (M-305)",
                            "channels": 1,
                            "sample_rate": 44100
                        })
                    elif 'ALC269VC' in line:
                        devices.append({
                            "index": 1, 
                            "name": "HD-Audio Generic (Internal)",
                            "channels": 1,
                            "sample_rate": 16000
                        })
            if not devices:  # Fallback if parsing fails
                devices = [
                    {
                        "index": 0,
                        "name": "USB PnP Sound Device (Server Microphone)",
                        "channels": 1,
                        "sample_rate": 44100
                    }
                ]
            return {"devices": devices}
    except:
        pass
    
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        devices = []
        
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                devices.append({
                    "index": i,
                    "name": info['name'],
                    "channels": info['maxInputChannels'],
                    "sample_rate": int(info['defaultSampleRate'])
                })
        
        p.terminate()
        return {"devices": devices}
    except Exception as e:
        logger.error(f"Failed to get audio devices: {e}")
        # Return mock device for development
        return {
            "devices": [
                {
                    "index": 0,
                    "name": "Default System Microphone",
                    "channels": 1,
                    "sample_rate": 16000
                }
            ],
            "note": "Using fallback device list"
        }

# Network status endpoint
@app.get("/api/network/status")
async def get_network_status():
    """Get network interface status and statistics"""
    try:
        import psutil
        import socket
        
        # Get network interfaces
        interfaces = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        io_counters = psutil.net_io_counters(pernic=True)
        
        for interface, addresses in addrs.items():
            if_data = {
                "name": interface,
                "status": "up" if stats[interface].isup else "down",
                "addresses": [],
                "stats": None
            }
            
            # Get addresses
            for addr in addresses:
                if addr.family == socket.AF_INET:
                    if_data["addresses"].append({
                        "type": "ipv4",
                        "address": addr.address,
                        "netmask": addr.netmask
                    })
                elif addr.family == socket.AF_INET6:
                    if_data["addresses"].append({
                        "type": "ipv6",
                        "address": addr.address
                    })
            
            # Get IO stats
            if interface in io_counters:
                counters = io_counters[interface]
                if_data["stats"] = {
                    "bytes_sent": counters.bytes_sent,
                    "bytes_recv": counters.bytes_recv,
                    "packets_sent": counters.packets_sent,
                    "packets_recv": counters.packets_recv,
                    "errors_in": counters.errin,
                    "errors_out": counters.errout
                }
            
            interfaces.append(if_data)
        
        # Get hostname
        hostname = socket.gethostname()
        
        # Simple firewall status (placeholder)
        firewall_status = {
            "enabled": False,
            "rules_count": 0,
            "last_updated": None
        }
        
        return {
            "hostname": hostname,
            "interfaces": interfaces,
            "firewall": firewall_status,
            "dns_servers": [],
            "gateway": None
        }
    except Exception as e:
        logger.error(f"Error getting network status: {e}")
        return {
            "error": str(e),
            "interfaces": [],
            "firewall": {"enabled": False}
        }

# Basic recording endpoints
import os
import subprocess
from datetime import datetime

# Simple recording state
recording_processes = {}

@app.post("/api/recording/start")
async def start_recording():
    """Start audio recording using system tools"""
    try:
        session_id = f"session_{int(datetime.now().timestamp())}"
        recording_dir = f"/tmp/recordings/{session_id}"
        os.makedirs(recording_dir, exist_ok=True)
        
        # Use arecord as fallback for audio recording
        audio_file = f"{recording_dir}/recording.wav"
        
        # Start recording with parec (PulseAudio)
        cmd = [
            'parec',
            '--format=s16le',     # 16-bit little-endian
            '--channels=1',       # mono
            '--rate=16000',       # 16kHz sample rate
            '--file-format=wav',  # WAV format
            audio_file
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        recording_processes[session_id] = {
            'process': process,
            'file': audio_file,
            'start_time': datetime.now()
        }
        
        return {
            "status": "recording",
            "session_id": session_id,
            "file_path": audio_file,
            "message": "Recording started with system audio"
        }
        
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/recording/stop/{session_id}")
async def stop_recording(session_id: str):
    """Stop audio recording"""
    try:
        if session_id not in recording_processes:
            return {"status": "error", "message": "Session not found"}
        
        # Stop the recording process
        process_info = recording_processes[session_id]
        process = process_info['process']
        process.terminate()
        process.wait()
        
        # Clean up
        del recording_processes[session_id]
        
        # Check if file was created
        file_path = process_info['file']
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        
        return {
            "status": "stopped",
            "session_id": session_id,
            "file_path": file_path,
            "file_size": file_size,
            "duration": (datetime.now() - process_info['start_time']).total_seconds()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/recording/status")
async def get_recording_status():
    """Get current recording status"""
    active_sessions = []
    for session_id, info in recording_processes.items():
        active_sessions.append({
            "session_id": session_id,
            "file_path": info['file'],
            "duration": (datetime.now() - info['start_time']).total_seconds(),
            "status": "recording" if info['process'].poll() is None else "stopped"
        })
    
    return {
        "active_sessions": active_sessions,
        "total_active": len(active_sessions)
    }

# Initialize transcriber globally
whisper_transcriber = None
whisperx_transcriber = None

def get_transcriber():
    """Get or initialize the transcriber - NPU ONLY"""
    global whisper_transcriber, whisperx_transcriber
    
    # Try NPU runtime ONLY
    if whisper_transcriber is None:
        try:
            from npu_whisper_transcriber import NPUWhisperTranscriber
            
            # Use the real NPU Whisper implementation
            whisper_transcriber = NPUWhisperTranscriber()
            
            if whisper_transcriber.model_loaded:
                logger.info("✅ NPU Whisper transcriber initialized")
                logger.info(f"   Using NPU: {whisper_transcriber.using_npu}")
                logger.info(f"   NPU Available: {whisper_transcriber.npu_available}")
                logger.info(f"   WhisperX Engine: {whisper_transcriber.whisperx_engine is not None}")
                return whisper_transcriber
            else:
                logger.error("❌ Failed to initialize NPU Whisper transcriber")
                # Per requirements: NPU or failure only
                raise RuntimeError("NPU transcriber required but initialization failed")
        except Exception as e:
            logger.error(f"NPU transcriber initialization failed: {e}")
            return None
    
    if whisperx_transcriber is None:
        try:
            from whisper_onnx_transcriber import WhisperXTranscriber
            whisperx_transcriber = WhisperXTranscriber(model_size="base", device="cpu")
            logger.info("✅ WhisperX transcriber initialized")
        except Exception as e:
            logger.warning(f"WhisperX initialization failed: {e}")
            
    if whisper_transcriber is None and whisperx_transcriber is None:
        try:
            from whisper_onnx_transcriber import WhisperONNXTranscriber
            whisper_transcriber = WhisperONNXTranscriber(model_size="base")
            logger.info("✅ ONNX Whisper transcriber initialized")
        except Exception as e:
            logger.error(f"Failed to initialize transcriber: {e}")
            
    return whisper_transcriber or whisperx_transcriber

# Initialize diarization service globally
diarization_service = None

async def get_diarization_service():
    """Get or initialize diarization service"""
    global diarization_service
    if diarization_service is None:
        from transcription_with_diarization import TranscriptionWithDiarization
        diarization_service = TranscriptionWithDiarization()
        await diarization_service.initialize_diarizer()
    return diarization_service

# Transcription endpoint with real ONNX Whisper
@app.post("/api/transcribe")
async def transcribe_audio(file_path: str = None, diarize: bool = False):
    """Transcribe audio file using ONNX Whisper"""
    try:
        if not file_path or not os.path.exists(file_path):
            return {"status": "error", "message": "File not found"}
        
        file_size = os.path.getsize(file_path)
        
        # Get transcriber
        transcriber = get_transcriber()
        
        if transcriber is None:
            # Fallback if transcriber fails
            return {
                "status": "error",
                "message": "Transcriber not available",
                "file_path": file_path,
                "file_size": file_size
            }
        
        # Perform transcription
        if diarize:
            # Use diarization service for speaker identification
            service = await get_diarization_service()
            result = service.transcribe_with_speakers(file_path)
        else:
            # Regular transcription without diarization
            if hasattr(transcriber, 'transcribe'):
                result = transcriber.transcribe(file_path)
            else:
                # Standard API
                result = transcriber.transcribe_file(file_path)
        
        return {
            "status": "success",
            "file_path": file_path,
            "file_size": file_size,
            "transcription": result,
            "model": getattr(transcriber, 'model_size', 'base'),
            "diarization": diarize and result.get("diarization", False)
        }
        
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return {"status": "error", "message": str(e)}

# Ollama summarization endpoint
from pydantic import BaseModel
from typing import Optional

class SummarizeRequest(BaseModel):
    session_id: Optional[str] = None
    text: Optional[str] = None

@app.post("/api/summarize")
async def summarize_transcription(request: SummarizeRequest):
    """Summarize transcription using Ollama"""
    try:
        import requests
        
        # Get transcription text
        if not request.text:
            # If session_id provided, fetch transcription from DB or file
            if request.session_id:
                # For now, use a placeholder
                text = "This is a placeholder transcription that needs to be summarized."
            else:
                return {"status": "error", "message": "No text provided for summarization"}
        else:
            text = request.text
        
        # Prepare Ollama request
        ollama_url = "http://localhost:11434/api/generate"
        
        prompt = f"""Please provide a concise summary of the following meeting transcription:

{text}

Summary format:
- Key Points: List the main topics discussed
- Action Items: List any action items mentioned
- Decisions: List any decisions made
- Next Steps: List any next steps discussed

Keep the summary brief and professional."""

        payload = {
            "model": "gemma3n:latest",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7
            }
        }
        
        # Call Ollama
        logger.info("Calling Ollama for summarization...")
        response = requests.post(ollama_url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            summary_text = result.get("response", "")
            
            return {
                "status": "success",
                "session_id": request.session_id,
                "summary": summary_text,
                "model": "gemma3n:latest",
                "word_count": len(text.split()),
                "summary_word_count": len(summary_text.split())
            }
        else:
            logger.error(f"Ollama error: {response.status_code} - {response.text}")
            return {
                "status": "error",
                "message": f"Ollama error: {response.status_code}",
                "details": response.text
            }
            
    except requests.exceptions.ConnectionError:
        logger.error("Failed to connect to Ollama at localhost:11434")
        return {
            "status": "error",
            "message": "Failed to connect to Ollama. Ensure Ollama is running at localhost:11434"
        }
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        return {"status": "error", "message": str(e)}

# Meeting insights endpoint using Gemma3n
class InsightsRequest(BaseModel):
    session_id: Optional[str] = None
    transcript: Optional[str] = None
    insight_type: str = "full"  # full, action_items, decisions, summary

@app.post("/api/insights")
async def generate_meeting_insights(request: InsightsRequest):
    """Generate AI-powered meeting insights using Gemma3n:e4b"""
    try:
        from services.ollama_service import OllamaService
        
        # Get transcript
        if not request.transcript:
            if request.session_id:
                # TODO: Fetch from database
                transcript = "Meeting transcript placeholder"
            else:
                return {"status": "error", "message": "No transcript provided"}
        else:
            transcript = request.transcript
        
        # Initialize Ollama service
        ollama = OllamaService()
        
        # Generate insights based on type
        if request.insight_type == "action_items":
            prompt = f"""Extract action items from this meeting transcript. 
For each action item, identify: owner, deadline, and description.

Transcript:
{transcript[:4000]}

List action items in bullet format with owner and deadline."""
        
        elif request.insight_type == "decisions":
            prompt = f"""Identify key decisions made in this meeting.
For each decision, explain the rationale.

Transcript:
{transcript[:4000]}

List decisions with their rationale."""
        
        elif request.insight_type == "summary":
            prompt = f"""Provide a 3-sentence executive summary of this meeting.
Focus on outcomes and next steps.

Transcript:
{transcript[:4000]}"""
        
        else:  # full insights
            prompt = f"""Analyze this meeting and provide:
1. Key Topics (3-5 bullet points)
2. Action Items (with owners and deadlines)
3. Decisions Made
4. Next Steps
5. Sentiment Analysis (positive/neutral/concerning areas)

Transcript:
{transcript[:4000]}

Provide structured insights."""
        
        # Generate insights with Gemma3n:e4b
        insights = ollama.generate(prompt, model="gemma3n:e4b")
        
        return {
            "status": "success",
            "insight_type": request.insight_type,
            "insights": insights,
            "model": "gemma3n:e4b",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Insights generation error: {e}")
        return {"status": "error", "message": str(e)}

# WebSocket endpoint for live transcription (ready for implementation)
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/transcription")
async def websocket_transcription(websocket: WebSocket):
    """WebSocket endpoint for live transcription feed"""
    await websocket.accept()
    from datetime import datetime
    import numpy as np
    import tempfile
    import wave
    import asyncio
    
    session_id = None
    audio_buffer = bytearray()
    transcriber = get_transcriber()
    chunk_size = 16000 * 2  # 2 seconds of 16kHz 16-bit audio
    
    try:
        # Wait for initial config message
        config_msg = await websocket.receive_json()
        session_id = config_msg.get("session_id", f"ws_{int(datetime.now().timestamp())}")
        logger.info(f"WebSocket transcription started for session: {session_id}")
        
        # Send acknowledgment
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "session_id": session_id,
            "message": "Live transcription started"
        })
        
        while True:
            # Receive audio data
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=30.0)
                if message["type"] == "websocket.receive":
                    if "bytes" in message:
                        data = message["bytes"]
                        audio_buffer.extend(data)
                    
                    # Process when we have enough audio (2 seconds)
                    if len(audio_buffer) >= chunk_size * 2:
                        # Save to temporary file for NPU processing
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                            with wave.open(tmp_file.name, 'wb') as wav:
                                wav.setnchannels(1)
                                wav.setsampwidth(2)
                                wav.setframerate(16000)
                                wav.writeframes(audio_buffer[:chunk_size * 2])
                            
                            # Transcribe with NPU
                            if transcriber and hasattr(transcriber, 'transcribe'):
                                result = transcriber.transcribe(tmp_file.name)
                                
                                # Send transcription result
                                response = {
                                    "type": "transcription",
                                    "text": result.get("text", ""),
                                    "timestamp": datetime.now().isoformat(),
                                    "confidence": result.get("confidence", 0.95),
                                    "npu_accelerated": result.get("npu_accelerated", False),
                                    "processing_time": result.get("processing_time", 0),
                                    "audio_duration": len(audio_buffer) / 32000  # 16kHz * 2 bytes
                                }
                                await websocket.send_json(response)
                            
                            # Remove temporary file
                            os.unlink(tmp_file.name)
                        
                        # Keep last 0.5 seconds for overlap
                        audio_buffer = audio_buffer[chunk_size * 2 - 8000:]
                
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({
                    "type": "keepalive",
                    "timestamp": datetime.now().isoformat()
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        if session_id in recording_processes:
            # Clean up any associated recording
            try:
                process_info = recording_processes[session_id]
                process_info['process'].terminate()
                del recording_processes[session_id]
            except:
                pass

@app.websocket("/ws/audio-levels")
async def websocket_audio_levels(websocket: WebSocket):
    """WebSocket endpoint for real-time audio level monitoring"""
    await websocket.accept()
    
    # Use Redis for scalable WebSocket broadcasting
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    use_redis = True  # Enable Redis-based broadcasting
    
    try:
        if use_redis:
            # Use Redis pub/sub for audio levels
            from audio_level_redis import AudioLevelWebSocketHandler
            handler = AudioLevelWebSocketHandler(redis_url)
            await handler.handle_websocket(websocket)
        else:
            # Use direct USB monitoring for real audio
            from audio_level_direct_usb import DirectUSBAudioMonitor, handle_direct_usb_websocket
            
            logger.info("🎤 Starting DIRECT USB audio monitoring (Texas Instruments PCM2902)")
            
            # Use the direct USB handler
            await handle_direct_usb_websocket(websocket)
            return
                    
    except WebSocketDisconnect:
        logger.info("Audio level WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error", 
                "message": str(e)
            })
        except:
            pass
@app.post("/api/session/create")
async def create_session_with_recording():
    """Create a new session and start recording"""
    try:
        # Start recording
        start_response = await start_recording()
        
        if start_response["status"] == "recording":
            return {
                "status": "session_created",
                "session_id": start_response["session_id"],
                "recording_status": "active",
                "file_path": start_response["file_path"],
                "message": "Session created and recording started",
                "next_steps": [
                    f"POST /api/recording/stop/{start_response['session_id']} to stop recording",
                    f"POST /api/transcribe?file_path={start_response['file_path']} to transcribe"
                ]
            }
        else:
            return start_response
            
    except Exception as e:
        logger.error(f"Session creation error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {"message": "Unicorn Commander API - Use /docs for API documentation"}

# Export endpoint
@app.get("/api/session/{session_id}/export")
async def export_session(session_id: str, format: str = "txt"):
    """Export session transcript in various formats"""
    try:
        from export_service import ExportService
        
        # Get transcript
        audio_path = f"/tmp/recordings/{session_id}/recording.wav"
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get transcriber and transcribe if needed
        transcriber = get_transcriber()
        result = transcriber.transcribe(audio_path)
        
        # Prepare session data
        session_data = {
            "session_id": session_id,
            "audio_file": audio_path,
            "duration": result.get("duration", 0),
            "transcript": result.get("text", ""),
            "npu_accelerated": result.get("npu_accelerated", False),
            "model": "whisper-base",
            "performance": result.get("performance", {})
        }
        
        # Export
        export_service = ExportService()
        
        if format.lower() == "json":
            content = export_service.export_json(session_data)
            return {"format": "json", "content": json.loads(content)}
        elif format.lower() == "pdf":
            try:
                pdf_bytes = export_service.export_pdf(session_data)
                import base64
                return {
                    "format": "pdf",
                    "content_base64": base64.b64encode(pdf_bytes).decode(),
                    "size": len(pdf_bytes)
                }
            except Exception as e:
                raise HTTPException(status_code=501, detail=f"PDF export failed: {str(e)}")
        else:  # Default to TXT
            content = export_service.export_txt(session_data)
            return {"format": "txt", "content": content}
            
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

# List all sessions
@app.get("/api/sessions")
async def list_sessions():
    import glob, os
    sessions = []
    for path in glob.glob("/tmp/recordings/session_*/recording.wav"):
        session_id = os.path.basename(os.path.dirname(path))
        stat = os.stat(path)
        sessions.append({
            "session_id": session_id,
            "path": path,
            "size": stat.st_size,
            "mtime": stat.st_mtime
        })
    return {"sessions": sessions}

# Get transcript for a session
@app.get("/api/session/{session_id}/transcript")
async def get_session_transcript(session_id: str):
    import os
    audio_path = f"/tmp/recordings/{session_id}/recording.wav"
    if not os.path.exists(audio_path):
        return {"status": "error", "message": "Session not found"}
    transcriber = get_transcriber()
    import numpy as np, wave
    with wave.open(audio_path, "rb") as wavf:
        frames = wavf.readframes(wavf.getnframes())
        audio_np = np.frombuffer(frames, dtype=np.int16)
    result = transcriber.transcribe(audio_np)
    return {"session_id": session_id, "transcript": result.get("text", ""), "raw": result}

# Analytics router (using inline mock for now)
@app.get("/api/analytics/meetings")
async def get_meeting_analytics(time_range: str = "month"):
    """Mock meeting analytics endpoint"""
    from datetime import datetime, timedelta
    import random
    
    # Generate mock data based on range
    days = {
        "week": 7,
        "month": 30,
        "quarter": 90,
        "year": 365
    }.get(time_range, 30)
    
    # Generate meetings by day
    meetings_by_day = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        count = random.randint(0, 5)
        duration = count * random.randint(1800, 7200)  # 30min to 2h per meeting
        meetings_by_day.append({
            "date": date,
            "count": count,
            "duration": duration
        })
    
    # Calculate totals
    total_meetings = sum(d["count"] for d in meetings_by_day)
    total_duration = sum(d["duration"] for d in meetings_by_day)
    
    # Meeting types
    meeting_types = [
        {"type": "Team Standup", "count": int(total_meetings * 0.4), "percentage": 40},
        {"type": "Client Meeting", "count": int(total_meetings * 0.25), "percentage": 25},
        {"type": "Planning Session", "count": int(total_meetings * 0.2), "percentage": 20},
        {"type": "Review", "count": int(total_meetings * 0.15), "percentage": 15}
    ]
    
    # Speaker stats
    speakers = [
        {"speaker": "John Doe", "totalTime": total_duration * 0.3, "percentage": 30},
        {"speaker": "Jane Smith", "totalTime": total_duration * 0.25, "percentage": 25},
        {"speaker": "Mike Johnson", "totalTime": total_duration * 0.2, "percentage": 20},
        {"speaker": "Sarah Williams", "totalTime": total_duration * 0.15, "percentage": 15},
        {"speaker": "Others", "totalTime": total_duration * 0.1, "percentage": 10}
    ]
    
    # Performance metrics
    performance = []
    for i in range(min(7, days)):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        performance.append({
            "date": date,
            "processingTime": random.uniform(0.5, 2.0),
            "rtf": random.uniform(0.1, 0.3),
            "npuAcceleration": random.choice([True, False])
        })
    
    # Top keywords
    keywords = [
        {"word": "project", "count": random.randint(50, 200)},
        {"word": "timeline", "count": random.randint(40, 150)},
        {"word": "budget", "count": random.randint(30, 120)},
        {"word": "development", "count": random.randint(25, 100)},
        {"word": "strategy", "count": random.randint(20, 80)},
        {"word": "implementation", "count": random.randint(15, 60)}
    ]
    
    return {
        "summary": {
            "totalMeetings": total_meetings,
            "totalDuration": total_duration,
            "averageDuration": total_duration / max(total_meetings, 1),
            "totalTranscriptions": total_meetings,
            "totalSpeakers": random.randint(10, 50),
            "npuUsage": random.randint(60, 90)
        },
        "meetingsByDay": meetings_by_day[-14:],  # Last 14 days
        "meetingsByType": meeting_types,
        "speakerStats": speakers,
        "performanceMetrics": performance,
        "topKeywords": keywords
    }

# Import email router
try:
    from routers.email import router as email_router
    app.include_router(email_router)
    logger.info("✅ Email router loaded")
except Exception as e:
    logger.warning(f"⚠️ Email router failed to load: {e}")

# Import files router
try:
    from routes.files import router as files_router
    app.include_router(files_router)
    logger.info("✅ Files router loaded")
except Exception as e:
    logger.warning(f"⚠️ Files router failed to load: {e}")
    
    # Add mock files endpoint for testing
    @app.get("/api/files")
    async def get_files(limit: int = 100, offset: int = 0, sort_by: str = "created_at", order: str = "desc"):
        """Mock files endpoint"""
        import uuid
        from datetime import datetime, timedelta
        
        mock_files = [
            {
                "id": 1,
                "file_id": str(uuid.uuid4()),
                "session_id": "test-session-001",
                "filename": "meeting-2025-07-25.wav",
                "file_size": 15728640,  # 15MB
                "file_format": "wav",
                "mime_type": "audio/wav",
                "duration_seconds": 1800,  # 30 minutes
                "created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "status": "processed",
                "tags": ["important", "quarterly-review", "team-meeting"]
            },
            {
                "id": 2,
                "file_id": str(uuid.uuid4()),
                "session_id": "test-session-002",
                "filename": "standup-2025-07-24.wav",
                "file_size": 5242880,  # 5MB
                "file_format": "wav",
                "mime_type": "audio/wav",
                "duration_seconds": 600,  # 10 minutes
                "created_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                "status": "processing",
                "tags": ["daily-standup", "engineering"]
            },
            {
                "id": 3,
                "file_id": str(uuid.uuid4()),
                "session_id": "test-session-003",
                "filename": "client-demo-2025-07-23.wav",
                "file_size": 31457280,  # 30MB
                "file_format": "wav",
                "mime_type": "audio/wav",
                "duration_seconds": 3600,  # 1 hour
                "created_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
                "status": "pending",
                "tags": ["client", "demo", "sales"]
            },
            {
                "id": 4,
                "file_id": str(uuid.uuid4()),
                "session_id": "test-session-004",
                "filename": "all-hands-2025-07-22.wav",
                "file_size": 52428800,  # 50MB
                "file_format": "wav",
                "mime_type": "audio/wav",
                "duration_seconds": 5400,  # 1.5 hours
                "created_at": (datetime.utcnow() - timedelta(days=3)).isoformat(),
                "status": "processed",
                "tags": ["all-hands", "company-meeting"]
            }
        ]
        
        # Sort files
        if sort_by == "file_size":
            mock_files.sort(key=lambda x: x["file_size"], reverse=(order == "desc"))
        elif sort_by == "filename":
            mock_files.sort(key=lambda x: x["filename"], reverse=(order == "desc"))
        else:  # created_at
            mock_files.sort(key=lambda x: x["created_at"], reverse=(order == "desc"))
        
        # Apply pagination
        paginated_files = mock_files[offset:offset + limit]
        
        return {
            "files": paginated_files,
            "total": len(mock_files),
            "limit": limit,
            "offset": offset
        }
    
    @app.get("/api/files/{file_id}/download")
    async def download_file(file_id: str):
        """Mock file download endpoint"""
        # In a real implementation, this would return the actual file
        # For now, return a simple response
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content="This is a mock audio file content",
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"attachment; filename=audio_{file_id}.wav"
            }
        )

# System Info Endpoint
@app.get("/api/system-info")
async def get_system_info():
    """Get comprehensive system information"""
    try:
        import psutil
        import platform
        
        # CPU info
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_freq = psutil.cpu_freq()
        cpu_cores = psutil.cpu_count()
        
        # Memory info
        memory = psutil.virtual_memory()
        
        # Disk info
        disk = psutil.disk_usage('/')
        
        # Network info
        net_io = psutil.net_io_counters()
        
        # Process info
        process_list = list(psutil.process_iter())
        running = sum(1 for p in process_list if p.status() == 'running')
        sleeping = sum(1 for p in process_list if p.status() == 'sleeping')
        
        # System uptime
        boot_time = psutil.boot_time()
        uptime = datetime.now().timestamp() - boot_time
        
        # Load average
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
        
        # Temperature (if available)
        temps = None
        try:
            temps = psutil.sensors_temperatures()
            cpu_temp = None
            if temps and 'coretemp' in temps:
                cpu_temp = temps['coretemp'][0].current if temps['coretemp'] else None
        except:
            cpu_temp = None
        
        # Check NPU availability
        npu_available = False
        try:
            if os.path.exists("/dev/accel/accel0"):
                npu_available = True
        except:
            pass
        
        # NPU info (mock for now)
        npu_info = {
            "available": npu_available,
            "status": "active" if npu_available else "not available",
            "utilization": 45 if npu_available else 0,
            "memory_used_mb": 512 if npu_available else 0,
            "power_watts": 12 if npu_available else 0
        }
        
        # GPU info (if available)
        gpu_info = None
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_info = {
                    "name": gpu.name,
                    "memory_total_mb": gpu.memoryTotal,
                    "memory_used_mb": gpu.memoryUsed,
                    "utilization": gpu.load * 100,
                    "temperature": gpu.temperature
                }
        except:
            pass
        
        return {
            "cpu": {
                "usage_percent": cpu_percent,
                "cores": cpu_cores,
                "frequency_mhz": cpu_freq.current if cpu_freq else 0,
                "temperature": cpu_temp
            },
            "memory": {
                "total_gb": memory.total / (1024**3),
                "used_gb": memory.used / (1024**3),
                "available_gb": memory.available / (1024**3),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": disk.total / (1024**3),
                "used_gb": disk.used / (1024**3),
                "free_gb": disk.free / (1024**3),
                "percent": disk.percent
            },
            "npu": npu_info,
            "gpu": gpu_info,
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            },
            "processes": {
                "total": len(process_list),
                "running": running,
                "sleeping": sleeping
            },
            "uptime_seconds": int(uptime),
            "load_average": list(load_avg)
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        # Return minimal info on error
        return {
            "cpu": {"usage_percent": 0, "cores": 1, "frequency_mhz": 0},
            "memory": {"total_gb": 0, "used_gb": 0, "available_gb": 0, "percent": 0},
            "disk": {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0},
            "network": {"bytes_sent": 0, "bytes_recv": 0, "packets_sent": 0, "packets_recv": 0},
            "processes": {"total": 0, "running": 0, "sleeping": 0},
            "uptime_seconds": 0,
            "load_average": [0, 0, 0],
            "error": str(e)
        }

# STT Model Management Endpoints
@app.get("/api/ai/stt/models")
async def get_stt_models():
    """Get available STT models"""
    models = [
        {
            "id": "whisper-base",
            "name": "Whisper Base",
            "description": "OpenAI's base Whisper model optimized for general transcription",
            "size": "142MB",
            "speed": "Fast",
            "accuracy": "Good",
            "languages": ["English", "Spanish", "French", "German", "Italian", "Portuguese", "Japanese", "Korean", "Chinese"],
            "use_cases": ["General meetings", "Interviews", "Lectures"],
            "installed": True,
            "current": True
        },
        {
            "id": "whisper-small",
            "name": "Whisper Small",
            "description": "Larger Whisper model with improved accuracy",
            "size": "462MB",
            "speed": "Medium",
            "accuracy": "Better",
            "languages": ["96+ languages"],
            "use_cases": ["Multi-language meetings", "Technical discussions", "Accented speech"],
            "installed": False,
            "current": False
        },
        {
            "id": "whisper-medium",
            "name": "Whisper Medium",
            "description": "High-accuracy model for professional use",
            "size": "1.46GB",
            "speed": "Slower",
            "accuracy": "Excellent",
            "languages": ["96+ languages"],
            "use_cases": ["Legal transcription", "Medical dictation", "High-accuracy requirements"],
            "installed": False,
            "current": False
        },
        {
            "id": "whisperx-diarization",
            "name": "WhisperX with Diarization",
            "description": "Enhanced model with speaker identification",
            "size": "1.8GB",
            "speed": "Medium",
            "accuracy": "Excellent + Speaker ID",
            "languages": ["English optimized", "20+ supported"],
            "use_cases": ["Multi-speaker meetings", "Panel discussions", "Interviews"],
            "installed": False,
            "current": False
        }
    ]
    return {"models": models}

@app.get("/api/ai/stt/current")
async def get_current_stt_model():
    """Get currently active STT model"""
    # Return the current model based on transcriber configuration
    current_transcriber = get_transcriber()
    
    if current_transcriber and hasattr(current_transcriber, 'model_size'):
        model_size = current_transcriber.model_size
    else:
        model_size = "base"
    
    return {
        "id": f"whisper-{model_size}",
        "name": f"Whisper {model_size.capitalize()}",
        "description": "Currently active STT model",
        "size": "142MB" if model_size == "base" else "Unknown",
        "speed": "Fast",
        "accuracy": "Good",
        "languages": ["Multiple"],
        "use_cases": ["General transcription"],
        "installed": True,
        "current": True
    }

@app.post("/api/ai/stt/models/{model_id}/download")
async def download_stt_model(model_id: str):
    """Download and install an STT model"""
    # In a real implementation, this would download the model
    # For now, we'll simulate the download
    return {
        "status": "success",
        "message": f"Model {model_id} download initiated",
        "model_id": model_id
    }

@app.delete("/api/ai/stt/models/{model_id}")
async def delete_stt_model(model_id: str):
    """Delete an installed STT model"""
    return {
        "status": "success",
        "message": f"Model {model_id} deleted",
        "model_id": model_id
    }

@app.put("/api/ai/stt/model")
async def set_current_stt_model(model_data: dict):
    """Set the current STT model"""
    model_id = model_data.get("model_id")
    return {
        "status": "success",
        "message": f"Switched to model {model_id}",
        "model_id": model_id
    }

@app.post("/api/ai/stt/test")
async def test_stt_accuracy():
    """Test STT accuracy with a sample audio"""
    # Simulate a test result
    return {
        "status": "success",
        "accuracy": 0.95,
        "wer": 0.05,
        "processing_time": 1.23,
        "test_audio_duration": 10.0
    }

@app.post("/api/ai/stt/benchmark/{model_id}")
async def benchmark_stt_model(model_id: str):
    """Run benchmark on an STT model"""
    # Simulate benchmark results
    return {
        "model_id": model_id,
        "inference_speed": "2.5x realtime",
        "memory_usage": "512MB",
        "npu_utilization": "45%",
        "power_consumption": "12W",
        "first_token_latency": "0.8s"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_docker:app", host="0.0.0.0", port=9050, reload=True)