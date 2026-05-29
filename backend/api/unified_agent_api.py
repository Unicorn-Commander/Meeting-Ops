"""
Unified Agent API
Simple endpoints for single meeting agent management
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict, Optional
from pydantic import BaseModel

from database.database import get_db
from auth.dependencies import get_current_user
from auth.models import User
from models.unified_agent import UnifiedMeetingAgent
from services.unified_agent_service import unified_agent_service

router = APIRouter(prefix="/api/unified-agent", tags=["Unified Agent"])

# Pydantic models
class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    system_prompt: Optional[str] = None
    provider_type: Optional[str] = None
    model_name: Optional[str] = None
    model_settings: Optional[Dict] = None  # Renamed from model_config
    progressive_config: Optional[Dict] = None
    output_template: Optional[Dict] = None

@router.get("/status")
async def get_agent_status(current_user: User = Depends(get_current_user)):
    """Get current unified agent status and configuration"""
    return unified_agent_service.get_agent_status()

@router.get("/agent")
async def get_agent(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get the current unified agent configuration"""
    agent = UnifiedMeetingAgent.get_default_agent(db)
    
    if not agent:
        # Create default agent if none exists
        agent = UnifiedMeetingAgent.create_default_agent(db)
    
    return agent.to_dict()

@router.put("/agent")
async def update_agent(
    update_request: AgentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the unified agent configuration"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")
    agent = UnifiedMeetingAgent.get_default_agent(db)
    
    if not agent:
        agent = UnifiedMeetingAgent.create_default_agent(db)
    
    # Update fields that were provided
    update_data = update_request.dict(exclude_unset=True)
    
    # model_settings is already the correct field name now
    for field, value in update_data.items():
        if hasattr(agent, field):
            setattr(agent, field, value)
    
    # Update timestamp
    agent.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(agent)
    
    return {
        "success": True,
        "message": "Agent updated successfully",
        "agent": agent.to_dict()
    }

@router.post("/agent/reset")
async def reset_agent(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Reset agent to default configuration"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")
    # Delete current agent
    current_agent = UnifiedMeetingAgent.get_default_agent(db)
    if current_agent:
        db.delete(current_agent)
        db.commit()
    
    # Create new default agent
    new_agent = UnifiedMeetingAgent.create_default_agent(db)
    
    return {
        "success": True,
        "message": "Agent reset to default configuration",
        "agent": new_agent.to_dict()
    }

@router.get("/models")
async def get_available_models(current_user: User = Depends(get_current_user)):
    """Get available models for the agent"""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        
        if response.status_code == 200:
            ollama_models = response.json().get('models', [])
            
            # Filter to supported models
            supported_models = []
            for model in ollama_models:
                model_name = model.get('name', '')
                if any(supported in model_name for supported in ['granite3.3', 'granite', 'phi4', 'gemma3n']):
                    supported_models.append({
                        "name": model_name,
                        "size": model.get('size', 0),
                        "modified_at": model.get('modified_at', ''),
                        "recommended": "granite3.3" in model_name
                    })
            
            return {
                "available": True,
                "models": supported_models,
                "default": "granite3.3:8b"
            }
        else:
            return {
                "available": False,
                "error": "Ollama not responding",
                "models": [],
                "default": "granite3.3:8b"
            }
            
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "models": [],
            "default": "granite3.3:8b"
        }

@router.get("/providers")
async def get_available_providers(current_user: User = Depends(get_current_user)):
    """Get available AI providers"""
    return {
        "providers": [
            {
                "type": "ollama",
                "name": "Ollama (Local)",
                "description": "Local model inference with granite3.3:8b",
                "recommended": True,
                "available": True  # TODO: Check actual availability
            },
            {
                "type": "openai", 
                "name": "OpenAI",
                "description": "GPT models via OpenAI API",
                "recommended": False,
                "available": False  # TODO: Check API key
            },
            {
                "type": "anthropic",
                "name": "Anthropic",
                "description": "Claude models via Anthropic API", 
                "recommended": False,
                "available": False  # TODO: Check API key
            }
        ],
        "default": "ollama"
    }

@router.post("/test")
async def test_agent(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Test the current agent configuration with sample text"""
    agent = UnifiedMeetingAgent.get_default_agent(db)
    
    if not agent:
        raise HTTPException(status_code=404, detail="No agent configured")
    
    # Test with sample transcript
    sample_transcript = """
    John: Welcome everyone to our Q4 planning meeting. We need to discuss the budget for next quarter.
    Sarah: I've prepared the financial projections. We're looking at a 15% increase in marketing spend.
    Mike: That sounds reasonable. What about the product development timeline?
    Sarah: We should have the new feature ready by December 15th. John, can you handle the client communication?
    John: Absolutely. I'll reach out to the key accounts this week.
    """
    
    try:
        import requests
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": agent.model_name,
                "prompt": f"""{agent.system_prompt}

TEST TRANSCRIPT:
{sample_transcript}

RESPOND WITH JSON:
{{
    "executive": "Brief summary",
    "bullets": ["Key point 1", "Key point 2"],
    "actions": [{{"action": "Task", "owner": "Person", "priority": "medium"}}],
    "decisions": ["Decision made"],
    "title": "Meeting title"
}}""",
                "stream": False,
                "format": "json",
                "options": agent.model_config
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            try:
                import json
                parsed_result = json.loads(result)
                return {
                    "success": True,
                    "test_result": parsed_result,
                    "model_used": agent.model_name,
                    "response_time": "< 30s"
                }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": "Model returned invalid JSON",
                    "raw_response": result
                }
        else:
            return {
                "success": False,
                "error": f"Model request failed: {response.status_code}",
                "model": agent.model_name
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "model": agent.model_name
        }
