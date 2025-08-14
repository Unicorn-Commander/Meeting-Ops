"""
Advanced Agents API Endpoints
Handles progressive meeting agents configuration and management
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Dict, Optional
import logging
from datetime import datetime
import uuid

from database.database import get_db
from models.progressive_agents import (
    MeetingAgent, AIProvider, ProgressiveSummary, ProgressiveSessionState,
    MeetingAgentResponse, MeetingAgentCreate, MeetingAgentUpdate,
    ActiveAgentRequest
)
from services.progressive_interval_manager import ProgressiveConfig

router = APIRouter(prefix="/api/advanced", tags=["advanced-agents"])
logger = logging.getLogger(__name__)

# ============= MEETING AGENTS ENDPOINTS =============

@router.get("/agents", response_model=List[MeetingAgentResponse])
async def get_all_agents(db: Session = Depends(get_db)):
    """Get all meeting agents"""
    try:
        agents = db.query(MeetingAgent).order_by(MeetingAgent.created_at).all()
        
        return [
            MeetingAgentResponse(
                id=str(agent.id),
                name=agent.name,
                description=agent.description,
                role=agent.role,
                personality=agent.personality,
                capabilities=agent.capabilities or {},
                trigger_type=agent.trigger_type,
                progressive_config=agent.progressive_config or {},
                sections=agent.sections or {},
                prompts=agent.prompts or {},
                is_active=agent.is_active,
                created_at=agent.created_at.isoformat(),
                updated_at=agent.updated_at.isoformat()
            )
            for agent in agents
        ]
    except Exception as e:
        logger.error(f"Error fetching agents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agents: {str(e)}")

@router.post("/agents", response_model=MeetingAgentResponse)
async def create_agent(agent_data: MeetingAgentCreate, db: Session = Depends(get_db)):
    """Create a new meeting agent"""
    try:
        # Validate progressive config
        try:
            ProgressiveConfig.from_dict(agent_data.progressive_config)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid progressive config: {str(e)}")
        
        # Create new agent
        agent = MeetingAgent(
            name=agent_data.name,
            description=agent_data.description,
            role=agent_data.role,
            personality=agent_data.personality,
            capabilities=agent_data.capabilities,
            trigger_type=agent_data.trigger_type,
            progressive_config=agent_data.progressive_config,
            sections=agent_data.sections,
            prompts=agent_data.prompts,
            is_active=False  # New agents start inactive
        )
        
        db.add(agent)
        db.commit()
        db.refresh(agent)
        
        logger.info(f"Created new meeting agent: {agent.name} (ID: {agent.id})")
        
        return MeetingAgentResponse(
            id=str(agent.id),
            name=agent.name,
            description=agent.description,
            role=agent.role,
            personality=agent.personality,
            capabilities=agent.capabilities or {},
            trigger_type=agent.trigger_type,
            progressive_config=agent.progressive_config or {},
            sections=agent.sections or {},
            prompts=agent.prompts or {},
            is_active=agent.is_active,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")

@router.get("/agents/{agent_id}", response_model=MeetingAgentResponse)
async def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """Get a specific meeting agent"""
    try:
        agent = db.query(MeetingAgent).filter(MeetingAgent.id == uuid.UUID(agent_id)).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        return MeetingAgentResponse(
            id=str(agent.id),
            name=agent.name,
            description=agent.description,
            role=agent.role,
            personality=agent.personality,
            capabilities=agent.capabilities or {},
            trigger_type=agent.trigger_type,
            progressive_config=agent.progressive_config or {},
            sections=agent.sections or {},
            prompts=agent.prompts or {},
            is_active=agent.is_active,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent: {str(e)}")

@router.put("/agents/{agent_id}", response_model=MeetingAgentResponse)
async def update_agent(agent_id: str, agent_data: MeetingAgentUpdate, db: Session = Depends(get_db)):
    """Update a meeting agent"""
    try:
        agent = db.query(MeetingAgent).filter(MeetingAgent.id == uuid.UUID(agent_id)).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Update fields if provided
        if agent_data.name is not None:
            agent.name = agent_data.name
        if agent_data.description is not None:
            agent.description = agent_data.description
        if agent_data.personality is not None:
            agent.personality = agent_data.personality
        if agent_data.capabilities is not None:
            agent.capabilities = agent_data.capabilities
        if agent_data.trigger_type is not None:
            agent.trigger_type = agent_data.trigger_type
        if agent_data.progressive_config is not None:
            # Validate progressive config
            try:
                ProgressiveConfig.from_dict(agent_data.progressive_config)
                agent.progressive_config = agent_data.progressive_config
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid progressive config: {str(e)}")
        if agent_data.sections is not None:
            agent.sections = agent_data.sections
        if agent_data.prompts is not None:
            agent.prompts = agent_data.prompts
        
        agent.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(agent)
        
        logger.info(f"Updated meeting agent: {agent.name} (ID: {agent.id})")
        
        return MeetingAgentResponse(
            id=str(agent.id),
            name=agent.name,
            description=agent.description,
            role=agent.role,
            personality=agent.personality,
            capabilities=agent.capabilities or {},
            trigger_type=agent.trigger_type,
            progressive_config=agent.progressive_config or {},
            sections=agent.sections or {},
            prompts=agent.prompts or {},
            is_active=agent.is_active,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")

@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    """Delete a meeting agent"""
    try:
        agent = db.query(MeetingAgent).filter(MeetingAgent.id == uuid.UUID(agent_id)).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Check if agent is currently active
        if agent.is_active:
            raise HTTPException(status_code=400, detail="Cannot delete active agent. Deactivate it first.")
        
        # Delete related records first
        db.query(ProgressiveSummary).filter(ProgressiveSummary.agent_id == agent.id).delete()
        db.query(ProgressiveSessionState).filter(ProgressiveSessionState.agent_id == agent.id).delete()
        
        agent_name = agent.name
        db.delete(agent)
        db.commit()
        
        logger.info(f"Deleted meeting agent: {agent_name} (ID: {agent_id})")
        
        return {"message": f"Agent '{agent_name}' deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {str(e)}")

@router.get("/agents/active", response_model=Optional[MeetingAgentResponse])
async def get_active_agent(db: Session = Depends(get_db)):
    """Get the currently active meeting agent"""
    try:
        agent = db.query(MeetingAgent).filter(MeetingAgent.is_active == True).first()
        
        if not agent:
            return None
        
        return MeetingAgentResponse(
            id=str(agent.id),
            name=agent.name,
            description=agent.description,
            role=agent.role,
            personality=agent.personality,
            capabilities=agent.capabilities or {},
            trigger_type=agent.trigger_type,
            progressive_config=agent.progressive_config or {},
            sections=agent.sections or {},
            prompts=agent.prompts or {},
            is_active=agent.is_active,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error fetching active agent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch active agent: {str(e)}")

@router.post("/agents/active")
async def set_active_agent(request: ActiveAgentRequest, db: Session = Depends(get_db)):
    """Set the active meeting agent"""
    try:
        # First, deactivate all agents
        db.query(MeetingAgent).update({"is_active": False})
        
        # Then activate the requested agent
        agent = db.query(MeetingAgent).filter(MeetingAgent.id == uuid.UUID(request.agent_id)).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent.is_active = True
        agent.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Set active meeting agent: {agent.name} (ID: {agent.id})")
        
        return {
            "message": f"Agent '{agent.name}' is now active",
            "agent_id": str(agent.id),
            "agent_name": agent.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting active agent: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to set active agent: {str(e)}")

@router.get("/agents/by-role/{role}", response_model=List[MeetingAgentResponse])
async def get_agents_by_role(role: str, db: Session = Depends(get_db)):
    """Get all agents with a specific role"""
    try:
        agents = db.query(MeetingAgent).filter(MeetingAgent.role == role).order_by(MeetingAgent.created_at).all()
        
        return [
            MeetingAgentResponse(
                id=str(agent.id),
                name=agent.name,
                description=agent.description,
                role=agent.role,
                personality=agent.personality,
                capabilities=agent.capabilities or {},
                trigger_type=agent.trigger_type,
                progressive_config=agent.progressive_config or {},
                sections=agent.sections or {},
                prompts=agent.prompts or {},
                is_active=agent.is_active,
                created_at=agent.created_at.isoformat(),
                updated_at=agent.updated_at.isoformat()
            )
            for agent in agents
        ]
        
    except Exception as e:
        logger.error(f"Error fetching agents by role {role}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agents by role: {str(e)}")

@router.get("/agents/{agent_id}/progressive-config")
async def get_agent_progressive_config(agent_id: str, db: Session = Depends(get_db)):
    """Get progressive configuration for an agent"""
    try:
        agent = db.query(MeetingAgent).filter(MeetingAgent.id == uuid.UUID(agent_id)).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        config = ProgressiveConfig.from_dict(agent.progressive_config or {})
        
        return {
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "progressive_config": config.to_dict(),
            "trigger_type": agent.trigger_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching progressive config for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch progressive config: {str(e)}")

# ============= AGENT STATISTICS AND ANALYTICS =============

@router.get("/agents/{agent_id}/stats")
async def get_agent_stats(agent_id: str, db: Session = Depends(get_db)):
    """Get statistics for an agent"""
    try:
        agent = db.query(MeetingAgent).filter(MeetingAgent.id == uuid.UUID(agent_id)).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Get summary statistics
        summaries = db.query(ProgressiveSummary).filter(ProgressiveSummary.agent_id == agent.id).all()
        
        total_summaries = len(summaries)
        avg_processing_time = sum(s.processing_time_ms for s in summaries if s.processing_time_ms) / max(1, len([s for s in summaries if s.processing_time_ms]))
        avg_word_count = sum(s.word_count for s in summaries) / max(1, total_summaries)
        
        # Get active sessions
        active_sessions = db.query(ProgressiveSessionState).filter(ProgressiveSessionState.agent_id == agent.id).count()
        
        return {
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "statistics": {
                "total_summaries": total_summaries,
                "average_processing_time_ms": round(avg_processing_time, 2),
                "average_word_count": round(avg_word_count, 2),
                "active_sessions": active_sessions,
                "last_used": summaries[-1].created_at.isoformat() if summaries else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agent stats {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent stats: {str(e)}")