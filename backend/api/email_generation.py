"""
Email Generation API
Generates contextual follow-up emails based on meeting content
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import RecordingSession as DBRecordingSession
from typing import List, Dict
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simple/recording-sessions", tags=["email-generation"])

@router.post("/{session_id}/generate-emails")
async def generate_emails(
    session_id: str,
    db: Session = Depends(get_db)
) -> List[Dict]:
    """Generate follow-up emails based on meeting content"""
    
    # Get session from database
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if session has transcript
    if not session.transcript_simple and not session.transcript:
        raise HTTPException(status_code=400, detail="Session has no transcript. Please transcribe first.")
    
    # Check if emails already generated (return cached if available)
    if session.generated_emails:
        logger.info(f"Returning cached emails for session {session_id}")
        return session.generated_emails
    
    # Get transcript and summary data
    transcript = session.transcript_simple or ""
    if not transcript and session.transcript:
        try:
            trans_data = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
            if isinstance(trans_data, dict) and "segments" in trans_data:
                transcript = " ".join([s.get("text", "") for s in trans_data["segments"]])
        except:
            transcript = str(session.transcript)
    
    # Get summary data
    summary_data = session.final_summary or {}
    if not summary_data and session.summary:
        try:
            summary_data = json.loads(session.summary) if isinstance(session.summary, str) else session.summary
        except:
            summary_data = {}
    
    # Generate emails using AI
    try:
        emails = await generate_contextual_emails(
            session_title=session.title or session.name or "Meeting",
            transcript=transcript,
            summary_data=summary_data,
            session_date=session.created_at
        )
        
        # Save generated emails to database
        session.generated_emails = emails
        session.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Generated {len(emails)} emails for session {session_id}")
        return emails
        
    except Exception as e:
        logger.error(f"Failed to generate emails: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate emails: {str(e)}")

async def generate_contextual_emails(
    session_title: str,
    transcript: str,
    summary_data: Dict,
    session_date: datetime
) -> List[Dict]:
    """Generate contextual emails using AI"""
    
    # Use the configured AI backend
    from config.dual_ai_backends import get_final_summary_backend
    import aiohttp
    
    emails = []
    
    # Get AI backend for email generation (use Granite for quality)
    _, backend = get_final_summary_backend()
    
    # Extract key information from summary
    executive_summary = summary_data.get("executive", "")
    bullets = summary_data.get("bullets", [])
    actions = summary_data.get("actions", [])
    decisions = summary_data.get("decisions", [])
    
    # Format date
    meeting_date = session_date.strftime("%B %d, %Y") if session_date else "today"
    
    # Generate Follow-up Email
    try:
        follow_up_prompt = f"""Generate a professional follow-up email for this meeting.

Meeting: {session_title}
Date: {meeting_date}
Summary: {executive_summary}
Key Points: {', '.join(bullets[:3]) if bullets else 'Discussion points covered'}

Create a follow-up email that:
1. Thanks participants
2. Summarizes key discussion points
3. Lists next steps
4. Ends with a call to action

Format as JSON:
{{
  "subject": "Follow-up email subject",
  "body": "Complete email body with proper formatting"
}}"""

        response = await call_ai_backend(backend["url"], follow_up_prompt)
        if response:
            follow_up_email = {
                "subject": response.get("subject", f"Follow-up: {session_title}"),
                "to": "participants@company.com",
                "cc": "",
                "body": response.get("body", generate_fallback_followup(session_title, meeting_date, executive_summary, bullets)),
                "attachments": ["meeting_summary.pdf", "transcript.txt"],
                "type": "follow-up"
            }
            emails.append(follow_up_email)
    except Exception as e:
        logger.error(f"Failed to generate follow-up email: {e}")
        # Add fallback email
        emails.append(generate_fallback_followup_dict(session_title, meeting_date, executive_summary, bullets))
    
    # Generate Action Items Email if there are action items
    if actions:
        try:
            actions_prompt = f"""Generate an action items email for this meeting.

Meeting: {session_title}
Date: {meeting_date}
Action Items: {json.dumps(actions)}

Create an email that:
1. Lists all action items clearly
2. Includes owners and priorities
3. Sets expectations for completion
4. Requests status updates

Format as JSON:
{{
  "subject": "Action items email subject",
  "body": "Complete email body with formatted action items"
}}"""

            response = await call_ai_backend(backend["url"], actions_prompt)
            if response:
                actions_email = {
                    "subject": response.get("subject", f"Action Items: {session_title}"),
                    "to": "team@company.com",
                    "cc": "manager@company.com",
                    "body": response.get("body", generate_fallback_actions(session_title, meeting_date, actions)),
                    "attachments": ["action_items.xlsx"],
                    "type": "action-items"
                }
                emails.append(actions_email)
        except Exception as e:
            logger.error(f"Failed to generate actions email: {e}")
            if actions:  # Only add if there are actual action items
                emails.append(generate_fallback_actions_dict(session_title, meeting_date, actions))
    
    # Generate Executive Summary Email if there are significant decisions
    if decisions or (executive_summary and len(executive_summary) > 100):
        try:
            exec_prompt = f"""Generate an executive summary email for leadership.

Meeting: {session_title}
Date: {meeting_date}
Summary: {executive_summary}
Decisions: {', '.join(decisions) if decisions else 'Key decisions made'}

Create a brief executive email that:
1. Provides high-level overview
2. Highlights key decisions
3. Notes any escalations needed
4. Is concise (under 200 words)

Format as JSON:
{{
  "subject": "Executive summary subject",
  "body": "Brief executive summary"
}}"""

            response = await call_ai_backend(backend["url"], exec_prompt)
            if response:
                exec_email = {
                    "subject": response.get("subject", f"Executive Summary: {session_title}"),
                    "to": "leadership@company.com",
                    "cc": "",
                    "body": response.get("body", generate_fallback_executive(session_title, meeting_date, executive_summary, decisions)),
                    "attachments": ["executive_summary.pdf"],
                    "type": "executive-summary"
                }
                emails.append(exec_email)
        except Exception as e:
            logger.error(f"Failed to generate executive email: {e}")
    
    # If no emails generated, create at least one follow-up email
    if not emails:
        emails.append(generate_fallback_followup_dict(session_title, meeting_date, executive_summary, bullets))
    
    return emails

async def call_ai_backend(base_url: str, prompt: str) -> Dict:
    """Call AI backend to generate email content"""
    import aiohttp
    import json
    
    try:
        url = f"{base_url}/completion"
        payload = {
            "prompt": prompt,
            "n_predict": 500,
            "temperature": 0.7,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result.get("content", "")
                    
                    # Try to parse JSON response
                    try:
                        return json.loads(content)
                    except:
                        # If not valid JSON, try to extract subject and body
                        lines = content.split("\n")
                        subject = lines[0] if lines else "Meeting Follow-up"
                        body = "\n".join(lines[1:]) if len(lines) > 1 else content
                        return {"subject": subject, "body": body}
                        
    except Exception as e:
        logger.error(f"AI backend call failed: {e}")
        return None

def generate_fallback_followup(title: str, date: str, summary: str, bullets: List) -> str:
    """Generate fallback follow-up email body"""
    body = f"""Dear Team,

Thank you for participating in today's meeting: {title}.

Meeting Summary:
{summary if summary else 'We had a productive discussion covering key topics.'}

Key Discussion Points:
"""
    
    if bullets:
        for bullet in bullets[:5]:
            body += f"• {bullet}\n"
    else:
        body += "• Topics discussed as per agenda\n"
    
    body += """
Next Steps:
Please review the attached meeting summary and transcript for complete details. If you have any questions or need clarification on any points, please don't hesitate to reach out.

Best regards,
Meeting Ops Team

---
This email was automatically generated from the meeting held on """ + date
    
    return body

def generate_fallback_followup_dict(title: str, date: str, summary: str, bullets: List) -> Dict:
    """Generate fallback follow-up email dictionary"""
    return {
        "subject": f"Follow-up: {title}",
        "to": "participants@company.com",
        "cc": "",
        "body": generate_fallback_followup(title, date, summary, bullets),
        "attachments": ["meeting_summary.pdf", "transcript.txt"],
        "type": "follow-up"
    }

def generate_fallback_actions(title: str, date: str, actions: List) -> str:
    """Generate fallback action items email body"""
    body = f"""Team,

Following our meeting "{title}" on {date}, please find below the action items assigned:

ACTION ITEMS:
"""
    
    for i, action in enumerate(actions, 1):
        if isinstance(action, dict):
            task = action.get("action", "Task")
            owner = action.get("owner", "TBD")
            priority = action.get("priority", "Normal")
            body += f"""
{i}. {task}
   Owner: {owner}
   Priority: {priority}
"""
        else:
            body += f"\n{i}. {action}\n"
    
    body += """
Please provide status updates on your assigned items by the end of the week.

If you have any questions about your action items or need additional resources, please let me know.

Thank you,
Meeting Ops Team"""
    
    return body

def generate_fallback_actions_dict(title: str, date: str, actions: List) -> Dict:
    """Generate fallback action items email dictionary"""
    return {
        "subject": f"Action Items from {title}",
        "to": "team@company.com",
        "cc": "manager@company.com",
        "body": generate_fallback_actions(title, date, actions),
        "attachments": ["action_items.xlsx"],
        "type": "action-items"
    }

def generate_fallback_executive(title: str, date: str, summary: str, decisions: List) -> str:
    """Generate fallback executive summary email body"""
    body = f"""Executive Team,

Brief summary of {title} held on {date}:

OVERVIEW:
{summary if summary else 'Meeting conducted to discuss strategic priorities.'}

"""
    
    if decisions:
        body += "KEY DECISIONS:\n"
        for decision in decisions[:3]:
            body += f"• {decision}\n"
        body += "\n"
    
    body += """Full details available in the attached summary.

Regards,
Meeting Ops Team"""
    
    return body