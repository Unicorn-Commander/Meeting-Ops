"""
Meeting-Ops Backend - Production main.py
Clean router loading with status tracking and real timestamps.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
import os
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router loading status tracking
loaded_routers: List[str] = []
failed_routers: List[dict] = []

audio_monitor_task = None


def _load_router(app: FastAPI, name: str, module_path: str, router_attr: str = "router",
                 prefix: str = "", required: bool = False):
    """Load a router with status tracking. Required routers raise on failure."""
    try:
        module = __import__(module_path, fromlist=[router_attr])
        router = getattr(module, router_attr)
        app.include_router(router, prefix=prefix if prefix else "")
        loaded_routers.append(name)
        logger.info(f"Loaded router: {name}")
    except Exception as e:
        entry = {"name": name, "error": str(e)}
        failed_routers.append(entry)
        if required:
            logger.error(f"REQUIRED router failed: {name} - {e}")
            raise RuntimeError(f"Required router '{name}' failed to load: {e}")
        else:
            logger.warning(f"Optional router skipped: {name} - {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global audio_monitor_task

    logger.info("Starting Meeting-Ops Backend...")

    # Initialize database
    try:
        from database.database import init_database
        init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}")

    # Clean up stale sessions (created but never started)
    try:
        from database.database import SessionLocal
        from database.models import RecordingSession
        from datetime import timedelta
        cleanup_db = SessionLocal()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        stale = cleanup_db.query(RecordingSession).filter(
            RecordingSession.status == "active",
            RecordingSession.started_at.is_(None),
            RecordingSession.created_at < cutoff
        ).all()
        if stale:
            for s in stale:
                s.status = "abandoned"
            cleanup_db.commit()
            logger.info(f"Cleaned up {len(stale)} stale sessions")
        cleanup_db.close()
    except Exception as e:
        logger.warning(f"Stale session cleanup failed: {e}")

    # Check transcription service
    try:
        from services.transcription_service import transcription_service
        if transcription_service.is_ready:
            logger.info(f"Transcription service ready: {transcription_service.current_model_id}")
        else:
            logger.warning("Transcription service not ready")
    except Exception as e:
        logger.warning(f"Transcription service check failed: {e}")

    logger.info(f"Routers loaded: {len(loaded_routers)}, failed: {len(failed_routers)}")

    yield

    logger.info("Shutting down...")
    if audio_monitor_task and not audio_monitor_task.done():
        audio_monitor_task.cancel()
        try:
            await audio_monitor_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Meeting-Ops API",
    description="AI-powered meeting recording and transcription system",
    version="0.0.3",
    lifespan=lifespan
)

_cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

app.add_middleware(
    CORSMiddleware,
    # In production: set CORS_ORIGINS env var. For LAN appliance: allow frontend port.
    allow_origins=_cors_origins or [],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?$" if not _cors_origins else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === REQUIRED ROUTERS (fail fast if missing) ===
_load_router(app, "auth", "auth.routes", required=True)
_load_router(app, "recording", "api.simple_recording_db", required=True)
_load_router(app, "sessions", "api.sessions", prefix="/api", required=True)

# === CORE ROUTERS (optional but expected) ===
_load_router(app, "meeting_management", "api.meeting_management")
_load_router(app, "meeting_intelligence", "api.meeting_intelligence_real")
_load_router(app, "ai_settings", "api.ai_settings")
_load_router(app, "agent_management", "api.agent_management_api")
_load_router(app, "meeting_notes", "api.meeting_notes_unified")
_load_router(app, "websocket_transcription", "api.websocket_transcription")
_load_router(app, "websocket_auto_summary", "api.websocket_auto_summary")
_load_router(app, "unified_agent", "api.unified_agent_api")
_load_router(app, "live_transcription", "api.live_transcription")
_load_router(app, "analytics", "api.analytics_simple")
_load_router(app, "ai_insights", "api.ai_insights")
_load_router(app, "ai_chat", "api.ai_chat")
_load_router(app, "vocabulary", "api.vocabulary")
_load_router(app, "batch_export", "api.batch_export")
_load_router(app, "audio_upload", "api.audio_upload")
_load_router(app, "simple_settings", "api.simple_settings")

# === SATELLITE DEVICE ROUTERS (optional) ===
_load_router(app, "satellite_api", "api.satellite_api")
_load_router(app, "websocket_satellite", "api.websocket_satellite")

# === COMPANION APP ROUTERS (optional) ===
_load_router(app, "websocket_remote_audio", "api.websocket_remote_audio")


# === CORE API ENDPOINTS ===

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Meeting-Ops API",
        "version": "0.0.2",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check with router status"""
    has_failures = len(failed_routers) > 0
    return {
        "status": "degraded" if has_failures else "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "routers_loaded": len(loaded_routers),
        "routers_failed": failed_routers if has_failures else [],
    }


@app.get("/api/status")
async def get_status():
    """Get system status"""
    try:
        npu_available = os.path.exists("/dev/accel/accel0")

        from services.transcription_service import transcription_service
        transcription_ready = transcription_service and transcription_service.is_ready
        model_loaded = transcription_service.current_model_id if transcription_service else "none"

        audio_devices = []
        try:
            from services.working_audio_service import WorkingAudioService
            audio_service = WorkingAudioService()
            audio_devices = audio_service.get_audio_devices()
        except Exception as e:
            logger.error(f"Failed to get audio devices: {e}")

        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            },
            "routers": {
                "loaded": len(loaded_routers),
                "failed": len(failed_routers),
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
        npu_available = os.path.exists("/dev/accel/accel0")

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
            "version": "0.0.2",
            "build": "production"
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9050)
