"""
Agent System API
Handles configuration and execution of the 2-agent architecture
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import asyncio
import aiohttp
import json
import time
from pydantic import BaseModel, Field

from database import get_db
from models.agent_config import AgentConfiguration, AgentProvider, AgentExecution
from database.models import RecordingSession
from auth.dependencies import get_current_user
from auth.models import User

router = APIRouter(prefix="/api/agents", tags=["Agent System"])


# Pydantic models for API
class AgentConfigCreate(BaseModel):
    """Create/Update agent configuration"""
    name: str
    description: Optional[str] = None
    agent_type: str = Field(..., pattern="^(live_enhancement|final_analysis)$")
    
    # Core configuration
    system_prompt: str
    tools: List[str] = []
    custom_instructions: Optional[str] = None
    
    # Model settings
    provider: str = "ollama"
    model_name: str = "granite3.3:8b"
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    
    # Performance settings
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    
    # Update strategy
    update_interval_min: int = 30
    update_interval_max: int = 90
    min_words_trigger: int = 150
    silence_trigger_seconds: int = 10
    priority_keywords: List[str] = ["action item", "decision", "deadline", "important"]
    
    # GPU optimization
    gpu_layers: int = 99
    context_window: int = 8192


class ProviderConfig(BaseModel):
    """Configure API provider"""
    name: str
    provider_type: str = Field(..., pattern="^(ollama|openai_compatible|custom)$")
    api_url: str
    api_key: Optional[str] = None
    timeout_seconds: int = 120


class LiveUpdateRequest(BaseModel):
    """Request for live agent update"""
    session_id: str
    transcript_chunk: str
    force_update: bool = False
    
    
# Default agent configurations
DEFAULT_LIVE_AGENT = {
    "name": "Hermes - Live Enhancement (Dual-Model Pipeline)",
    "description": "Real-time transcript enhancement with adaptive dual-model pipeline",
    "agent_type": "live_enhancement",
    "system_prompt": """You are Hermes, a real-time meeting intelligence assistant.
Your role is to:
1. Take raw transcription and create a polished, well-formatted transcript
2. Generate concise meeting notes highlighting key points
3. Identify and extract action items as they're discussed
4. Recognize important decisions and flag them
5. Create a running summary that evolves as the meeting progresses

Format your responses as JSON with these fields:
- formatted_transcript: Clean, properly punctuated transcript with speaker labels
- summary: Concise running summary (2-3 sentences)
- key_points: List of important points discussed
- action_items: List of {task, owner, deadline} objects
- decisions: List of decisions made
- topics: Main topics being discussed

Be concise but thorough. Update existing content rather than repeating.""",
    "tools": ["format_transcript", "extract_entities", "identify_speakers"],
    "model_name": "granite3.3:8b",
    "provider": "ollama",
    "temperature": 0.7,
    "gpu_layers": 99
}

DEFAULT_FINAL_AGENT = {
    "name": "Athena - Final Analysis",
    "description": "Comprehensive post-meeting analysis and reporting",
    "agent_type": "final_analysis",
    "system_prompt": """You are Athena, a comprehensive meeting analysis assistant.
Your role is to:
1. Create detailed meeting reports with full context
2. Generate action item matrices with clear ownership
3. Develop project plans from meeting discussions
4. Analyze meeting effectiveness and participation
5. Create executive summaries for different audiences

Provide thorough analysis with professional formatting.""",
    "tools": ["generate_report", "create_matrix", "analyze_participation"],
    "model_name": "granite3.3:8b",
    "provider": "ollama",
    "temperature": 0.5,
    "gpu_layers": 99
}


class AgentService:
    """Service for managing agent executions"""
    
    def __init__(self):
        self.active_sessions = {}  # Track active live sessions
        self.update_queues = {}    # Pending updates per session
        
    async def execute_agent(
        self,
        agent_config: AgentConfiguration,
        input_text: str,
        session_id: str,
        execution_type: str = "manual"
    ) -> Dict[str, Any]:
        """Execute an agent and return results"""
        
        start_time = time.time()
        
        try:
            # Prepare the prompt
            messages = [
                {"role": "system", "content": agent_config.system_prompt}
            ]
            
            if agent_config.custom_instructions:
                messages.append({
                    "role": "system", 
                    "content": f"Additional instructions: {agent_config.custom_instructions}"
                })
            
            messages.append({"role": "user", "content": input_text})
            
            # Call the model based on provider
            if agent_config.provider == "ollama":
                response = await self._call_ollama(
                    model=agent_config.model_name,
                    messages=messages,
                    options={
                        "temperature": agent_config.temperature / 10,
                        "top_p": agent_config.top_p / 10,
                        "num_predict": agent_config.max_tokens,
                        "num_gpu": agent_config.gpu_layers,
                        "num_ctx": agent_config.context_window
                    }
                )
            elif agent_config.provider in ["openai", "openai_compatible"]:
                response = await self._call_openai_compatible(
                    endpoint=agent_config.api_endpoint,
                    api_key=agent_config.api_key,
                    model=agent_config.model_name,
                    messages=messages,
                    temperature=agent_config.temperature / 10,
                    max_tokens=agent_config.max_tokens
                )
            else:
                raise ValueError(f"Unknown provider: {agent_config.provider}")
            
            # Parse response based on agent type
            if agent_config.agent_type == "live_enhancement":
                output = self._parse_live_response(response)
            else:
                output = {"content": response}
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "output": output,
                "execution_time_ms": execution_time,
                "model": agent_config.model_name
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": int((time.time() - start_time) * 1000)
            }
    
    async def _call_ollama(self, model: str, messages: List[Dict], options: Dict) -> str:
        """Call Ollama API"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "options": options,
                    "stream": False
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("message", {}).get("content", "")
                else:
                    raise Exception(f"Ollama API error: {response.status}")
    
    async def _call_openai_compatible(
        self, 
        endpoint: str, 
        api_key: str, 
        model: str, 
        messages: List[Dict],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Call OpenAI-compatible API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else ""
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{endpoint}/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    raise Exception(f"API error: {response.status}")
    
    def _parse_live_response(self, response: str) -> Dict[str, Any]:
        """Parse response from live enhancement agent"""
        try:
            # Try to parse as JSON first
            return json.loads(response)
        except:
            # Fallback to structured parsing
            return {
                "formatted_transcript": response,
                "summary": "",
                "key_points": [],
                "action_items": [],
                "decisions": [],
                "topics": []
            }
    
    def should_update(
        self,
        session_id: str,
        word_count: int,
        last_update_time: float,
        silence_duration: float,
        text: str,
        agent_config: AgentConfiguration
    ) -> tuple[bool, str]:
        """Determine if live update should trigger"""
        
        current_time = time.time()
        time_since_update = current_time - last_update_time
        
        # Check various trigger conditions
        if word_count >= agent_config.min_words_trigger:
            return True, f"Word count threshold reached: {word_count}"
        
        if silence_duration >= agent_config.silence_trigger_seconds and word_count > 50:
            return True, f"Natural pause detected after {silence_duration}s"
        
        # Check for priority keywords
        text_lower = text.lower()
        for keyword in agent_config.priority_keywords:
            if keyword.lower() in text_lower:
                return True, f"Priority keyword detected: {keyword}"
        
        if time_since_update >= agent_config.update_interval_max and word_count > 30:
            return True, f"Maximum interval reached: {time_since_update}s"
        
        return False, ""


# Initialize service
agent_service = AgentService()


# API Endpoints
@router.get("/configurations")
async def list_agent_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict]:
    """List all agent configurations"""
    configs = db.query(AgentConfiguration).filter_by(is_active=True).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "agent_type": c.agent_type,
            "model": c.model_name,
            "provider": c.provider,
            "is_default": c.is_default
        }
        for c in configs
    ]


@router.post("/configurations")
async def create_agent_config(
    config: AgentConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """Create new agent configuration"""
    
    agent = AgentConfiguration(
        name=config.name,
        description=config.description,
        agent_type=config.agent_type,
        system_prompt=config.system_prompt,
        tools=config.tools,
        custom_instructions=config.custom_instructions,
        provider=config.provider,
        model_name=config.model_name,
        api_endpoint=config.api_endpoint,
        api_key=config.api_key,
        temperature=int(config.temperature * 10),
        max_tokens=config.max_tokens,
        top_p=int(config.top_p * 10),
        update_interval_min=config.update_interval_min,
        update_interval_max=config.update_interval_max,
        min_words_trigger=config.min_words_trigger,
        silence_trigger_seconds=config.silence_trigger_seconds,
        priority_keywords=config.priority_keywords,
        gpu_layers=config.gpu_layers,
        context_window=config.context_window,
        created_by=current_user.id
    )
    
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    return {"id": agent.id, "message": "Agent configuration created successfully"}


@router.post("/providers")
async def add_provider(
    provider: ProviderConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """Add API provider configuration"""
    
    # Test connection
    try:
        async with aiohttp.ClientSession() as session:
            if provider.provider_type == "ollama":
                async with session.get(
                    f"{provider.api_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [m["name"] for m in data.get("models", [])]
                    else:
                        raise HTTPException(400, "Failed to connect to Ollama")
            else:
                # For OpenAI compatible, try to get models
                headers = {"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {}
                async with session.get(
                    f"{provider.api_url}/v1/models",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [m["id"] for m in data.get("data", [])]
                    else:
                        models = []
    except Exception as e:
        raise HTTPException(400, f"Failed to verify provider: {str(e)}")
    
    # Save provider
    provider_obj = AgentProvider(
        name=provider.name,
        provider_type=provider.provider_type,
        api_url=provider.api_url,
        api_key=provider.api_key,
        available_models=models,
        is_verified=True,
        last_health_check=datetime.utcnow()
    )
    
    db.add(provider_obj)
    db.commit()
    
    return {
        "id": provider_obj.id,
        "message": "Provider added successfully",
        "models": models
    }


@router.post("/execute/live")
async def execute_live_update(
    request: LiveUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """Execute live enhancement agent"""
    
    # Get default live agent
    agent = db.query(AgentConfiguration).filter_by(
        agent_type="live_enhancement",
        is_default=True
    ).first()
    
    if not agent:
        # Create default if not exists
        agent = AgentConfiguration(**DEFAULT_LIVE_AGENT)
        agent.created_by = current_user.id
        agent.is_default = True
        db.add(agent)
        db.commit()
    
    # Execute agent
    result = await agent_service.execute_agent(
        agent_config=agent,
        input_text=request.transcript_chunk,
        session_id=request.session_id,
        execution_type="triggered" if request.force_update else "scheduled"
    )
    
    # Log execution
    execution = AgentExecution(
        agent_id=agent.id,
        session_id=request.session_id,
        execution_type="triggered" if request.force_update else "scheduled",
        trigger_reason="Manual" if request.force_update else "Scheduled update",
        input_text=request.transcript_chunk,
        input_word_count=len(request.transcript_chunk.split()),
        output_content=result.get("output"),
        execution_time_ms=result.get("execution_time_ms"),
        model_used=agent.model_name,
        status="success" if result["success"] else "failed",
        error_message=result.get("error"),
        completed_at=datetime.utcnow()
    )
    
    db.add(execution)
    db.commit()
    
    return result


@router.post("/initialize-defaults")
async def initialize_default_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """Initialize default agent configurations"""
    
    # Check if defaults exist
    existing = db.query(AgentConfiguration).filter_by(is_default=True).count()
    if existing > 0:
        return {"message": "Default agents already configured"}
    
    # Create defaults
    live_agent = AgentConfiguration(**DEFAULT_LIVE_AGENT)
    live_agent.created_by = current_user.id
    live_agent.is_default = True
    
    final_agent = AgentConfiguration(**DEFAULT_FINAL_AGENT)
    final_agent.created_by = current_user.id
    final_agent.is_default = True
    
    db.add(live_agent)
    db.add(final_agent)
    db.commit()
    
    return {"message": "Default agents initialized successfully"}