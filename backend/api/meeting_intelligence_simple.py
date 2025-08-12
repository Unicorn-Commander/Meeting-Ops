"""
Real Meeting Intelligence API using UnifiedLLMService
Provides actual AI analysis from transcript data
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import json

from services.unified_llm_service import UnifiedLLMService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meeting-intelligence-simple", tags=["meeting-intelligence-real"])

# Initialize LLM service
llm_service = UnifiedLLMService()

@router.post("/live-notes")
async def generate_live_notes(request: Dict[str, Any]):
    """Generate real live meeting notes using AI analysis"""
    
    transcript = request.get("transcript", "")
    templates = request.get("templates", ["executive-summary"])
    session_id = request.get("session_id")
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required")
    
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty")
    
    logger.info(f"Generating live notes for session {session_id} with {len(transcript)} chars, templates: {templates}")
    
    try:
        # Generate AI summary using UnifiedLLMService
        summary_result = llm_service.summarize_meeting(transcript, template="standard")
        
        # Initialize response structure
        notes = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "templates_used": templates,
            "notes": {}
        }
        
        # Extract content based on requested templates
        if "executive-summary" in templates:
            notes["notes"]["executive_summary"] = {
                "title": "Executive Summary",
                "content": summary_result.get("summary", "Meeting analysis in progress..."),
                "key_points": summary_result.get("action_items", [])[:5]  # Top 5 points
            }
        
        if "bullet-points" in templates:
            # Generate bullet points from summary
            bullet_prompt = f"Convert this meeting summary into 5-7 concise bullet points:\n\n{transcript[:1500]}"
            bullet_response = llm_service._generate_with_ollama(transcript[:1500], bullet_prompt)
            
            # Parse bullet points
            bullet_items = []
            if bullet_response:
                for line in bullet_response.split('\n'):
                    line = line.strip()
                    if line and (line.startswith('•') or line.startswith('-') or line.startswith('*')):
                        bullet_items.append(line)
                    elif line and len(line) > 10 and not line.endswith(':'):
                        bullet_items.append(f"• {line}")
            
            notes["notes"]["bullet_points"] = {
                "title": "Discussion Points",
                "items": bullet_items[:7] if bullet_items else ["Meeting discussion captured"]
            }
        
        if "key-decisions" in templates:
            # Generate decisions
            decision_prompt = f"Extract key decisions made in this meeting. List only the decisions:\n\n{transcript[:1500]}"
            decision_response = llm_service._generate_with_ollama(transcript[:1500], decision_prompt)
            
            decisions = []
            if decision_response:
                for line in decision_response.split('\n'):
                    line = line.strip()
                    if line and len(line) > 10 and ('decide' in line.lower() or 'agreed' in line.lower() or 'approved' in line.lower()):
                        decisions.append(line.replace('•', '').replace('-', '').strip())
            
            notes["notes"]["key_decisions"] = {
                "title": "Key Decisions",
                "items": decisions[:5] if decisions else ["No specific decisions identified"]
            }
        
        if "action-alerts" in templates or "action-items" in templates:
            # Generate action items
            action_prompt = f"Extract action items from this meeting. Format as JSON with task, owner, and priority:\n\n{transcript[:1500]}"
            action_response = llm_service._generate_with_ollama(transcript[:1500], action_prompt)
            
            action_items = []
            if action_response and summary_result.get("action_items"):
                # Use structured action items from summary
                for item in summary_result.get("action_items", [])[:5]:
                    if isinstance(item, str):
                        action_items.append({
                            "task": item,
                            "owner": "Team Member",
                            "priority": "medium",
                            "deadline": "TBD"
                        })
                    elif isinstance(item, dict):
                        action_items.append(item)
            
            notes["notes"]["action_items"] = {
                "title": "Action Items",
                "items": action_items if action_items else [{"task": "Follow up on meeting discussion", "owner": "Team", "priority": "medium"}]
            }
        
        logger.info(f"Generated live notes with {len(notes['notes'])} sections")
        return notes
        
    except Exception as e:
        logger.error(f"Error generating live notes: {e}")
        # Return minimal structure on error
        return {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "templates_used": templates,
            "notes": {
                "executive_summary": {
                    "title": "Executive Summary",
                    "content": "AI analysis temporarily unavailable. Please try again.",
                    "key_points": []
                }
            },
            "error": "AI service temporarily unavailable"
        }

@router.post("/final-report")
async def generate_final_report(request: Dict[str, Any]):
    """Generate real final meeting report using AI analysis"""
    
    transcript = request.get("transcript", "")
    templates = request.get("templates", ["full-report"])
    session_id = request.get("session_id")
    live_notes = request.get("live_notes")
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required")
    
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty")
    
    logger.info(f"Generating final report for session {session_id} with {len(transcript)} chars, templates: {templates}")
    
    try:
        # Generate comprehensive AI analysis
        executive_summary = llm_service.summarize_meeting(transcript, template="executive")
        technical_summary = llm_service.summarize_meeting(transcript, template="technical")
        standard_summary = llm_service.summarize_meeting(transcript, template="standard")
        
        # Extract participants from transcript
        participants = []
        participant_prompt = f"Extract the names of participants from this meeting transcript. List only names:\n\n{transcript[:1000]}"
        participant_response = llm_service._generate_with_ollama(transcript[:1000], participant_prompt)
        
        if participant_response:
            for line in participant_response.split('\n'):
                line = line.strip()
                if line and len(line) > 2 and len(line) < 50:
                    # Simple name detection
                    if any(char.isupper() for char in line) and not line.lower().startswith('speaker'):
                        participants.append(line.replace('•', '').replace('-', '').strip())
        
        # Generate comprehensive report
        report = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "report": {
                "title": "AI-Generated Meeting Report",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "duration": "Recorded session",
                "participants": participants[:8] if participants else ["Meeting participants"],
                "summary": executive_summary.get("summary", "Comprehensive meeting analysis generated from transcript."),
                "sections": {}
            }
        }
        
        # Add sections based on requested templates
        if "full-report" in templates:
            report["report"]["sections"]["overview"] = {
                "title": "Meeting Overview",
                "content": standard_summary.get("summary", "Meeting discussion and decisions captured.")
            }
            
            # Extract key topics
            topics_prompt = f"List the main topics discussed in this meeting. Be specific:\n\n{transcript[:2000]}"
            topics_response = llm_service._generate_with_ollama(transcript[:2000], topics_prompt)
            
            topics = []
            if topics_response:
                for line in topics_response.split('\n'):
                    line = line.strip()
                    if line and len(line) > 10 and not line.endswith(':'):
                        topics.append(line.replace('•', '').replace('-', '').strip())
            
            report["report"]["sections"]["key_topics"] = {
                "title": "Key Topics Discussed",
                "items": topics[:6] if topics else ["Meeting topics analyzed"]
            }
        
        if "action-items" in templates:
            # Detailed action items analysis
            action_items = []
            if executive_summary.get("action_items"):
                for item in executive_summary.get("action_items", [])[:8]:
                    if isinstance(item, str):
                        action_items.append({
                            "task": item,
                            "owner": "Assigned Team Member",
                            "deadline": "To be determined",
                            "priority": "medium"
                        })
                    elif isinstance(item, dict):
                        action_items.append(item)
            
            report["report"]["sections"]["action_items"] = {
                "title": "Action Items & Deliverables",
                "items": action_items if action_items else [{"task": "Review meeting outcomes", "owner": "Team", "deadline": "TBD"}]
            }
        
        if "responsibility-matrix" in templates:
            # Generate responsibility matrix
            responsibility_prompt = f"Create a responsibility matrix from this meeting. Who is responsible for what:\n\n{transcript[:1500]}"
            responsibility_response = llm_service._generate_with_ollama(transcript[:1500], responsibility_prompt)
            
            report["report"]["sections"]["responsibilities"] = {
                "title": "Responsibility Matrix",
                "content": responsibility_response if responsibility_response else "Responsibilities to be clarified based on meeting discussion."
            }
        
        if "project-plan" in templates:
            # Extract project planning elements
            project_prompt = f"Extract project timeline and milestones from this meeting:\n\n{transcript[:1500]}"
            project_response = llm_service._generate_with_ollama(transcript[:1500], project_prompt)
            
            report["report"]["sections"]["project_plan"] = {
                "title": "Project Planning Elements",
                "content": project_response if project_response else "Project planning elements identified from meeting discussion."
            }
        
        if "executive-brief" in templates:
            report["report"]["sections"]["executive_brief"] = {
                "title": "Executive Brief",
                "content": executive_summary.get("summary", "Executive summary of meeting outcomes and strategic implications.")
            }
        
        # Always include decisions and next steps
        decisions = executive_summary.get("key_decisions", [])
        if not decisions and standard_summary.get("key_decisions"):
            decisions = standard_summary.get("key_decisions", [])
        
        report["report"]["sections"]["decisions"] = {
            "title": "Key Decisions Made",
            "items": decisions[:5] if decisions else ["Decisions captured from meeting discussion"]
        }
        
        # Generate next steps
        next_steps_prompt = f"What are the next steps after this meeting? Be specific:\n\n{transcript[-1000:]}"
        next_steps_response = llm_service._generate_with_ollama(transcript[-1000:], next_steps_prompt)
        
        report["report"]["sections"]["next_steps"] = {
            "title": "Next Steps & Follow-up",
            "content": next_steps_response if next_steps_response else "Follow-up actions to be determined based on meeting outcomes."
        }
        
        logger.info(f"Generated final report with {len(report['report']['sections'])} sections")
        return report
        
    except Exception as e:
        logger.error(f"Error generating final report: {e}")
        # Return minimal structure on error
        return {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "report": {
                "title": "Meeting Report",
                "summary": "AI analysis temporarily unavailable. Please try again.",
                "sections": {
                    "overview": {
                        "title": "Overview",
                        "content": "Report generation encountered an error. Please retry."
                    }
                }
            },
            "error": "AI service temporarily unavailable"
        }

@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify the AI-powered API is working"""
    try:
        # Test LLM service availability
        status = llm_service.get_status()
        return {
            "status": "ok",
            "message": "Real AI Meeting Intelligence API is working",
            "llm_service": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"AI service error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }