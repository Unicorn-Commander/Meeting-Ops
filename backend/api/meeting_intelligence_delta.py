"""
Live Meeting Intelligence and Session Templates API endpoints
Implements missing endpoints from API Delta Document
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Optional, Any
import json
import asyncio
from pathlib import Path
from datetime import datetime
import uuid

from database.database import get_db
from models.settings import (
    LiveTemplateContent,
    GenerateTemplateRequest,
    UpdateTemplateRequest
)
from services.unified_llm_service import UnifiedLLMService
from services.transcription_service import transcription_service  # Import singleton instance

router = APIRouter(tags=["meeting-intelligence"])

# Storage paths
TEMPLATES_DIR = Path("data/session_templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Initialize services
llm_service = UnifiedLLMService()
# transcription_service is already initialized as singleton

# Active WebSocket connections
active_connections: Dict[str, WebSocket] = {}


# ==================== LIVE MEETING TEMPLATES ====================

@router.get("/api/meeting-intelligence-real/live-templates/{session_id}", response_model=LiveTemplateContent)
async def get_live_templates(session_id: str, db: Session = Depends(get_db)):
    """
    Get live-generated templates during meeting
    Returns real-time AI-generated content for the ongoing meeting
    """
    try:
        # Get session transcript
        from models.session import RecordingSession
        session = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        # Get transcript text
        transcript = session.transcript if session.transcript else ""
        
        if len(transcript) < 100:
            # Not enough content yet
            return LiveTemplateContent(
                executive_summary="Waiting for more content...",
                action_items="No action items yet",
                key_decisions="No decisions recorded yet",
                participants="Analyzing participants...",
                next_steps="To be determined",
                risks_issues="None identified"
            )
        
        # Generate templates using LLM
        templates = {}
        
        # Executive Summary
        summary_prompt = f"""Generate a brief executive summary of this meeting:
{transcript}

Provide a 2-3 sentence summary focusing on the main topic and outcome."""
        templates["executive_summary"] = llm_service.generate_response(summary_prompt)
        
        # Action Items
        action_prompt = f"""Extract action items from this meeting transcript:
{transcript}

List each action item with the responsible person if mentioned. Format as numbered list."""
        templates["action_items"] = llm_service.generate_response(action_prompt)
        
        # Key Decisions
        decisions_prompt = f"""Identify key decisions made in this meeting:
{transcript}

List the main decisions that were agreed upon."""
        templates["key_decisions"] = llm_service.generate_response(decisions_prompt)
        
        # Participants
        participants_prompt = f"""List the meeting participants based on this transcript:
{transcript}

Identify speakers and their roles if mentioned."""
        templates["participants"] = llm_service.generate_response(participants_prompt)
        
        # Next Steps
        next_steps_prompt = f"""What are the next steps from this meeting:
{transcript}

List follow-up actions and future meetings mentioned."""
        templates["next_steps"] = llm_service.generate_response(next_steps_prompt)
        
        # Risks and Issues
        risks_prompt = f"""Identify any risks or issues discussed:
{transcript}

List potential problems, blockers, or concerns raised."""
        templates["risks_issues"] = llm_service.generate_response(risks_prompt)
        
        return LiveTemplateContent(**templates)
        
    except Exception as e:
        print(f"Error generating live templates: {e}")
        return LiveTemplateContent(
            executive_summary=f"Error generating summary: {str(e)}",
            action_items="Error extracting action items",
            key_decisions="Error identifying decisions",
            participants="Error analyzing participants",
            next_steps="Error determining next steps",
            risks_issues="Error identifying risks"
        )


@router.post("/api/meeting-intelligence-real/generate-template")
async def generate_template(request: GenerateTemplateRequest, db: Session = Depends(get_db)):
    """
    Generate specific template from transcript
    Allows on-demand generation of specific template types
    """
    try:
        # Get session transcript
        from models.session import RecordingSession
        session = db.query(RecordingSession).filter(
            RecordingSession.id == request.session_id
        ).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {request.session_id} not found"
            )
        
        transcript = session.transcript if session.transcript else ""
        
        if len(transcript) < 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not enough transcript content to generate template"
            )
        
        # Generate based on template ID
        template_prompts = {
            "executive-summary": "Generate an executive summary of this meeting",
            "action-items": "Extract all action items with owners and deadlines",
            "key-decisions": "List all key decisions made in this meeting",
            "participants": "Identify all meeting participants and their roles",
            "next-steps": "List the next steps and follow-up actions",
            "risks-issues": "Identify risks, issues, and concerns discussed",
            "meeting-notes": "Create detailed meeting notes",
            "technical-summary": "Create a technical summary focusing on technical decisions and architecture"
        }
        
        prompt = template_prompts.get(request.template_id)
        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown template ID: {request.template_id}"
            )
        
        # Generate content
        full_prompt = f"{prompt}:\n\n{transcript}"
        content = llm_service.generate_response(full_prompt)
        
        # Save generated template
        template_file = TEMPLATES_DIR / f"{request.session_id}_{request.template_id}.json"
        template_data = {
            "session_id": request.session_id,
            "template_id": request.template_id,
            "content": content,
            "generated_at": datetime.utcnow().isoformat()
        }
        
        with open(template_file, "w") as f:
            json.dump(template_data, f, indent=2)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "template_id": request.template_id,
                "content": content
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate template: {str(e)}"
        )


# ==================== SESSION TEMPLATES STORAGE ====================

@router.get("/api/sessions/{session_id}/templates")
async def get_session_templates(session_id: str):
    """
    Get saved templates for a session
    Returns all generated templates for a specific session
    """
    templates = {}
    
    # Find all template files for this session
    for template_file in TEMPLATES_DIR.glob(f"{session_id}_*.json"):
        try:
            with open(template_file, "r") as f:
                data = json.load(f)
                template_id = data.get("template_id", "unknown")
                templates[template_id] = data.get("content", "")
        except Exception as e:
            print(f"Error loading template {template_file}: {e}")
    
    if not templates:
        # Return empty object if no templates found
        return {}
    
    return templates


@router.put("/api/sessions/{session_id}/templates/{template_id}")
async def save_session_template(
    session_id: str,
    template_id: str,
    request: UpdateTemplateRequest
):
    """
    Save/update template content for a session
    Allows manual editing and saving of generated templates
    """
    try:
        # Create template file path
        template_file = TEMPLATES_DIR / f"{session_id}_{template_id}.json"
        
        # Save template data
        template_data = {
            "session_id": session_id,
            "template_id": template_id,
            "content": request.content,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        with open(template_file, "w") as f:
            json.dump(template_data, f, indent=2)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": f"Template {template_id} saved for session {session_id}"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save template: {str(e)}"
        )


# ==================== WEBSOCKET ENDPOINTS ====================

@router.websocket("/ws/transcription/{session_id}")
async def websocket_transcription(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for live transcription streaming
    Sends real-time transcription segments to connected clients
    """
    await websocket.accept()
    active_connections[session_id] = websocket
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connection",
            "message": "Connected to transcription stream",
            "session_id": session_id
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                # Handle ping/pong for keepalive
                if data == "ping":
                    await websocket.send_text("pong")
                
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({
                    "type": "keepalive",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
    except WebSocketDisconnect:
        if session_id in active_connections:
            del active_connections[session_id]
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        print(f"WebSocket error for session {session_id}: {e}")
        if session_id in active_connections:
            del active_connections[session_id]


async def broadcast_transcription_segment(session_id: str, segment: Dict[str, Any]):
    """
    Broadcast transcription segment to connected WebSocket clients
    Called by transcription service when new segments are available
    """
    if session_id in active_connections:
        websocket = active_connections[session_id]
        try:
            await websocket.send_json({
                "type": "transcription",
                "segment": segment
            })
        except Exception as e:
            print(f"Error broadcasting to session {session_id}: {e}")
            # Remove failed connection
            if session_id in active_connections:
                del active_connections[session_id]


# ==================== LIVE NOTES WITH CONTENT TRIGGERS ====================

@router.post("/api/meeting-intelligence-real/live-notes")
async def generate_live_notes(
    session_id: str,
    word_count_threshold: int = 500,
    db: Session = Depends(get_db)
):
    """
    Generate live meeting notes based on content triggers
    Supports word count thresholds for automatic generation
    """
    try:
        # Get session and transcript
        from models.session import RecordingSession
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id
        ).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        transcript = session.transcript if session.transcript else ""
        word_count = len(transcript.split())
        
        # Check if threshold is met
        if word_count < word_count_threshold:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "waiting",
                    "message": f"Waiting for more content. Current: {word_count} words, Required: {word_count_threshold}",
                    "word_count": word_count,
                    "threshold": word_count_threshold
                }
            )
        
        # Generate live notes
        notes_prompt = f"""Generate concise meeting notes from this transcript.
Include:
1. Main topics discussed
2. Key points and decisions
3. Action items
4. Notable quotes or statements

Transcript:
{transcript}"""
        
        notes = llm_service.generate_response(notes_prompt)
        
        # Save notes
        notes_file = TEMPLATES_DIR / f"{session_id}_live_notes.json"
        notes_data = {
            "session_id": session_id,
            "notes": notes,
            "word_count": word_count,
            "generated_at": datetime.utcnow().isoformat()
        }
        
        with open(notes_file, "w") as f:
            json.dump(notes_data, f, indent=2)
        
        # Broadcast to WebSocket if connected
        if session_id in active_connections:
            await active_connections[session_id].send_json({
                "type": "live_notes",
                "content": notes,
                "word_count": word_count
            })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "notes": notes,
                "word_count": word_count,
                "generated_at": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate live notes: {str(e)}"
        )


# ==================== SUMMARIZATION TEMPLATES FIX ====================

@router.get("/api/summarization-templates")
async def get_summarization_templates():
    """
    Get available summarization templates
    Returns properly formatted array of template objects
    """
    templates = [
        {
            "id": "executive-summary",
            "name": "Executive Summary",
            "description": "High-level overview for executives",
            "prompt": "Generate an executive summary focusing on key decisions and outcomes",
            "category": "summary"
        },
        {
            "id": "technical-brief",
            "name": "Technical Brief",
            "description": "Technical details and architecture decisions",
            "prompt": "Create a technical summary focusing on implementation details",
            "category": "technical"
        },
        {
            "id": "action-items",
            "name": "Action Items",
            "description": "List of tasks and assignments",
            "prompt": "Extract all action items with owners and deadlines",
            "category": "tasks"
        },
        {
            "id": "meeting-minutes",
            "name": "Meeting Minutes",
            "description": "Formal meeting minutes",
            "prompt": "Generate formal meeting minutes with agenda items and decisions",
            "category": "formal"
        },
        {
            "id": "key-decisions",
            "name": "Key Decisions",
            "description": "Important decisions made",
            "prompt": "List all key decisions and agreements reached",
            "category": "decisions"
        }
    ]
    
    return templates