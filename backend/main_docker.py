"""
Simplified main.py for Docker deployment
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Unicorn Commander (Docker Mode)...")
    yield
    # Shutdown
    logger.info("👋 Shutting down...")

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

# Import simplified auth for Docker
try:
    from auth_docker import router as auth_router
    app.include_router(auth_router)
    logger.info("✅ Auth router loaded")
except Exception as e:
    logger.warning(f"⚠️ Auth router failed to load: {e}")

# Try to import other routers (optional)
try:
    from routers import sessions, settings, status
    app.include_router(sessions.router)
    app.include_router(settings.router)
    app.include_router(status.router)
    logger.info("✅ Additional routers loaded")
except Exception as e:
    logger.warning(f"⚠️ Some routers failed to load: {e}")

# Health check endpoint
@app.get("/api/status")
async def get_status():
    return {
        "status": "running",
        "mode": "docker",
        "transcriber_ready": False,
        "npu_available": False,
        "speaker_diarization_ready": False,
        "active_sessions": 0,
        "system_info": {
            "onnx_whisper_ready": False,
            "npu_available": False,
            "onnx_providers": [],
            "model_path": None
        },
        "diarizer_info": {
            "ready": False,
            "device": "cpu",
            "model": "not-loaded"
        }
    }

@app.get("/")
async def root():
    return {"message": "Unicorn Commander API - Use /docs for API documentation"}

if __name__ == "__main__":
    uvicorn.run("main_docker:app", host="0.0.0.0", port=9050, reload=True)