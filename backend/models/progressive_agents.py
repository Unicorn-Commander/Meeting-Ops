"""
Database models for Progressive Meeting Agent System
"""
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from typing import Dict, Optional, List
from pydantic import BaseModel, Field

Base = declarative_base()

class MeetingAgent(Base):
    """Meeting Agent database model"""
    __tablename__ = 'meeting_agents'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    role = Column(String(50), nullable=False)  # 'action_tracker', 'meeting_analyst', etc.
    personality = Column(Text)
    capabilities = Column(JSONB, default={})
    trigger_type = Column(String(20), nullable=False, default='progressive')
    progressive_config = Column(JSONB, default={
        'initialWordCount': 50,
        'intervalMultiplier': 1.5,
        'maxInterval': 1000,
        'modelSize': 'small'
    })
    sections = Column(JSONB, default={})  # Agent-specific output sections
    prompts = Column(JSONB, default={})  # System prompts
    is_active = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class AIProvider(Base):
    """AI Provider database model"""
    __tablename__ = 'ai_providers'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # 'ollama', 'openai', 'anthropic', 'local'
    api_url = Column(String(500))
    api_key_encrypted = Column(Text)  # Encrypted API keys
    models = Column(JSONB, default=[])  # Available models
    capabilities = Column(JSONB, default={})
    performance_config = Column(JSONB, default={})  # Model mappings, performance settings
    is_active = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProgressiveSummary(Base):
    """Progressive Summary history model"""
    __tablename__ = 'progressive_summaries'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey('meeting_agents.id'))
    provider_id = Column(UUID(as_uuid=True), ForeignKey('ai_providers.id'))
    word_count = Column(Integer, nullable=False)
    interval_used = Column(Integer, nullable=False)
    next_interval = Column(Integer, nullable=False)
    model_size = Column(String(20), nullable=False)
    sections = Column(JSONB, nullable=False)
    processing_time_ms = Column(Integer)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    
    # Relationships
    agent = relationship("MeetingAgent")
    provider = relationship("AIProvider")

class ProgressiveSessionState(Base):
    """Progressive Session State model"""
    __tablename__ = 'progressive_session_state'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey('meeting_agents.id'))
    current_interval = Column(Integer, nullable=False)
    last_summary_at = Column(Integer, default=0)
    total_summaries = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint
    __table_args__ = (UniqueConstraint('session_id', 'agent_id', name='unique_session_agent'),)
    
    # Relationship
    agent = relationship("MeetingAgent")

# Pydantic models for API

class MeetingAgentResponse(BaseModel):
    """Meeting Agent API response model"""
    id: str
    name: str
    description: Optional[str] = None
    role: str
    personality: Optional[str] = None
    capabilities: Dict = Field(default_factory=dict)
    trigger_type: str = "progressive"
    progressive_config: Dict = Field(default_factory=dict)
    sections: Dict = Field(default_factory=dict)
    prompts: Dict = Field(default_factory=dict)
    is_active: bool = False
    created_at: str
    updated_at: str

class MeetingAgentCreate(BaseModel):
    """Meeting Agent creation model"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    role: str = Field(..., min_length=1, max_length=50)
    personality: Optional[str] = None
    capabilities: Dict = Field(default_factory=dict)
    trigger_type: str = "progressive"
    progressive_config: Dict = Field(default_factory=lambda: {
        'initialWordCount': 50,
        'intervalMultiplier': 1.5,
        'maxInterval': 1000,
        'modelSize': 'small'
    })
    sections: Dict = Field(default_factory=dict)
    prompts: Dict = Field(default_factory=dict)

class MeetingAgentUpdate(BaseModel):
    """Meeting Agent update model"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    personality: Optional[str] = None
    capabilities: Optional[Dict] = None
    trigger_type: Optional[str] = None
    progressive_config: Optional[Dict] = None
    sections: Optional[Dict] = None
    prompts: Optional[Dict] = None

class AIProviderResponse(BaseModel):
    """AI Provider API response model"""
    id: str
    name: str
    type: str
    api_url: Optional[str] = None
    models: List[Dict] = Field(default_factory=list)
    capabilities: Dict = Field(default_factory=dict)
    performance_config: Dict = Field(default_factory=dict)
    is_active: bool = False
    created_at: str
    updated_at: str

class AIProviderCreate(BaseModel):
    """AI Provider creation model"""
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=50)
    api_url: Optional[str] = None
    api_key: Optional[str] = None  # Will be encrypted before storage
    models: List[Dict] = Field(default_factory=list)
    capabilities: Dict = Field(default_factory=dict)
    performance_config: Dict = Field(default_factory=dict)

class AIProviderUpdate(BaseModel):
    """AI Provider update model"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    models: Optional[List[Dict]] = None
    capabilities: Optional[Dict] = None
    performance_config: Optional[Dict] = None

class ProgressiveSummaryResponse(BaseModel):
    """Progressive Summary response model"""
    id: str
    session_id: str
    agent_id: str
    provider_id: str
    word_count: int
    interval_used: int
    next_interval: int
    model_size: str
    sections: Dict
    processing_time_ms: Optional[int] = None
    created_at: str
    agent_name: Optional[str] = None
    provider_name: Optional[str] = None

class ActiveAgentRequest(BaseModel):
    """Request to set active agent"""
    agent_id: str

class ActiveProviderRequest(BaseModel):
    """Request to set active provider"""
    provider_id: str