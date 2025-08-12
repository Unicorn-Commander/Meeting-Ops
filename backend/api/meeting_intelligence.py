"""
Meeting Intelligence API - Live Notes and Final Reports with Gemma2-27b
Provides real-time meeting notes and comprehensive final reports
"""

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
import json
import asyncio
import logging
from datetime import datetime
import ollama
import requests
import sys
import os

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.llm_config import llm_config_manager, LLMProvider

from database import get_db
from auth.dependencies import get_current_user, get_current_user_optional
from auth.models import User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meeting-intelligence", tags=["meeting-intelligence"])

# Dynamic LLM client initialization
def get_ollama_client():
    """Get Ollama client with current active endpoint"""
    endpoint = llm_config_manager.config.get_active_endpoint()
    if not endpoint:
        raise ValueError("No active LLM endpoint configured")
    
    if endpoint.provider not in [LLMProvider.LOCAL_OLLAMA, LLMProvider.REMOTE_OLLAMA]:
        raise ValueError(f"Provider {endpoint.provider} not supported for Ollama")
    
    return ollama.Client(host=endpoint.url), endpoint.model, endpoint

class MeetingIntelligenceService:
    """Service for generating meeting notes and reports"""
    
    @staticmethod
    async def generate_live_notes(
        transcript: str,
        templates: List[str],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate live meeting notes based on selected templates"""
        
        # Build prompt based on selected templates
        template_prompts = {
            "executive-summary": "Provide a brief executive summary with key points and takeaways.",
            "bullet-points": "List the main discussion points as clear bullet points.",
            "key-decisions": "Identify and list any decisions made during the discussion.",
            "action-alerts": "Extract immediate action items that need attention."
        }
        
        selected_prompts = [template_prompts.get(t, "") for t in templates if t in template_prompts]
        
        prompt = f"""Analyze this meeting transcript and provide real-time notes.
        
TRANSCRIPT:
{transcript[-8000:]}  # Use last 8k chars for live notes (quick processing)

Generate the following:
{' '.join(selected_prompts)}

Format your response as JSON with these keys:
- executive_summary (if requested): Brief summary paragraph
- bullet_points (if requested): Array of key points
- key_decisions (if requested): Array of decisions made
- action_alerts (if requested): Array of immediate action items

Be concise and focus on the most recent information."""

        try:
            # Generate with configured LLM
            client, model_name, endpoint = get_ollama_client()
            response = client.generate(
                model=model_name,
                prompt=prompt,
                options={
                    "temperature": 0.7,
                    "num_predict": 1000,  # Limit tokens for speed
                    "top_k": 40,
                    "top_p": 0.9
                }
            )
            
            # Parse JSON response
            try:
                notes = json.loads(response['response'])
            except json.JSONDecodeError:
                # Fallback to text parsing if JSON fails
                notes = {"summary": response['response']}
            
            return {
                "type": "live",
                "session_id": session_id,
                "notes": notes,
                "timestamp": datetime.utcnow().isoformat(),
                "templates_used": templates
            }
            
        except Exception as e:
            logger.error(f"Error generating live notes: {e}")
            return {
                "type": "live",
                "session_id": session_id,
                "notes": {"error": str(e)},
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def generate_final_report(
        transcript: str,
        templates: List[str],
        live_notes: Optional[Dict] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive final report with full context"""
        
        # Template definitions for final reports
        template_prompts = {
            "full-report": """Create a comprehensive meeting report with:
                - Executive Summary
                - Meeting Purpose and Objectives
                - Key Discussion Points
                - Decisions Made
                - Action Items
                - Next Steps
                - Participants and Roles""",
            
            "action-items": """Create a detailed action items matrix with:
                - Task description
                - Owner/Responsible person
                - Priority (High/Medium/Low)
                - Deadline or timeline
                - Dependencies
                - Success criteria""",
            
            "responsibility-matrix": """Create a RACI matrix showing:
                - Tasks/Deliverables
                - Responsible (R): Who does the work
                - Accountable (A): Who is accountable
                - Consulted (C): Who provides input
                - Informed (I): Who needs updates""",
            
            "project-plan": """Extract project planning information:
                - Project goals and objectives
                - Milestones and timeline
                - Resource requirements
                - Risks and mitigation strategies
                - Dependencies and constraints""",
            
            "gantt-chart": """Structure data for a Gantt chart:
                - Task name
                - Start date
                - End date
                - Duration
                - Dependencies (predecessor tasks)
                - Resource assignments
                - Completion percentage""",
            
            "executive-brief": """Create a high-level executive brief:
                - Strategic implications
                - Key metrics and KPIs discussed
                - Budget considerations
                - Risk assessment
                - Recommendations for leadership"""
        }
        
        selected_prompts = [f"{t}: {template_prompts.get(t, '')}" for t in templates if t in template_prompts]
        
        # Include live notes context if available
        live_context = ""
        if live_notes:
            live_context = f"\nPREVIOUS LIVE NOTES:\n{json.dumps(live_notes, indent=2)}\n"
        
        prompt = f"""Analyze this complete meeting transcript and generate a comprehensive report.
        
{live_context}

FULL TRANSCRIPT:
{transcript[:100000]}  # Use up to 100k chars for comprehensive analysis

Generate detailed reports for the following templates:
{chr(10).join(selected_prompts)}

Format your response as structured JSON with a key for each requested template.
For matrices and charts, use arrays of objects with clear field names.
Be thorough and include all relevant information from the entire transcript.
Use the 128k context window to provide comprehensive analysis."""

        try:
            # Generate with configured LLM using full context
            client, model_name, endpoint = get_ollama_client()
            response = client.generate(
                model=model_name,
                prompt=prompt,
                options={
                    "temperature": 0.7,
                    "num_predict": 8000,  # Allow longer responses for reports
                    "num_ctx": endpoint.context_window,  # Use configured context
                    "top_k": 40,
                    "top_p": 0.9
                }
            )
            
            # Parse JSON response
            try:
                report = json.loads(response['response'])
            except json.JSONDecodeError:
                # Structure the text response
                report = {
                    "full_report": response['response'],
                    "generated_text": True
                }
            
            return {
                "type": "final",
                "session_id": session_id,
                "report": report,
                "timestamp": datetime.utcnow().isoformat(),
                "templates_used": templates,
                "transcript_length": len(transcript),
                "context_used": min(len(transcript), 100000)
            }
            
        except Exception as e:
            logger.error(f"Error generating final report: {e}")
            return {
                "type": "final",
                "session_id": session_id,
                "report": {"error": str(e)},
                "timestamp": datetime.utcnow().isoformat()
            }


# Initialize service
intelligence_service = MeetingIntelligenceService()


@router.post("/live-notes")
async def generate_live_notes(
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Generate real-time meeting notes"""
    
    transcript = request.get("transcript", "")
    templates = request.get("templates", ["executive-summary"])
    session_id = request.get("session_id")
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required")
    
    notes = await intelligence_service.generate_live_notes(
        transcript=transcript,
        templates=templates,
        session_id=session_id
    )
    
    return notes


@router.post("/final-report")
async def generate_final_report(
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Generate comprehensive final report"""
    
    transcript = request.get("transcript", "")
    templates = request.get("templates", ["full-report"])
    live_notes = request.get("live_notes")
    session_id = request.get("session_id")
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required")
    
    report = await intelligence_service.generate_final_report(
        transcript=transcript,
        templates=templates,
        live_notes=live_notes,
        session_id=session_id
    )
    
    return report


@router.websocket("/ws/live-notes/{session_id}")
async def live_notes_websocket(
    websocket: WebSocket,
    session_id: str
):
    """WebSocket endpoint for real-time notes updates during recording"""
    
    await websocket.accept()
    logger.info(f"WebSocket connected for live notes: {session_id}")
    
    try:
        # Buffer for accumulating transcript chunks
        transcript_buffer = []
        last_update_time = datetime.utcnow()
        UPDATE_INTERVAL = 30  # Generate notes every 30 seconds
        
        while True:
            # Receive transcript chunk
            data = await websocket.receive_json()
            
            if data.get("type") == "transcript_chunk":
                transcript_buffer.append(data.get("text", ""))
                
                # Check if it's time to generate notes
                current_time = datetime.utcnow()
                time_diff = (current_time - last_update_time).total_seconds()
                
                if time_diff >= UPDATE_INTERVAL and transcript_buffer:
                    # Generate live notes
                    full_transcript = " ".join(transcript_buffer)
                    
                    notes = await intelligence_service.generate_live_notes(
                        transcript=full_transcript,
                        templates=data.get("templates", ["executive-summary"]),
                        session_id=session_id
                    )
                    
                    # Send notes update
                    await websocket.send_json({
                        "type": "notes_update",
                        "notes": notes["notes"],
                        "timestamp": notes["timestamp"]
                    })
                    
                    last_update_time = current_time
            
            elif data.get("type") == "end_session":
                # Generate final notes before closing
                if transcript_buffer:
                    full_transcript = " ".join(transcript_buffer)
                    
                    final_notes = await intelligence_service.generate_live_notes(
                        transcript=full_transcript,
                        templates=data.get("templates", ["executive-summary"]),
                        session_id=session_id
                    )
                    
                    await websocket.send_json({
                        "type": "final_notes",
                        "notes": final_notes["notes"],
                        "timestamp": final_notes["timestamp"]
                    })
                
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


@router.get("/templates")
async def get_available_templates(
    current_user: User = Depends(get_current_user)
):
    """Get list of available templates for live and final modes"""
    
    return {
        "live_templates": [
            {
                "id": "executive-summary",
                "name": "Executive Summary",
                "description": "Key points and takeaways as they happen"
            },
            {
                "id": "bullet-points",
                "name": "Bullet Points",
                "description": "Quick bullet points of discussion topics"
            },
            {
                "id": "key-decisions",
                "name": "Key Decisions",
                "description": "Important decisions made in real-time"
            },
            {
                "id": "action-alerts",
                "name": "Action Alerts",
                "description": "Immediate action items as they come up"
            }
        ],
        "final_templates": [
            {
                "id": "full-report",
                "name": "Full Report",
                "description": "Comprehensive meeting report with context"
            },
            {
                "id": "action-items",
                "name": "Action Items Matrix",
                "description": "Detailed task assignments with owners and deadlines"
            },
            {
                "id": "responsibility-matrix",
                "name": "Responsibility Matrix",
                "description": "RACI matrix showing who does what"
            },
            {
                "id": "project-plan",
                "name": "Project Plan",
                "description": "Timeline and milestones from discussion"
            },
            {
                "id": "gantt-chart",
                "name": "Gantt Chart Data",
                "description": "Task dependencies and timeline visualization"
            },
            {
                "id": "executive-brief",
                "name": "Executive Brief",
                "description": "High-level summary for leadership"
            }
        ]
    }


@router.get("/model-status")
async def get_model_status(
    current_user: User = Depends(get_current_user)
):
    """Check if Gemma2 model is loaded and ready"""
    
    try:
        # Get current endpoint and check model
        client, model_name, endpoint = get_ollama_client()
        models = client.list()
        model_info = None
        
        for model in models.get('models', []):
            if model_name in model.get('name', ''):
                model_info = model
                break
        
        if not model_info:
            # Try partial match
            for model in models.get('models', []):
                if any(part in model.get('name', '') for part in model_name.split(':')):
                    model_info = model
                    break
        
        return {
            "status": "ready" if model_info else "not_loaded",
            "model": model_info,
            "endpoint": endpoint.name,
            "provider": endpoint.provider,
            "url": endpoint.url,
            "context_window": endpoint.context_window,
            "capabilities": [
                "128k context window",
                "Memory-mapped for fast access",
                "Optimized for meeting analysis",
                "Real-time and batch processing"
            ]
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Ollama service may not be running"
        }