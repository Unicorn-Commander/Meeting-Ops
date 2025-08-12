"""
LLM Settings API - Manage LLM endpoints and configurations
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional, Any
import logging
import sys
import os

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.llm_config import llm_config_manager, LLMEndpoint, LLMProvider

from auth.dependencies import get_current_user
from auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-settings", tags=["llm-settings"])

@router.get("/endpoints")
async def get_endpoints(
    current_user: User = Depends(get_current_user)
):
    """Get all configured LLM endpoints"""
    config = llm_config_manager.config
    return {
        "endpoints": [e.dict() for e in config.endpoints],
        "active_endpoint": config.active_endpoint,
        "fallback_enabled": config.fallback_enabled,
        "timeout_seconds": config.timeout_seconds,
        "retry_attempts": config.retry_attempts
    }

@router.get("/endpoints/{name}")
async def get_endpoint(
    name: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific endpoint configuration"""
    for endpoint in llm_config_manager.config.endpoints:
        if endpoint.name == name:
            return endpoint.dict()
    
    raise HTTPException(status_code=404, detail=f"Endpoint '{name}' not found")

@router.post("/endpoints")
async def add_endpoint(
    endpoint_data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Add a new LLM endpoint"""
    try:
        # Validate provider
        if endpoint_data.get('provider') not in [p.value for p in LLMProvider]:
            raise ValueError(f"Invalid provider: {endpoint_data.get('provider')}")
        
        endpoint = LLMEndpoint(**endpoint_data)
        llm_config_manager.add_endpoint(endpoint)
        
        return {
            "success": True,
            "message": f"Endpoint '{endpoint.name}' added successfully",
            "endpoint": endpoint.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/endpoints/{name}")
async def update_endpoint(
    name: str,
    updates: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Update an existing endpoint"""
    try:
        llm_config_manager.update_endpoint(name, updates)
        
        # Find updated endpoint
        updated = None
        for e in llm_config_manager.config.endpoints:
            if e.name == name:
                updated = e
                break
        
        return {
            "success": True,
            "message": f"Endpoint '{name}' updated successfully",
            "endpoint": updated.dict() if updated else None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/endpoints/{name}")
async def delete_endpoint(
    name: str,
    current_user: User = Depends(get_current_user)
):
    """Delete an endpoint"""
    try:
        llm_config_manager.delete_endpoint(name)
        return {
            "success": True,
            "message": f"Endpoint '{name}' deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/endpoints/{name}/activate")
async def activate_endpoint(
    name: str,
    current_user: User = Depends(get_current_user)
):
    """Set an endpoint as active"""
    try:
        llm_config_manager.set_active_endpoint(name)
        return {
            "success": True,
            "message": f"Endpoint '{name}' is now active",
            "active_endpoint": name
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/endpoints/{name}/test")
async def test_endpoint(
    name: str,
    current_user: User = Depends(get_current_user)
):
    """Test an endpoint connection"""
    result = llm_config_manager.test_endpoint(name)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=503, 
            detail=f"Endpoint test failed: {result.get('error', 'Unknown error')}"
        )
    
    return result

@router.post("/config/fallback")
async def toggle_fallback(
    enabled: bool,
    current_user: User = Depends(get_current_user)
):
    """Enable or disable fallback to other endpoints"""
    llm_config_manager.config.fallback_enabled = enabled
    llm_config_manager.save_config()
    
    return {
        "success": True,
        "fallback_enabled": enabled,
        "message": f"Fallback {'enabled' if enabled else 'disabled'}"
    }

@router.post("/config/reset")
async def reset_to_defaults(
    current_user: User = Depends(get_current_user)
):
    """Reset LLM configuration to defaults"""
    llm_config_manager.config = llm_config_manager.get_default_config()
    llm_config_manager.save_config()
    
    return {
        "success": True,
        "message": "Configuration reset to defaults",
        "config": {
            "endpoints": [e.dict() for e in llm_config_manager.config.endpoints],
            "active_endpoint": llm_config_manager.config.active_endpoint
        }
    }

@router.get("/providers")
async def get_available_providers(
    current_user: User = Depends(get_current_user)
):
    """Get list of available LLM providers"""
    return {
        "providers": [
            {
                "value": LLMProvider.LOCAL_OLLAMA,
                "name": "Local Ollama",
                "description": "Ollama running locally on this machine"
            },
            {
                "value": LLMProvider.REMOTE_OLLAMA,
                "name": "Remote Ollama",
                "description": "Ollama running on a remote server"
            },
            {
                "value": LLMProvider.OPENAI,
                "name": "OpenAI",
                "description": "OpenAI GPT models (requires API key)"
            },
            {
                "value": LLMProvider.ANTHROPIC,
                "name": "Anthropic",
                "description": "Anthropic Claude models (requires API key)"
            },
            {
                "value": LLMProvider.CUSTOM,
                "name": "Custom",
                "description": "Custom LLM endpoint"
            }
        ]
    }

@router.get("/quick-switch")
async def get_quick_switch_options(
    current_user: User = Depends(get_current_user)
):
    """Get quick switch options for UI"""
    enabled_endpoints = [e for e in llm_config_manager.config.endpoints if e.enabled]
    active = llm_config_manager.config.get_active_endpoint()
    
    return {
        "active": active.name if active else None,
        "options": [
            {
                "name": e.name,
                "provider": e.provider,
                "description": e.description or f"{e.provider} - {e.model}",
                "is_active": e.name == (active.name if active else None)
            }
            for e in sorted(enabled_endpoints, key=lambda x: x.priority)
        ]
    }