"""
AI Models Management API Router
Handles Ollama models, STT models, templates, and LLM settings
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
import logging
import json

from auth.models import User
from auth.dependencies import require_permission, get_current_user
from services.ollama_model_manager import ollama_model_manager
from services.stt_model_manager import stt_model_manager
from services.meeting_templates import MeetingTemplates
# from services.llm_summarization_service import llm_summarization_service  # Temporarily commented

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI Models"])

# Pydantic models for requests/responses
class ModelActionRequest(BaseModel):
    model_name: str

class LLMSettingsUpdate(BaseModel):
    default_model: Optional[str] = None
    system_prompt: Optional[str] = None
    custom_instructions: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

class TemplateCreate(BaseModel):
    name: str
    description: str
    system_prompt: str
    sections: List[str]
    focus_areas: List[str]

class TestPromptRequest(BaseModel):
    model_name: str
    prompt: str
    parameters: Optional[Dict[str, Any]] = None

# Ollama Model Management Endpoints
@router.get("/ollama/models")
async def list_ollama_models(current_user: User = Depends(require_permission("ai.read"))):
    """List all available Ollama models"""
    try:
        models = await ollama_model_manager.list_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing Ollama models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ollama/pull")
async def pull_ollama_model(
    request: ModelActionRequest,
    current_user: User = Depends(require_permission("ai.write"))
):
    """Pull (download) an Ollama model"""
    try:
        result = await ollama_model_manager.pull_model(request.model_name)
        return result
    except Exception as e:
        logger.error(f"Error pulling model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/ollama/models/{model_name}")
async def delete_ollama_model(
    model_name: str,
    current_user: User = Depends(require_permission("ai.delete"))
):
    """Delete an Ollama model"""
    try:
        result = await ollama_model_manager.delete_model(model_name)
        return result
    except Exception as e:
        logger.error(f"Error deleting model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ollama/models/{model_name}/info")
async def get_ollama_model_info(
    model_name: str,
    current_user: User = Depends(require_permission("ai.read"))
):
    """Get detailed information about a model"""
    try:
        info = await ollama_model_manager.get_model_info(model_name)
        return info
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ollama/running")
async def list_running_models(current_user: User = Depends(require_permission("ai.read"))):
    """List currently loaded/running models"""
    try:
        models = await ollama_model_manager.list_running_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing running models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ollama/search")
async def search_ollama_models(
    query: Optional[str] = "",
    current_user: User = Depends(require_permission("ai.read"))
):
    """Search for available models in Ollama library"""
    try:
        models = await ollama_model_manager.search_models(query)
        return {"models": models}
    except Exception as e:
        logger.error(f"Error searching models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ollama/test")
async def test_ollama_model(
    request: TestPromptRequest,
    current_user: User = Depends(require_permission("ai.write"))
):
    """Test a model with a prompt"""
    try:
        result = await ollama_model_manager.test_model(
            request.model_name,
            request.prompt
        )
        return result
    except Exception as e:
        logger.error(f"Error testing model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ollama/parameters/{model_name}")
async def get_model_parameters(
    model_name: str,
    current_user: User = Depends(require_permission("ai.read"))
):
    """Get current parameters for a model"""
    try:
        params = await ollama_model_manager.get_model_parameters(model_name)
        return {"parameters": params}
    except Exception as e:
        logger.error(f"Error getting model parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# STT Model Management Endpoints
@router.get("/stt/models")
async def list_stt_models(current_user: User = Depends(require_permission("ai.read"))):
    """List all NPU-optimized STT models"""
    try:
        models = stt_model_manager.list_available_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing STT models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stt/download/{model_id}")
async def download_stt_model(
    model_id: str,
    current_user: User = Depends(require_permission("ai.write"))
):
    """Download and optimize an STT model for NPU"""
    try:
        result = await stt_model_manager.download_model(model_id)
        return result
    except Exception as e:
        logger.error(f"Error downloading STT model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/stt/models/{model_id}")
async def delete_stt_model(
    model_id: str,
    current_user: User = Depends(require_permission("ai.delete"))
):
    """Delete an STT model"""
    try:
        result = stt_model_manager.delete_model(model_id)
        return result
    except Exception as e:
        logger.error(f"Error deleting STT model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stt/set-current/{model_id}")
async def set_current_stt_model(
    model_id: str,
    current_user: User = Depends(require_permission("ai.write"))
):
    """Set the current active STT model"""
    try:
        result = stt_model_manager.set_current_model(model_id)
        return result
    except Exception as e:
        logger.error(f"Error setting current STT model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stt/current")
async def get_current_stt_model(current_user: User = Depends(require_permission("ai.read"))):
    """Get info about the current STT model"""
    try:
        info = stt_model_manager.get_current_model_info()
        return info
    except Exception as e:
        logger.error(f"Error getting current STT model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stt/benchmark/{model_id}")
async def benchmark_stt_model(
    model_id: str,
    current_user: User = Depends(require_permission("ai.read"))
):
    """Benchmark an STT model's performance"""
    try:
        result = stt_model_manager.benchmark_model(model_id)
        return result
    except Exception as e:
        logger.error(f"Error benchmarking STT model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stt/optimization-stats")
async def get_stt_optimization_stats(current_user: User = Depends(require_permission("ai.read"))):
    """Get NPU optimization statistics"""
    try:
        stats = stt_model_manager.get_optimization_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting optimization stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Meeting Templates Endpoints
@router.get("/templates")
async def list_meeting_templates(current_user: User = Depends(require_permission("ai.read"))):
    """List all available meeting templates"""
    try:
        templates = MeetingTemplates.list_templates()
        return {"templates": templates}
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    current_user: User = Depends(require_permission("ai.read"))
):
    """Get a specific template"""
    try:
        template = MeetingTemplates.get_template(template_id)
        return template
    except Exception as e:
        logger.error(f"Error getting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/templates")
async def create_custom_template(
    template: TemplateCreate,
    current_user: User = Depends(require_permission("ai.write"))
):
    """Create a custom template"""
    try:
        custom_template = MeetingTemplates.create_custom_template(
            name=template.name,
            description=template.description,
            system_prompt=template.system_prompt,
            sections=template.sections,
            focus_areas=template.focus_areas
        )
        # In a real implementation, save to database
        return custom_template
    except Exception as e:
        logger.error(f"Error creating template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# LLM Settings Endpoints
@router.get("/llm/settings")
async def get_llm_settings(current_user: User = Depends(require_permission("ai.read"))):
    """Get current LLM settings"""
    try:
        # In real implementation, load from database
        settings = {
            "default_model": "gemma3n:latest",
            "system_prompt": "You are a helpful meeting assistant.",
            "custom_instructions": "",
            "parameters": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 2048,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0
            }
        }
        return settings
    except Exception as e:
        logger.error(f"Error getting LLM settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/llm/settings")
async def update_llm_settings(
    settings: LLMSettingsUpdate,
    current_user: User = Depends(require_permission("ai.write"))
):
    """Update LLM settings"""
    try:
        # In real implementation, save to database
        return {"message": "Settings updated successfully"}
    except Exception as e:
        logger.error(f"Error updating LLM settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket for model download progress
@router.websocket("/ws/model-progress/{task_id}")
async def model_progress_websocket(websocket: WebSocket, task_id: str):
    """WebSocket for real-time model download progress"""
    await websocket.accept()
    try:
        # In real implementation, this would track actual download progress
        # For now, simulate progress
        import asyncio
        for i in range(0, 101, 10):
            await websocket.send_json({
                "progress": i,
                "status": "downloading" if i < 50 else "optimizing" if i < 100 else "complete"
            })
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()