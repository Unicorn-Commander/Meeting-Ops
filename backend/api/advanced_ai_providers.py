"""
Advanced AI Providers API Endpoints
Handles AI provider configuration and management for progressive agents
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
import logging
from datetime import datetime
import uuid
import json
from cryptography.fernet import Fernet
import os
import base64

from database.database import get_db
from models.progressive_agents import (
    AIProvider, MeetingAgent,
    AIProviderResponse, AIProviderCreate, AIProviderUpdate,
    ActiveProviderRequest
)

router = APIRouter(prefix="/api/advanced", tags=["advanced-ai-providers"])
logger = logging.getLogger(__name__)

# Simple encryption for API keys (in production, use proper key management)
def get_encryption_key():
    """Get or create encryption key for API keys"""
    key_file = "/home/ucadmin/Meeting-Ops/backend/.encryption_key"
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        os.chmod(key_file, 0o600)  # Restrict permissions
        return key

def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key for storage"""
    if not api_key:
        return ""
    
    key = get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(api_key.encode())
    return base64.b64encode(encrypted).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key from storage"""
    if not encrypted_key:
        return ""
    
    try:
        key = get_encryption_key()
        f = Fernet(key)
        encrypted_bytes = base64.b64decode(encrypted_key.encode())
        decrypted = f.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {e}")
        return ""

# ============= AI PROVIDERS ENDPOINTS =============

@router.get("/ai-providers", response_model=List[AIProviderResponse])
async def get_all_providers(db: Session = Depends(get_db)):
    """Get all AI providers"""
    try:
        providers = db.query(AIProvider).order_by(AIProvider.created_at).all()
        
        return [
            AIProviderResponse(
                id=str(provider.id),
                name=provider.name,
                type=provider.type,
                api_url=provider.api_url,
                models=provider.models or [],
                capabilities=provider.capabilities or {},
                performance_config=provider.performance_config or {},
                is_active=provider.is_active,
                created_at=provider.created_at.isoformat(),
                updated_at=provider.updated_at.isoformat()
            )
            for provider in providers
        ]
    except Exception as e:
        logger.error(f"Error fetching AI providers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch AI providers: {str(e)}")

@router.post("/ai-providers", response_model=AIProviderResponse)
async def create_provider(provider_data: AIProviderCreate, db: Session = Depends(get_db)):
    """Create a new AI provider"""
    try:
        # Encrypt API key if provided
        encrypted_key = ""
        if provider_data.api_key:
            encrypted_key = encrypt_api_key(provider_data.api_key)
        
        # Create new provider
        provider = AIProvider(
            name=provider_data.name,
            type=provider_data.type,
            api_url=provider_data.api_url,
            api_key_encrypted=encrypted_key,
            models=provider_data.models,
            capabilities=provider_data.capabilities,
            performance_config=provider_data.performance_config,
            is_active=False  # New providers start inactive
        )
        
        db.add(provider)
        db.commit()
        db.refresh(provider)
        
        logger.info(f"Created new AI provider: {provider.name} (ID: {provider.id})")
        
        return AIProviderResponse(
            id=str(provider.id),
            name=provider.name,
            type=provider.type,
            api_url=provider.api_url,
            models=provider.models or [],
            capabilities=provider.capabilities or {},
            performance_config=provider.performance_config or {},
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error creating AI provider: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create AI provider: {str(e)}")

@router.get("/ai-providers/{provider_id}", response_model=AIProviderResponse)
async def get_provider(provider_id: str, db: Session = Depends(get_db)):
    """Get a specific AI provider"""
    try:
        provider = db.query(AIProvider).filter(AIProvider.id == uuid.UUID(provider_id)).first()
        
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found")
        
        return AIProviderResponse(
            id=str(provider.id),
            name=provider.name,
            type=provider.type,
            api_url=provider.api_url,
            models=provider.models or [],
            capabilities=provider.capabilities or {},
            performance_config=provider.performance_config or {},
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching AI provider {provider_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch AI provider: {str(e)}")

@router.put("/ai-providers/{provider_id}", response_model=AIProviderResponse)
async def update_provider(provider_id: str, provider_data: AIProviderUpdate, db: Session = Depends(get_db)):
    """Update an AI provider"""
    try:
        provider = db.query(AIProvider).filter(AIProvider.id == uuid.UUID(provider_id)).first()
        
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found")
        
        # Update fields if provided
        if provider_data.name is not None:
            provider.name = provider_data.name
        if provider_data.type is not None:
            provider.type = provider_data.type
        if provider_data.api_url is not None:
            provider.api_url = provider_data.api_url
        if provider_data.api_key is not None:
            provider.api_key_encrypted = encrypt_api_key(provider_data.api_key)
        if provider_data.models is not None:
            provider.models = provider_data.models
        if provider_data.capabilities is not None:
            provider.capabilities = provider_data.capabilities
        if provider_data.performance_config is not None:
            provider.performance_config = provider_data.performance_config
        
        provider.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(provider)
        
        logger.info(f"Updated AI provider: {provider.name} (ID: {provider.id})")
        
        return AIProviderResponse(
            id=str(provider.id),
            name=provider.name,
            type=provider.type,
            api_url=provider.api_url,
            models=provider.models or [],
            capabilities=provider.capabilities or {},
            performance_config=provider.performance_config or {},
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating AI provider {provider_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update AI provider: {str(e)}")

@router.delete("/ai-providers/{provider_id}")
async def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    """Delete an AI provider"""
    try:
        provider = db.query(AIProvider).filter(AIProvider.id == uuid.UUID(provider_id)).first()
        
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found")
        
        # Check if provider is currently active
        if provider.is_active:
            raise HTTPException(status_code=400, detail="Cannot delete active AI provider. Deactivate it first.")
        
        provider_name = provider.name
        db.delete(provider)
        db.commit()
        
        logger.info(f"Deleted AI provider: {provider_name} (ID: {provider_id})")
        
        return {"message": f"AI provider '{provider_name}' deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting AI provider {provider_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete AI provider: {str(e)}")

@router.get("/ai-providers/active", response_model=Optional[AIProviderResponse])
async def get_active_provider(db: Session = Depends(get_db)):
    """Get the currently active AI provider"""
    try:
        provider = db.query(AIProvider).filter(AIProvider.is_active == True).first()
        
        if not provider:
            return None
        
        return AIProviderResponse(
            id=str(provider.id),
            name=provider.name,
            type=provider.type,
            api_url=provider.api_url,
            models=provider.models or [],
            capabilities=provider.capabilities or {},
            performance_config=provider.performance_config or {},
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error fetching active AI provider: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch active AI provider: {str(e)}")

@router.post("/ai-providers/active")
async def set_active_provider(request: ActiveProviderRequest, db: Session = Depends(get_db)):
    """Set the active AI provider"""
    try:
        # First, deactivate all providers
        db.query(AIProvider).update({"is_active": False})
        
        # Then activate the requested provider
        provider = db.query(AIProvider).filter(AIProvider.id == uuid.UUID(request.provider_id)).first()
        
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found")
        
        provider.is_active = True
        provider.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Set active AI provider: {provider.name} (ID: {provider.id})")
        
        return {
            "message": f"AI provider '{provider.name}' is now active",
            "provider_id": str(provider.id),
            "provider_name": provider.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting active AI provider: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to set active AI provider: {str(e)}")

@router.get("/ai-providers/{provider_id}/test-connection")
async def test_provider_connection(provider_id: str, db: Session = Depends(get_db)):
    """Test connection to an AI provider"""
    try:
        provider = db.query(AIProvider).filter(AIProvider.id == uuid.UUID(provider_id)).first()
        
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found")
        
        # Test connection based on provider type
        if provider.type == "ollama":
            import httpx
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{provider.api_url}/api/tags", timeout=5.0)
                    
                if response.status_code == 200:
                    models_data = response.json()
                    available_models = [model["name"] for model in models_data.get("models", [])]
                    
                    return {
                        "status": "connected",
                        "provider_type": provider.type,
                        "api_url": provider.api_url,
                        "available_models": available_models,
                        "message": f"Successfully connected to {provider.name}"
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Failed to connect: HTTP {response.status_code}"
                    }
                    
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Connection failed: {str(e)}"
                }
        
        elif provider.type in ["openai", "anthropic"]:
            # For external providers, just validate the API key format
            api_key = decrypt_api_key(provider.api_key_encrypted or "")
            
            if not api_key:
                return {
                    "status": "error",
                    "message": "No API key configured"
                }
            
            return {
                "status": "configured",
                "provider_type": provider.type,
                "message": f"API key configured for {provider.name}. Connection test requires actual API call."
            }
        
        else:
            return {
                "status": "unknown",
                "message": f"Connection test not implemented for provider type: {provider.type}"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing AI provider connection {provider_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to test connection: {str(e)}")

@router.get("/ai-providers/by-type/{provider_type}", response_model=List[AIProviderResponse])
async def get_providers_by_type(provider_type: str, db: Session = Depends(get_db)):
    """Get all AI providers of a specific type"""
    try:
        providers = db.query(AIProvider).filter(AIProvider.type == provider_type).order_by(AIProvider.created_at).all()
        
        return [
            AIProviderResponse(
                id=str(provider.id),
                name=provider.name,
                type=provider.type,
                api_url=provider.api_url,
                models=provider.models or [],
                capabilities=provider.capabilities or {},
                performance_config=provider.performance_config or {},
                is_active=provider.is_active,
                created_at=provider.created_at.isoformat(),
                updated_at=provider.updated_at.isoformat()
            )
            for provider in providers
        ]
        
    except Exception as e:
        logger.error(f"Error fetching AI providers by type {provider_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch AI providers by type: {str(e)}")

@router.get("/ai-providers/{provider_id}/models")
async def get_provider_models(provider_id: str, db: Session = Depends(get_db)):
    """Get available models for an AI provider"""
    try:
        provider = db.query(AIProvider).filter(AIProvider.id == uuid.UUID(provider_id)).first()
        
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found")
        
        # Get models based on provider type
        if provider.type == "ollama" and provider.api_url:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{provider.api_url}/api/tags", timeout=5.0)
                    
                if response.status_code == 200:
                    models_data = response.json()
                    live_models = [
                        {
                            "name": model["name"],
                            "size": model.get("size", 0),
                            "modified_at": model.get("modified_at", ""),
                            "status": "available"
                        }
                        for model in models_data.get("models", [])
                    ]
                    
                    return {
                        "provider_id": str(provider.id),
                        "provider_name": provider.name,
                        "configured_models": provider.models or [],
                        "live_models": live_models,
                        "status": "connected"
                    }
                
            except Exception as e:
                logger.warning(f"Failed to fetch live models from Ollama: {e}")
        
        # Return configured models as fallback
        return {
            "provider_id": str(provider.id),
            "provider_name": provider.name,
            "configured_models": provider.models or [],
            "live_models": [],
            "status": "configured_only"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching models for provider {provider_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch provider models: {str(e)}")