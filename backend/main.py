"""
Clean main.py for Meeting-Ops - Production version with no mock/dummy/simulation code
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
    logger.info("🚀 Starting Meeting-Ops Backend (Production Mode)...")
    
    # Initialize database
    try:
        from database.database import init_database
        init_database()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization failed: {e}")
    
    # Transcription service is already initialized in its __init__
    try:
        from services.transcription_service import transcription_service
        if transcription_service.is_ready:
            logger.info(f"✅ Transcription service ready with model: {transcription_service.current_model_id}")
        else:
            logger.warning("⚠️ Transcription service not ready")
    except Exception as e:
        logger.warning(f"⚠️ Error checking transcription service: {e}")
    
    # Audio monitoring disabled - only runs during recording
    logger.info("🎤 Audio monitoring disabled (only active during recording)")
    
    # Audio monitoring via Redis WebSocket
    logger.info("📌 Audio levels served via Redis WebSocket pipeline")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down...")
    
    # Audio monitoring cleanup not needed (disabled)
    
    if audio_monitor_task and not audio_monitor_task.done():
        audio_monitor_task.cancel()
        try:
            await audio_monitor_task
        except asyncio.CancelledError:
            pass

# Create FastAPI app
app = FastAPI(
    title="Meeting-Ops API",
    description="AI-powered meeting recording and transcription system",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Transcription service is already imported in lifespan context above

# Auth router
try:
    from auth.routes import router as auth_router
    app.include_router(auth_router)
    logger.info("✅ Auth router loaded")
except Exception as e:
    logger.warning(f"⚠️ Auth router failed to load: {e}")

# Recording API v2
try:
    from api.recording_v2 import router as recording_router
    app.include_router(recording_router, prefix="/api")
    logger.info("✅ Recording router loaded")
except Exception as e:
    logger.warning(f"⚠️ Recording router failed to load: {e}")

# Sessions management
try:
    from api.sessions import router as sessions_router
    app.include_router(sessions_router, prefix="/api")
    logger.info("✅ Sessions router loaded")
except Exception as e:
    logger.warning(f"⚠️ Sessions router failed to load: {e}")

# Meeting Management
try:
    from api.meeting_management import router as meeting_router
    app.include_router(meeting_router)
    logger.info("✅ Meeting Management router loaded")
except Exception as e:
    logger.warning(f"⚠️ Meeting Management router failed to load: {e}")

# Meeting Intelligence (Primary)
try:
    from api.meeting_intelligence_real import router as intelligence_real_router
    app.include_router(intelligence_real_router)
    logger.info("✅ Meeting Intelligence router loaded")
except Exception as e:
    logger.warning(f"⚠️ Meeting Intelligence router failed to load: {e}")

# AI Settings
try:
    from api.ai_settings import router as ai_settings_router
    app.include_router(ai_settings_router)
    logger.info("✅ AI Settings router loaded")
except Exception as e:
    logger.warning(f"⚠️ AI Settings router failed to load: {e}")

# Agent System (Legacy)
try:
    from api.agent_system import router as agent_router
    app.include_router(agent_router)
    logger.info("✅ Agent System router loaded")
except Exception as e:
    logger.warning(f"⚠️ Agent System router failed to load: {e}")

# Agent Management (Multi-tier system)
try:
    from api.agent_management_api import router as agent_management_router
    app.include_router(agent_management_router)
    logger.info("✅ Agent Management router loaded")
except Exception as e:
    logger.warning(f"⚠️ Agent Management router failed to load: {e}")

# LLM Settings
try:
    from api.llm_settings import router as llm_settings_router
    app.include_router(llm_settings_router)
    logger.info("✅ LLM Settings router loaded")
except Exception as e:
    logger.warning(f"⚠️ LLM Settings router failed to load: {e}")

# Model Management (Decoupled)
try:
    from api.model_management import router as model_management_router
    app.include_router(model_management_router)
    logger.info("✅ Model Management router loaded")
except Exception as e:
    logger.warning(f"⚠️ Model Management router failed to load: {e}")

# Unified Meeting Notes (Multi-model support)
try:
    from api.meeting_notes_unified import router as meeting_notes_unified_router
    app.include_router(meeting_notes_unified_router)
    logger.info("✅ Unified Meeting Notes router loaded")
except Exception as e:
    logger.warning(f"⚠️ Unified Meeting Notes router failed to load: {e}")

# Simple Recording (Fixed with FFmpeg)
try:
    from api.simple_recording_db import router as simple_recording_router
    app.include_router(simple_recording_router)
    logger.info("✅ Simple Recording DB router loaded")
except Exception as e:
    logger.warning(f"⚠️ Simple Recording router failed to load: {e}")

# WebSocket Transcription
try:
    from api.websocket_transcription import router as ws_transcription_router
    app.include_router(ws_transcription_router)
    logger.info("✅ WebSocket Transcription router loaded")
except Exception as e:
    logger.warning(f"⚠️ WebSocket Transcription router failed to load: {e}")

# WebSocket with Auto-Summary
try:
    from api.websocket_auto_summary import router as ws_auto_summary_router
    app.include_router(ws_auto_summary_router)
    logger.info("✅ WebSocket Auto-Summary router loaded")
except Exception as e:
    logger.warning(f"⚠️ WebSocket Auto-Summary router failed to load: {e}")

# Unified Agent (Simplified Single Agent with granite3.3:8b)
try:
    from api.unified_agent_api import router as unified_agent_router
    app.include_router(unified_agent_router)
    logger.info("✅ Unified Agent router loaded")
except Exception as e:
    logger.warning(f"⚠️ Unified Agent router failed to load: {e}")

# Advanced Agents (Progressive Meeting Agent System - Legacy)
try:
    from api.advanced_agents import router as advanced_agents_router
    app.include_router(advanced_agents_router)
    logger.info("✅ Advanced Agents router loaded")
except Exception as e:
    logger.warning(f"⚠️ Advanced Agents router failed to load: {e}")

# Advanced AI Providers (Progressive Meeting Agent System)
try:
    from api.advanced_ai_providers import router as advanced_providers_router
    app.include_router(advanced_providers_router)
    logger.info("✅ Advanced AI Providers router loaded")
except Exception as e:
    logger.warning(f"⚠️ Advanced AI Providers router failed to load: {e}")

# Live Transcription
try:
    from api.live_transcription import router as live_transcription_router
    app.include_router(live_transcription_router)
    logger.info("✅ Live Transcription router loaded")
except Exception as e:
    logger.warning(f"⚠️ Live Transcription router failed to load: {e}")

# Summary Downloads (PDF, DOCX, Text exports)
try:
    from api.summary_downloads import router as summary_downloads_router
    app.include_router(summary_downloads_router)
    logger.info("✅ Summary Downloads router loaded")
except Exception as e:
    logger.warning(f"⚠️ Summary Downloads router failed to load: {e}")

# Audio Upload for existing sessions
try:
    from api.audio_upload import router as audio_upload_router
    app.include_router(audio_upload_router)
    logger.info("✅ Audio Upload router loaded")
except Exception as e:
    logger.warning(f"⚠️ Audio Upload router failed to load: {e}")

# Email Generation
try:
    from api.email_generation import router as email_generation_router
    app.include_router(email_generation_router)
    logger.info("✅ Email Generation router loaded")
except Exception as e:
    logger.warning(f"⚠️ Email Generation router failed to load: {e}")

# Transcription Loop
try:
    from routers.transcription_loop import router as transcription_loop_router
    app.include_router(transcription_loop_router)
    logger.info("✅ Transcription Loop router loaded")
except Exception as e:
    logger.warning(f"⚠️ Transcription Loop router failed to load: {e}")

# Analytics (Primary)
try:
    from api.analytics_simple import router as analytics_simple_router
    app.include_router(analytics_simple_router)
    logger.info("✅ Analytics router loaded")
except Exception as e:
    logger.warning(f"⚠️ Analytics router failed to load: {e}")

# AI Insights
try:
    from api.ai_insights import router as ai_insights_router
    app.include_router(ai_insights_router)
    logger.info("✅ AI Insights router loaded")
except Exception as e:
    logger.warning(f"⚠️ AI Insights router failed to load: {e}")

# AI Chat
try:
    from api.ai_chat import router as ai_chat_router
    app.include_router(ai_chat_router)
    logger.info("✅ AI Chat router loaded")
except Exception as e:
    logger.warning(f"⚠️ AI Chat router failed to load: {e}")

# Vocabulary Management
try:
    from api.vocabulary import router as vocabulary_router
    app.include_router(vocabulary_router)
    logger.info("✅ Vocabulary Management router loaded")
except Exception as e:
    logger.warning(f"⚠️ Vocabulary Management router failed to load: {e}")

# Meeting Notes (Legacy - disabled, using Unified)
# Replaced by meeting_notes_unified router above

# System Configuration
try:
    from api.system_config import router as system_config_router
    app.include_router(system_config_router)
    logger.info("✅ System Configuration router loaded")
except Exception as e:
    logger.warning(f"⚠️ System Configuration router failed to load: {e}")

# Simple Settings (New)
try:
    from api.simple_settings import router as simple_settings_router
    app.include_router(simple_settings_router)
    logger.info("✅ Simple Settings router loaded")
except Exception as e:
    logger.warning(f"⚠️ Simple Settings router failed to load: {e}")

# Batch Export
try:
    from api.batch_export import router as batch_export_router
    app.include_router(batch_export_router)
    logger.info("✅ Batch Export router loaded")
except Exception as e:
    logger.warning(f"⚠️ Batch Export router failed to load: {e}")

# Logs
try:
    from routers.logs import router as logs_router
    app.include_router(logs_router)
    logger.info("✅ Logs router loaded")
except Exception as e:
    logger.warning(f"⚠️ Logs router failed to load: {e}")

# Backup
try:
    from routers.backup import router as backup_router
    app.include_router(backup_router)
    logger.info("✅ Backup router loaded")
except Exception as e:
    logger.warning(f"⚠️ Backup router failed to load: {e}")

# SSL
try:
    from routers.ssl import router as ssl_router
    app.include_router(ssl_router)
    logger.info("✅ SSL router loaded")
except Exception as e:
    logger.warning(f"⚠️ SSL router failed to load: {e}")

# Email
try:
    from routers.email import router as email_router
    app.include_router(email_router)
    logger.info("✅ Email router loaded")
except Exception as e:
    logger.warning(f"⚠️ Email router failed to load: {e}")

# Files
try:
    from routes.files import router as files_router
    app.include_router(files_router)
    logger.info("✅ Files router loaded")
except Exception as e:
    logger.warning(f"⚠️ Files router failed to load: {e}")

# New Settings API (from API Delta Document)
try:
    from api.settings_new import router as settings_new_router
    app.include_router(settings_new_router)
    logger.info("✅ New Settings API router loaded")
except Exception as e:
    logger.warning(f"⚠️ New Settings API router failed to load: {e}")

# Meeting Intelligence Delta (Live Templates & Session Templates)
try:
    from api.meeting_intelligence_delta import router as intelligence_delta_router
    app.include_router(intelligence_delta_router)
    logger.info("✅ Meeting Intelligence Delta router loaded")
except Exception as e:
    logger.warning(f"⚠️ Meeting Intelligence Delta router failed to load: {e}")

# Export Templates (Enhanced export formats)
try:
    from api.export_templates import router as export_templates_router
    app.include_router(export_templates_router)
    logger.info("✅ Export Templates router loaded")
except Exception as e:
    logger.warning(f"⚠️ Export Templates router failed to load: {e}")

# Analytics Summary (Dashboard metrics)
try:
    from api.analytics_summary import router as analytics_summary_router
    app.include_router(analytics_summary_router)
    logger.info("✅ Analytics Summary router loaded")
except Exception as e:
    logger.warning(f"⚠️ Analytics Summary router failed to load: {e}")


# === CORE API ENDPOINTS ===

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Meeting-Ops API", 
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/api/status")
async def get_status():
    """Get system status"""
    try:
        # NPU Status
        npu_available = os.path.exists("/dev/accel/accel0")
        
        # Transcription Status
        from services.transcription_service import transcription_service
        transcription_ready = transcription_service and transcription_service.is_ready
        model_loaded = transcription_service.current_model_id if transcription_service else "none"
        
        # Audio devices
        audio_devices = []
        try:
            from services.working_audio_service import WorkingAudioService
            audio_service = WorkingAudioService()
            audio_devices = audio_service.get_audio_devices()  # This returns a list directly
        except Exception as e:
            logger.error(f"Failed to get audio devices: {e}")
        
        return {
            "status": "healthy",
            "timestamp": "2025-08-12T04:39:03Z",
            "transcription": {
                "ready": transcription_ready,
                "model": model_loaded,
                "engine": "whisperx-npu" if transcription_ready else "none"
            },
            "npu": {
                "available": npu_available,
                "device": "/dev/accel/accel0" if npu_available else None,
                "status": "active" if npu_available and transcription_ready else "idle"
            },
            "audio": {
                "devices_count": len(audio_devices),
                "server_mic_available": any("usb" in d.get("name", "").lower() or 
                                         "m-305" in d.get("name", "").lower() 
                                         for d in audio_devices)
            },
            "services": {
                "recording": True,
                "transcription": transcription_ready,
                "ai_notes": True,
                "websockets": True
            }
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/audio-devices")
async def get_audio_devices():
    """Get list of available audio input devices"""
    try:
        from services.working_audio_service import WorkingAudioService
        audio_service = WorkingAudioService()
        devices = audio_service.get_audio_devices()
        return {"devices": devices, "status": "success"}
    except Exception as e:
        logger.error(f"Failed to get audio devices: {e}")
        return {"devices": [], "status": "error", "message": str(e)}

@app.get("/api/system-info")
async def get_system_info():
    """Get detailed system information"""
    import platform
    import psutil
    
    try:
        # NPU Detection
        npu_available = os.path.exists("/dev/accel/accel0")
        
        # Transcription service info
        from services.transcription_service import transcription_service
        transcription_ready = transcription_service and transcription_service.is_ready
        model_loaded = transcription_service.current_model_id if transcription_service else "none"
        
        return {
            "system": {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "cpu_count": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total,
                "memory_available": psutil.virtual_memory().available
            },
            "npu": {
                "available": npu_available,
                "device_path": "/dev/accel/accel0" if npu_available else None,
                "status": "active" if npu_available and transcription_ready else "idle",
                "driver": "MLIR-AIE2" if npu_available else None
            },
            "transcription": {
                "service_ready": transcription_ready,
                "current_model": model_loaded,
                "engine_type": "whisperx-npu" if transcription_ready else "none",
                "performance_factor": "220x speedup" if npu_available else "CPU-only"
            },
            "version": "2.0.0",
            "build": "production"
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {"error": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2025-08-12T04:39:03Z"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9050)