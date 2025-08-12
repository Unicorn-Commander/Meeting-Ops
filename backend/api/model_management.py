"""
Model Management API
Endpoints for managing model configurations and providers
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database import get_db, SessionLocal
    from models.model_config import ModelConfiguration, ModelTemplate
    from models.agent_config import AgentConfiguration
    from services.model_providers import ModelProviderFactory, ModelParameters
    from api.auth import get_current_user
    from models.user import User
except ImportError:
    # Fallback imports
    def get_db():
        return None
    class ModelConfiguration:
        pass
    class ModelTemplate:
        pass
    class AgentConfiguration:
        pass
    def get_current_user():
        return None
    class User:
        pass
    from services.model_providers import ModelProviderFactory, ModelParameters
from sqlalchemy.orm import Session


router = APIRouter(prefix="/api/models", tags=["Model Management"])


class ModelConfigRequest(BaseModel):
    """Request to create or update a model configuration"""
    name: str
    provider: str = Field(..., description="ollama, openai, anthropic, or custom")
    model_name: str = Field(..., description="Model identifier like granite3.3:8b or gpt-4")
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    
    # Basic parameters (0-10 scale for UI)
    temperature: int = Field(7, ge=0, le=10)
    max_tokens: int = Field(2048, ge=100, le=32000)
    top_p: int = Field(9, ge=0, le=10)
    frequency_penalty: int = Field(0, ge=0, le=10)
    presence_penalty: int = Field(0, ge=0, le=10)
    
    # Advanced parameters
    context_window: int = Field(8192, ge=1024, le=128000)
    gpu_layers: Optional[int] = Field(99, ge=0, le=200)
    batch_size: Optional[int] = Field(512, ge=1, le=2048)
    repeat_penalty: Optional[int] = Field(11, ge=10, le=20)  # 1.0-2.0 as 10-20
    seed: Optional[int] = None
    
    # Provider-specific parameters
    provider_params: Dict[str, Any] = Field(default_factory=dict)
    
    is_default: bool = False
    tags: List[str] = Field(default_factory=list)


class ModelConfigResponse(BaseModel):
    """Response with model configuration"""
    id: str
    name: str
    provider: str
    model_name: str
    api_endpoint: Optional[str]
    
    temperature: int
    max_tokens: int
    top_p: int
    frequency_penalty: int
    presence_penalty: int
    
    context_window: int
    gpu_layers: Optional[int]
    batch_size: Optional[int]
    repeat_penalty: Optional[int]
    seed: Optional[int]
    
    provider_params: Dict[str, Any]
    is_default: bool
    is_active: bool
    tags: List[str]
    
    created_at: datetime
    updated_at: Optional[datetime]
    last_tested: Optional[datetime]
    test_status: Optional[str]


class ModelTestRequest(BaseModel):
    """Request to test a model configuration"""
    prompt: str = "Hello, please respond with 'Model test successful' if you can read this."
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = 50


class ModelTestResponse(BaseModel):
    """Response from model test"""
    success: bool
    response: Optional[str]
    error: Optional[str]
    execution_time_ms: int
    model: str
    provider: str


@router.get("/configurations", response_model=List[ModelConfigResponse])
async def list_model_configurations(
    provider: Optional[str] = None,
    is_active: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all model configurations"""
    
    query = db.query(ModelConfiguration)
    
    if provider:
        query = query.filter(ModelConfiguration.provider == provider)
    
    query = query.filter(ModelConfiguration.is_active == is_active)
    
    configs = query.all()
    
    return [
        ModelConfigResponse(
            id=config.id,
            name=config.name,
            provider=config.provider,
            model_name=config.model_name,
            api_endpoint=config.api_endpoint,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            frequency_penalty=config.frequency_penalty,
            presence_penalty=config.presence_penalty,
            context_window=config.context_window,
            gpu_layers=config.gpu_layers,
            batch_size=config.batch_size,
            repeat_penalty=config.repeat_penalty,
            seed=config.seed,
            provider_params=config.provider_params or {},
            is_default=config.is_default,
            is_active=config.is_active,
            tags=config.tags or [],
            created_at=config.created_at,
            updated_at=config.updated_at,
            last_tested=config.last_tested,
            test_status=config.test_status
        )
        for config in configs
    ]


@router.post("/configurations", response_model=ModelConfigResponse)
async def create_model_configuration(
    request: ModelConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new model configuration"""
    
    # Check if name already exists
    existing = db.query(ModelConfiguration).filter_by(name=request.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model configuration with name '{request.name}' already exists"
        )
    
    # If this should be default, unset other defaults
    if request.is_default:
        db.query(ModelConfiguration).update({"is_default": False})
    
    # Create configuration
    config = ModelConfiguration(
        id=str(uuid4()),
        name=request.name,
        provider=request.provider,
        model_name=request.model_name,
        api_endpoint=request.api_endpoint,
        api_key=request.api_key,  # Should be encrypted in production
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        frequency_penalty=request.frequency_penalty,
        presence_penalty=request.presence_penalty,
        context_window=request.context_window,
        gpu_layers=request.gpu_layers,
        batch_size=request.batch_size,
        repeat_penalty=request.repeat_penalty,
        seed=request.seed,
        provider_params=request.provider_params,
        is_default=request.is_default,
        is_active=True,
        tags=request.tags,
        created_by=current_user.id
    )
    
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return ModelConfigResponse(
        id=config.id,
        name=config.name,
        provider=config.provider,
        model_name=config.model_name,
        api_endpoint=config.api_endpoint,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        frequency_penalty=config.frequency_penalty,
        presence_penalty=config.presence_penalty,
        context_window=config.context_window,
        gpu_layers=config.gpu_layers,
        batch_size=config.batch_size,
        repeat_penalty=config.repeat_penalty,
        seed=config.seed,
        provider_params=config.provider_params or {},
        is_default=config.is_default,
        is_active=config.is_active,
        tags=config.tags or [],
        created_at=config.created_at,
        updated_at=config.updated_at,
        last_tested=config.last_tested,
        test_status=config.test_status
    )


@router.put("/configurations/{config_id}", response_model=ModelConfigResponse)
async def update_model_configuration(
    config_id: str,
    request: ModelConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing model configuration"""
    
    config = db.query(ModelConfiguration).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model configuration not found"
        )
    
    # If this should be default, unset other defaults
    if request.is_default and not config.is_default:
        db.query(ModelConfiguration).update({"is_default": False})
    
    # Update configuration
    config.name = request.name
    config.provider = request.provider
    config.model_name = request.model_name
    config.api_endpoint = request.api_endpoint
    if request.api_key:  # Only update if provided
        config.api_key = request.api_key
    config.temperature = request.temperature
    config.max_tokens = request.max_tokens
    config.top_p = request.top_p
    config.frequency_penalty = request.frequency_penalty
    config.presence_penalty = request.presence_penalty
    config.context_window = request.context_window
    config.gpu_layers = request.gpu_layers
    config.batch_size = request.batch_size
    config.repeat_penalty = request.repeat_penalty
    config.seed = request.seed
    config.provider_params = request.provider_params
    config.is_default = request.is_default
    config.tags = request.tags
    config.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(config)
    
    return ModelConfigResponse(
        id=config.id,
        name=config.name,
        provider=config.provider,
        model_name=config.model_name,
        api_endpoint=config.api_endpoint,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        frequency_penalty=config.frequency_penalty,
        presence_penalty=config.presence_penalty,
        context_window=config.context_window,
        gpu_layers=config.gpu_layers,
        batch_size=config.batch_size,
        repeat_penalty=config.repeat_penalty,
        seed=config.seed,
        provider_params=config.provider_params or {},
        is_default=config.is_default,
        is_active=config.is_active,
        tags=config.tags or [],
        created_at=config.created_at,
        updated_at=config.updated_at,
        last_tested=config.last_tested,
        test_status=config.test_status
    )


@router.delete("/configurations/{config_id}")
async def delete_model_configuration(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a model configuration"""
    
    config = db.query(ModelConfiguration).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model configuration not found"
        )
    
    # Check if any agents are using this configuration
    agents_using = db.query(AgentConfiguration).filter_by(model_config_id=config_id).count()
    if agents_using > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete: {agents_using} agents are using this configuration"
        )
    
    db.delete(config)
    db.commit()
    
    return {"message": "Model configuration deleted successfully"}


@router.post("/configurations/{config_id}/test", response_model=ModelTestResponse)
async def test_model_configuration(
    config_id: str,
    request: ModelTestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test a model configuration"""
    
    config = db.query(ModelConfiguration).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model configuration not found"
        )
    
    start_time = datetime.utcnow()
    
    try:
        # Create provider
        provider = ModelProviderFactory.create_provider(
            provider_type=config.provider,
            host=config.api_endpoint,
            model_name=config.model_name,
            api_key=config.api_key
        )
        
        # Build parameters
        params = ModelParameters(
            temperature=request.temperature or (config.temperature / 10.0),
            max_tokens=request.max_tokens or 50,
            top_p=config.top_p / 10.0
        )
        
        # Test generation
        response = await provider.generate(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            parameters=params
        )
        
        # Update test status
        config.last_tested = datetime.utcnow()
        config.test_status = "success"
        db.commit()
        
        execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return ModelTestResponse(
            success=True,
            response=response.content,
            error=None,
            execution_time_ms=execution_time,
            model=response.model,
            provider=response.provider
        )
        
    except Exception as e:
        # Update test status
        config.last_tested = datetime.utcnow()
        config.test_status = f"failed: {str(e)}"
        db.commit()
        
        execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return ModelTestResponse(
            success=False,
            response=None,
            error=str(e),
            execution_time_ms=execution_time,
            model=config.model_name,
            provider=config.provider
        )


@router.get("/providers")
async def list_available_providers(
    current_user: User = Depends(get_current_user)
):
    """List available model providers and their capabilities"""
    
    return {
        "providers": [
            {
                "name": "ollama",
                "display_name": "Ollama (Local)",
                "description": "Local models via Ollama",
                "requires_api_key": False,
                "default_endpoint": "http://localhost:11434",
                "supports_streaming": True,
                "recommended_models": [
                    "granite3.3:8b",
                    "phi4-mini:3.8b",
                    "gemma3n:e4b",
                    "llama3.2:3b",
                    "mistral:7b"
                ]
            },
            {
                "name": "openai",
                "display_name": "OpenAI",
                "description": "OpenAI GPT models",
                "requires_api_key": True,
                "default_endpoint": "https://api.openai.com/v1",
                "supports_streaming": True,
                "recommended_models": [
                    "gpt-4-turbo-preview",
                    "gpt-4",
                    "gpt-3.5-turbo",
                    "gpt-3.5-turbo-16k"
                ]
            },
            {
                "name": "anthropic",
                "display_name": "Anthropic",
                "description": "Claude models",
                "requires_api_key": True,
                "default_endpoint": "https://api.anthropic.com/v1",
                "supports_streaming": True,
                "recommended_models": [
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "claude-3-haiku-20240307"
                ]
            },
            {
                "name": "custom",
                "display_name": "Custom API",
                "description": "OpenAI-compatible custom endpoint",
                "requires_api_key": True,
                "default_endpoint": "",
                "supports_streaming": True,
                "recommended_models": []
            }
        ]
    }


@router.get("/templates")
async def list_model_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List predefined model configuration templates"""
    
    templates = db.query(ModelTemplate).filter_by(is_active=True).all()
    
    if not templates:
        # Return default templates if none in database
        return {
            "templates": [
                {
                    "name": "Fast Live Transcription",
                    "description": "Optimized for speed during live sessions",
                    "provider": "ollama",
                    "model_name": "phi4-mini:3.8b",
                    "temperature": 5,
                    "max_tokens": 1024,
                    "context_window": 4096
                },
                {
                    "name": "Balanced Analysis",
                    "description": "Good balance of speed and quality",
                    "provider": "ollama",
                    "model_name": "granite3.3:8b",
                    "temperature": 7,
                    "max_tokens": 2048,
                    "context_window": 8192
                },
                {
                    "name": "Deep Analysis",
                    "description": "Maximum quality for final summaries",
                    "provider": "ollama",
                    "model_name": "gemma3n:e4b",
                    "temperature": 7,
                    "max_tokens": 4096,
                    "context_window": 32768
                },
                {
                    "name": "OpenAI GPT-4",
                    "description": "High quality with OpenAI",
                    "provider": "openai",
                    "model_name": "gpt-4",
                    "temperature": 7,
                    "max_tokens": 4096,
                    "context_window": 8192
                }
            ]
        }
    
    return {
        "templates": [
            {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "category": template.category,
                "provider": template.provider,
                "model_name": template.model_name,
                "config": template.default_config
            }
            for template in templates
        ]
    }