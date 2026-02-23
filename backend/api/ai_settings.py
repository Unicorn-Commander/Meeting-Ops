"""
AI Settings API endpoints for managing LLM and transcription configurations
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import json
import logging

router = APIRouter(prefix="/api", tags=["ai-settings"])
logger = logging.getLogger(__name__)


class ModelSwitchRequest(BaseModel):
    model_id: str


@router.get("/settings/models")
async def get_model_info():
    """Return actual running model configuration from the model registry"""
    from config.model_registry import MODEL_REGISTRY, get_active_model

    active = get_active_model()

    # Get LLM status from unified_llm_service
    llm_info = {"llamacpp_available": False, "base_url": "", "model": active["model_id"]}
    try:
        from services.unified_llm_service import llm_service
        llm_info = llm_service.get_status()
    except Exception as e:
        llm_info["error"] = str(e)

    # Get whisper-server (Vulkan iGPU) status
    whisper_server_info: Dict[str, Any] = {"available": False}
    try:
        from services.whisper_server_client import whisper_server_client
        ws_available = whisper_server_client.is_available()
        whisper_server_info = {
            "available": ws_available,
            "model": "large-v3-turbo",
            "backend": "whisper.cpp Vulkan (780M iGPU)",
            "endpoint": whisper_server_client.base_url,
            "speed": "~9.6x realtime",
            "rtf": 0.104,
        }
    except Exception as e:
        whisper_server_info["error"] = str(e)

    # Get fallback STT model info from transcription_service
    stt_fallback: Dict[str, Any] = {}
    try:
        from services.transcription_service import transcription_service
        stt_fallback = transcription_service.get_current_model_info()
    except Exception as e:
        stt_fallback = {"error": str(e)}

    return {
        "llm": {
            "model": active["model_id"],
            "model_label": active["display_name"],
            "endpoint": llm_info.get("base_url", "http://localhost:11437"),
            "available": llm_info.get("llamacpp_available", False),
            "active_engine": llm_info.get("active_engine", "none"),
            "backend": "llama.cpp Vulkan",
            "speed_estimate": active.get("speed_estimate", "unknown"),
            "context_window": active.get("ctx_size", 8192),
            "vram_usage": active.get("vram_estimate", "unknown"),
            "max_tokens_multiplier": active.get("max_tokens_multiplier", 1.0),
        },
        "stt": {
            "primary": whisper_server_info,
            "fallback": stt_fallback,
            "active": "whisper-server-vulkan" if whisper_server_info.get("available") else "cpu-fallback",
        },
        "available_llm_models": [
            {
                "name": model_id,
                "label": entry["display_name"],
                "speed_estimate": entry.get("speed_estimate", "unknown"),
                "context_window": entry.get("ctx_size", 8192),
                "vram_usage": entry.get("vram_estimate", "unknown"),
                "best_for": entry.get("best_for", ""),
                "max_tokens_multiplier": entry.get("max_tokens_multiplier", 1.0),
                "endpoint": "http://localhost:11437",
                "status": "active" if model_id == active["model_id"] else "available",
            }
            for model_id, entry in MODEL_REGISTRY.items()
        ],
    }


@router.get("/settings/models/available")
async def get_available_models():
    """Return list of models from the registry with active indicator"""
    from config.model_registry import MODEL_REGISTRY, get_active_model

    active = get_active_model()
    models = []
    for model_id, entry in MODEL_REGISTRY.items():
        models.append({
            "model_id": model_id,
            "display_name": entry["display_name"],
            "gguf_file": entry.get("gguf_file", ""),
            "speed_estimate": entry.get("speed_estimate", "unknown"),
            "vram_estimate": entry.get("vram_estimate", "unknown"),
            "ctx_size": entry.get("ctx_size", 8192),
            "best_for": entry.get("best_for", ""),
            "max_tokens_multiplier": entry.get("max_tokens_multiplier", 1.0),
            "is_active": model_id == active["model_id"],
        })
    return {"models": models, "active_model": active["model_id"]}


@router.post("/settings/models/active")
async def set_active_model(request: ModelSwitchRequest):
    """Set the active LLM model via settings_manager.

    Note: Switching the loaded model requires restarting the llama-gpu
    container with a different GGUF file. This endpoint updates the
    persisted setting; the container must be restarted separately.
    """
    from config.model_registry import MODEL_REGISTRY
    from services.settings_manager import settings_manager

    if request.model_id not in MODEL_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown model: {request.model_id}. Available: {list(MODEL_REGISTRY.keys())}")

    success = settings_manager.update_setting("ai.llm_model", request.model_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update model setting")

    entry = MODEL_REGISTRY[request.model_id]
    logger.info(f"Active LLM model switched to: {request.model_id} ({entry['display_name']})")

    return {
        "status": "success",
        "active_model": request.model_id,
        "display_name": entry["display_name"],
        "message": f"Model set to {entry['display_name']}. If the llama.cpp container is running a different GGUF, restart it to load {entry['gguf_file']}.",
    }


@router.get("/settings/ai")
async def get_ai_settings():
    """Get current AI settings from the centralized settings manager"""
    try:
        from services.settings_manager import settings_manager
        all_settings = settings_manager.get_all_settings()
        return all_settings.get("ai", {})
    except Exception as e:
        logger.warning(f"Could not load AI settings: {e}")
        return {}


@router.put("/settings/ai")
async def update_ai_settings(settings: Dict[str, Any]):
    """Update AI settings"""
    try:
        from services.settings_manager import settings_manager
        success = settings_manager.update_category_settings("ai", settings)
        if success:
            return {"status": "success", "message": "AI settings updated"}
        raise HTTPException(status_code=500, detail="Failed to update settings")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
