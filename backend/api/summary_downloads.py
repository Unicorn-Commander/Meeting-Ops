"""
Summary Download Endpoints
Provides text, PDF, and DOCX export functionality for meeting summaries
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response, FileResponse
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import RecordingSession as DBRecordingSession
import json
import tempfile
import os
from datetime import datetime

router = APIRouter(prefix="/api/simple/recording-sessions", tags=["summary-downloads"])

@router.get("/{session_id}/download/summary")
async def download_summary_text(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download formatted summary as text"""
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build summary text
    summary_text = f"MEETING SUMMARY\n"
    summary_text += "=" * 50 + "\n\n"
    summary_text += f"Title: {session.title or session.name or 'Untitled Meeting'}\n"
    summary_text += f"Date: {session.created_at.strftime('%B %d, %Y') if session.created_at else 'Unknown'}\n"
    summary_text += f"Duration: {int(session.duration // 60)} minutes\n"
    
    # Add metadata
    if session.processing_metadata:
        summary_text += f"Participants: {session.processing_metadata.get('speaker_count', 'Unknown')}\n"
        summary_text += f"Total Words: {session.processing_metadata.get('word_count', 'Unknown')}\n"
    
    summary_text += "\n" + "=" * 50 + "\n\n"
    
    # Use final_summary if available, otherwise fall back to summary
    summary_data = session.final_summary or {}
    if not summary_data and session.summary:
        try:
            summary_data = json.loads(session.summary) if isinstance(session.summary, str) else session.summary
        except:
            summary_data = {}
    
    # Executive Summary
    summary_text += "EXECUTIVE SUMMARY\n"
    summary_text += "-" * 20 + "\n"
    summary_text += summary_data.get("executive", "No executive summary available.") + "\n\n"
    
    # Key Points
    summary_text += "KEY DISCUSSION POINTS\n"
    summary_text += "-" * 20 + "\n"
    bullets = summary_data.get("bullets", [])
    if bullets:
        for i, bullet in enumerate(bullets, 1):
            summary_text += f"{i}. {bullet}\n"
    else:
        summary_text += "No key points recorded.\n"
    summary_text += "\n"
    
    # Action Items
    summary_text += "ACTION ITEMS\n"
    summary_text += "-" * 20 + "\n"
    actions = summary_data.get("actions", [])
    if actions:
        for action in actions:
            if isinstance(action, dict):
                owner = action.get("owner", "Unassigned")
                priority = action.get("priority", "Normal")
                task = action.get("action", "")
                summary_text += f"• [{priority.upper()}] {task} (Owner: {owner})\n"
            else:
                summary_text += f"• {action}\n"
    else:
        summary_text += "No action items identified.\n"
    summary_text += "\n"
    
    # Decisions
    summary_text += "DECISIONS MADE\n"
    summary_text += "-" * 20 + "\n"
    decisions = summary_data.get("decisions", [])
    if decisions:
        for decision in decisions:
            summary_text += f"• {decision}\n"
    else:
        summary_text += "No decisions recorded.\n"
    summary_text += "\n"
    
    # Progressive Summaries (if any)
    if session.progressive_summaries and len(session.progressive_summaries) > 0:
        summary_text += "PROGRESSIVE INSIGHTS\n"
        summary_text += "-" * 20 + "\n"
        summary_text += f"Generated {len(session.progressive_summaries)} summaries during recording.\n"
        last_summary = session.progressive_summaries[-1]
        if isinstance(last_summary, dict):
            summary_text += f"Final word count: {last_summary.get('word_count_at_summary', 'Unknown')}\n"
        summary_text += "\n"
    
    # Footer
    summary_text += "=" * 50 + "\n"
    summary_text += f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
    summary_text += "Powered by Meeting-Ops AI Recording System\n"
    
    filename = f"{(session.name or session.title or 'meeting').replace(' ', '_')}_summary.txt"
    return Response(
        content=summary_text,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@router.get("/{session_id}/download/summary/pdf")
async def download_summary_pdf(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download summary as PDF (placeholder - requires reportlab installation)"""
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # For now, return a text file with .pdf extension
    # In production, you would use reportlab or similar to generate actual PDF
    raise HTTPException(
        status_code=501, 
        detail="PDF export not yet implemented. Please use text format for now."
    )

@router.get("/{session_id}/download/summary/docx")
async def download_summary_docx(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download summary as DOCX (placeholder - requires python-docx installation)"""
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # For now, return error
    # In production, you would use python-docx to generate actual DOCX
    raise HTTPException(
        status_code=501, 
        detail="DOCX export not yet implemented. Please use text format for now."
    )

@router.get("/{session_id}/download/minutes")
async def download_meeting_minutes(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Download formatted meeting minutes"""
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build meeting minutes
    minutes = f"MEETING MINUTES\n"
    minutes += "=" * 50 + "\n\n"
    minutes += f"Meeting: {session.title or session.name or 'Untitled'}\n"
    minutes += f"Date: {session.created_at.strftime('%B %d, %Y at %I:%M %p') if session.created_at else 'Unknown'}\n"
    minutes += f"Duration: {int(session.duration // 60)} minutes {int(session.duration % 60)} seconds\n"
    
    if session.processing_metadata:
        minutes += f"Attendees: {session.processing_metadata.get('speaker_count', 'Unknown')} participants\n"
    
    minutes += "\n" + "-" * 50 + "\n\n"
    
    # Agenda/Discussion Points
    minutes += "DISCUSSION POINTS:\n\n"
    
    summary_data = session.final_summary or {}
    bullets = summary_data.get("bullets", [])
    if bullets:
        for i, bullet in enumerate(bullets, 1):
            minutes += f"{i}. {bullet}\n"
    minutes += "\n"
    
    # Action Items
    minutes += "ACTION ITEMS:\n\n"
    actions = summary_data.get("actions", [])
    if actions:
        for i, action in enumerate(actions, 1):
            if isinstance(action, dict):
                minutes += f"{i}. {action.get('action', '')}\n"
                minutes += f"   Assigned to: {action.get('owner', 'TBD')}\n"
                minutes += f"   Priority: {action.get('priority', 'Normal')}\n\n"
            else:
                minutes += f"{i}. {action}\n\n"
    
    # Decisions
    minutes += "DECISIONS:\n\n"
    decisions = summary_data.get("decisions", [])
    if decisions:
        for i, decision in enumerate(decisions, 1):
            minutes += f"{i}. {decision}\n"
    
    minutes += "\n" + "-" * 50 + "\n"
    minutes += f"Minutes prepared: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
    
    filename = f"{(session.name or session.title or 'meeting').replace(' ', '_')}_minutes.txt"
    return Response(
        content=minutes,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )