"""Enhanced Export Templates API"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response, FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import json
from datetime import datetime
import logging

from database.database import get_db
from database.models import RecordingSession as DBRecordingSession, Transcription
from services.unified_agent_service import unified_agent_service

router = APIRouter(prefix="/api/sessions", tags=["export-templates"])
logger = logging.getLogger(__name__)

def format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def format_timestamp(seconds: float) -> str:
    """Format timestamp in seconds to MM:SS or HH:MM:SS"""
    return format_duration(seconds)

@router.get("/{session_id}/export/meeting-minutes")
async def export_meeting_minutes(
    session_id: str,
    format: str = "txt",
    db: Session = Depends(get_db)
):
    """Export formatted meeting minutes"""
    try:
        # Get session from database
        session = db.query(DBRecordingSession).filter(
            DBRecordingSession.session_id == session_id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get transcription segments
        segments = db.query(Transcription).filter(
            Transcription.session_id == str(session.id)
        ).order_by(Transcription.start_time).all()
        
        # Parse summary if exists
        summary_data = {}
        if session.summary:
            try:
                summary_data = json.loads(session.summary) if isinstance(session.summary, str) else session.summary
            except:
                summary_data = {}
        
        # Generate meeting minutes
        minutes = []
        
        # Header
        minutes.append("=" * 80)
        minutes.append("MEETING MINUTES")
        minutes.append("=" * 80)
        minutes.append("")
        
        # Meeting Information
        minutes.append("Meeting Information:")
        minutes.append("-" * 40)
        minutes.append(f"Title: {session.title or session.name or 'Untitled Meeting'}")
        minutes.append(f"Date: {session.created_at.strftime('%B %d, %Y')}")
        if session.started_at:
            minutes.append(f"Start Time: {session.started_at.strftime('%I:%M %p')}")
        if session.ended_at:
            minutes.append(f"End Time: {session.ended_at.strftime('%I:%M %p')}")
        minutes.append(f"Duration: {format_duration(session.duration or 0)}")
        minutes.append("")
        
        # Attendees (if available from speaker detection)
        speakers = set()
        for seg in segments:
            if seg.speaker:
                speakers.add(seg.speaker)
        
        if speakers:
            minutes.append("Attendees:")
            minutes.append("-" * 40)
            for speaker in sorted(speakers):
                minutes.append(f"  • {speaker}")
            minutes.append("")
        
        # Executive Summary
        if summary_data.get('analysis', {}).get('executive'):
            minutes.append("Executive Summary:")
            minutes.append("-" * 40)
            minutes.append(summary_data['analysis']['executive'])
            minutes.append("")
        
        # Agenda/Key Topics
        if summary_data.get('analysis', {}).get('bullets'):
            minutes.append("Key Discussion Points:")
            minutes.append("-" * 40)
            for bullet in summary_data['analysis']['bullets']:
                minutes.append(f"  • {bullet}")
            minutes.append("")
        
        # Decisions Made
        if summary_data.get('analysis', {}).get('decisions'):
            minutes.append("Decisions Made:")
            minutes.append("-" * 40)
            for i, decision in enumerate(summary_data['analysis']['decisions'], 1):
                minutes.append(f"  {i}. {decision}")
            minutes.append("")
        
        # Action Items
        if summary_data.get('analysis', {}).get('actions'):
            minutes.append("Action Items:")
            minutes.append("-" * 40)
            for action in summary_data['analysis']['actions']:
                owner = action.get('owner', 'TBD')
                priority = action.get('priority', 'medium').upper()
                minutes.append(f"  □ {action['action']}")
                minutes.append(f"    Owner: {owner} | Priority: {priority}")
                minutes.append("")
        
        # Next Steps
        minutes.append("Next Steps:")
        minutes.append("-" * 40)
        if summary_data.get('analysis', {}).get('actions'):
            minutes.append("  1. Review and assign action items")
            minutes.append("  2. Schedule follow-up meeting if needed")
            minutes.append("  3. Distribute meeting minutes to all attendees")
        else:
            minutes.append("  No specific next steps identified")
        minutes.append("")
        
        # Footer
        minutes.append("-" * 80)
        minutes.append(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
        minutes.append("Meeting-Ops AI Recording System")
        
        # Return formatted minutes
        content = "\n".join(minutes)
        
        if format == "txt":
            return Response(
                content=content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=meeting_minutes_{session_id}.txt"
                }
            )
        else:
            # Return as JSON for other formats
            return {
                "session_id": session_id,
                "title": session.title or session.name,
                "content": content,
                "sections": {
                    "executive_summary": summary_data.get('analysis', {}).get('executive'),
                    "key_points": summary_data.get('analysis', {}).get('bullets'),
                    "decisions": summary_data.get('analysis', {}).get('decisions'),
                    "action_items": summary_data.get('analysis', {}).get('actions')
                }
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting meeting minutes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/export/action-items")
async def export_action_items(
    session_id: str,
    format: str = "txt",
    db: Session = Depends(get_db)
):
    """Export just action items with owners"""
    try:
        # Get session from database
        session = db.query(DBRecordingSession).filter(
            DBRecordingSession.session_id == session_id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Parse summary for action items
        action_items = []
        if session.summary:
            try:
                summary_data = json.loads(session.summary) if isinstance(session.summary, str) else session.summary
                action_items = summary_data.get('analysis', {}).get('actions', [])
            except:
                pass
        
        # If no action items in summary, try to extract from transcript
        if not action_items and session.transcript:
            # Call AI to extract action items
            result = await unified_agent_service.analyze_meeting(
                session_id=session_id,
                transcript=session.transcript
            )
            if result.get('success') and result.get('analysis'):
                action_items = result['analysis'].get('actions', [])
        
        # Format action items
        lines = []
        lines.append("=" * 60)
        lines.append("ACTION ITEMS")
        lines.append(f"Meeting: {session.title or session.name or 'Untitled'}")
        lines.append(f"Date: {session.created_at.strftime('%B %d, %Y')}")
        lines.append("=" * 60)
        lines.append("")
        
        if action_items:
            # Group by priority
            high_priority = [a for a in action_items if a.get('priority', '').lower() == 'high']
            medium_priority = [a for a in action_items if a.get('priority', '').lower() == 'medium']
            low_priority = [a for a in action_items if a.get('priority', '').lower() == 'low']
            
            if high_priority:
                lines.append("HIGH PRIORITY:")
                lines.append("-" * 30)
                for i, action in enumerate(high_priority, 1):
                    owner = action.get('owner', 'Unassigned')
                    lines.append(f"{i}. {action['action']}")
                    lines.append(f"   Owner: {owner}")
                    lines.append("")
            
            if medium_priority:
                lines.append("MEDIUM PRIORITY:")
                lines.append("-" * 30)
                for i, action in enumerate(medium_priority, 1):
                    owner = action.get('owner', 'Unassigned')
                    lines.append(f"{i}. {action['action']}")
                    lines.append(f"   Owner: {owner}")
                    lines.append("")
            
            if low_priority:
                lines.append("LOW PRIORITY:")
                lines.append("-" * 30)
                for i, action in enumerate(low_priority, 1):
                    owner = action.get('owner', 'Unassigned')
                    lines.append(f"{i}. {action['action']}")
                    lines.append(f"   Owner: {owner}")
                    lines.append("")
            
            # Summary
            lines.append("-" * 60)
            lines.append(f"Total Action Items: {len(action_items)}")
            lines.append(f"High Priority: {len(high_priority)}")
            lines.append(f"Medium Priority: {len(medium_priority)}")
            lines.append(f"Low Priority: {len(low_priority)}")
        else:
            lines.append("No action items identified in this meeting.")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
        
        content = "\n".join(lines)
        
        if format == "txt":
            return Response(
                content=content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=action_items_{session_id}.txt"
                }
            )
        else:
            return {
                "session_id": session_id,
                "title": session.title or session.name,
                "action_items": action_items,
                "summary": {
                    "total": len(action_items),
                    "high": len([a for a in action_items if a.get('priority', '').lower() == 'high']),
                    "medium": len([a for a in action_items if a.get('priority', '').lower() == 'medium']),
                    "low": len([a for a in action_items if a.get('priority', '').lower() == 'low'])
                }
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting action items: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/export/executive-summary")
async def export_executive_summary(
    session_id: str,
    format: str = "txt",
    db: Session = Depends(get_db)
):
    """Export one-page executive summary"""
    try:
        # Get session from database
        session = db.query(DBRecordingSession).filter(
            DBRecordingSession.session_id == session_id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Parse summary
        summary_data = {}
        if session.summary:
            try:
                summary_data = json.loads(session.summary) if isinstance(session.summary, str) else session.summary
            except:
                pass
        
        # If no summary, generate one
        if not summary_data and session.transcript:
            result = await unified_agent_service.analyze_meeting(
                session_id=session_id,
                transcript=session.transcript
            )
            if result.get('success') and result.get('analysis'):
                summary_data = {'analysis': result['analysis']}
        
        # Format executive summary
        lines = []
        lines.append("=" * 70)
        lines.append("EXECUTIVE SUMMARY")
        lines.append("=" * 70)
        lines.append("")
        
        # Meeting header
        lines.append(f"Meeting: {session.title or session.name or 'Untitled Meeting'}")
        lines.append(f"Date: {session.created_at.strftime('%B %d, %Y')}")
        lines.append(f"Duration: {format_duration(session.duration or 0)}")
        lines.append("")
        lines.append("-" * 70)
        lines.append("")
        
        # Executive Overview
        if summary_data.get('analysis', {}).get('executive'):
            lines.append("OVERVIEW")
            lines.append("")
            lines.append(summary_data['analysis']['executive'])
            lines.append("")
        
        # Key Outcomes
        if summary_data.get('analysis', {}).get('decisions'):
            lines.append("KEY DECISIONS")
            lines.append("")
            for decision in summary_data['analysis']['decisions'][:3]:  # Top 3 decisions
                lines.append(f"• {decision}")
            lines.append("")
        
        # Critical Action Items
        if summary_data.get('analysis', {}).get('actions'):
            high_priority = [a for a in summary_data['analysis']['actions'] 
                           if a.get('priority', '').lower() == 'high'][:3]
            if high_priority:
                lines.append("CRITICAL ACTION ITEMS")
                lines.append("")
                for action in high_priority:
                    owner = action.get('owner', 'TBD')
                    lines.append(f"• {action['action']} ({owner})")
                lines.append("")
        
        # Key Discussion Points (condensed)
        if summary_data.get('analysis', {}).get('bullets'):
            lines.append("KEY TOPICS DISCUSSED")
            lines.append("")
            for bullet in summary_data['analysis']['bullets'][:3]:  # Top 3 points
                lines.append(f"• {bullet}")
            lines.append("")
        
        # Bottom line
        lines.append("-" * 70)
        lines.append("")
        lines.append("RECOMMENDATION")
        lines.append("")
        if summary_data.get('analysis', {}).get('actions'):
            lines.append("Immediate attention required on high-priority action items.")
            lines.append("Schedule follow-up meeting within 1-2 weeks to review progress.")
        else:
            lines.append("No critical actions required. Continue with current plans.")
        
        lines.append("")
        lines.append("=" * 70)
        lines.append(f"Prepared: {datetime.now().strftime('%B %d, %Y')}")
        
        content = "\n".join(lines)
        
        if format == "txt":
            return Response(
                content=content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=executive_summary_{session_id}.txt"
                }
            )
        else:
            return {
                "session_id": session_id,
                "title": session.title or session.name,
                "content": content,
                "data": summary_data.get('analysis', {})
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting executive summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))