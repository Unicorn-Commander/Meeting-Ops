"""
AI Chat API - Per-meeting AI chat using real LLM inference.
Loads session transcript as context and sends to Granite 3.3 2B via unified_llm_service.
Chat history stored in memory (dict keyed by session_id).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import json
import logging

from database.database import get_db
from database.models import RecordingSession as DBRecordingSession
from auth.dependencies import get_current_user
from auth.models import User
from services.unified_llm_service import llm_service

router = APIRouter(prefix="/api/ai-chat", tags=["AI Chat"])
logger = logging.getLogger(__name__)

# In-memory chat history keyed by session_id
_chat_history: Dict[str, List[Dict[str, Any]]] = {}


# Request/Response Models
class SendMessageRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = {}


class AIResponse(BaseModel):
    content: str
    sources: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = {}


def _get_transcript_text(session: DBRecordingSession) -> str:
    """Extract the best available transcript text from a recording session."""
    # Prefer simple transcript text
    if session.transcript_simple:
        return session.transcript_simple

    # Try diarized transcript
    if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
        segments = session.transcript_diarized.get("segments", [])
        if segments:
            lines = []
            for seg in segments:
                speaker = seg.get("speaker", "Speaker")
                text = seg.get("text", "")
                if text:
                    lines.append(f"{speaker}: {text}")
            return "\n".join(lines)

    # Try raw transcript field (may be JSON)
    if session.transcript:
        try:
            data = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
            if isinstance(data, dict):
                if "segments" in data:
                    texts = [s.get("text", "") for s in data["segments"] if s.get("text")]
                    return " ".join(texts)
                if "text" in data:
                    return data["text"]
            return str(data)
        except (json.JSONDecodeError, TypeError):
            return str(session.transcript)

    return ""


def _get_summary_text(session: DBRecordingSession) -> str:
    """Extract summary text if available."""
    if session.final_summary and isinstance(session.final_summary, dict):
        parts = []
        if session.final_summary.get("executive"):
            parts.append(f"Executive Summary: {session.final_summary['executive']}")
        if session.final_summary.get("bullets"):
            parts.append("Key Points: " + "; ".join(session.final_summary["bullets"]))
        if session.final_summary.get("decisions"):
            parts.append("Decisions: " + "; ".join(session.final_summary["decisions"]))
        return "\n".join(parts)

    if session.summary:
        try:
            data = json.loads(session.summary) if isinstance(session.summary, str) else session.summary
            if isinstance(data, dict):
                parts = []
                if data.get("executive_summary") or data.get("executive"):
                    parts.append(data.get("executive_summary") or data.get("executive", ""))
                return "\n".join(parts) if parts else str(data)
            return str(data)
        except (json.JSONDecodeError, TypeError):
            return str(session.summary)

    return ""


def _build_system_prompt(session: DBRecordingSession, transcript: str, summary: str) -> str:
    """Build the system prompt with meeting context."""
    meeting_name = session.title or session.name or "Untitled Meeting"
    duration_str = f"{int(session.duration // 60)}m {int(session.duration % 60)}s" if session.duration else "unknown"
    date_str = session.created_at.strftime("%Y-%m-%d %H:%M") if session.created_at else "unknown"

    prompt = f"""You are an AI assistant for Meeting-Ops, a meeting recording and transcription system. You are helping the user understand and analyze a specific meeting recording.

Meeting: {meeting_name}
Date: {date_str}
Duration: {duration_str}
"""

    if summary:
        prompt += f"\nMeeting Summary:\n{summary}\n"

    # Include transcript, truncated if too long (keep under ~3000 tokens worth)
    if transcript:
        max_chars = 8000
        if len(transcript) > max_chars:
            prompt += f"\nMeeting Transcript (truncated to first {max_chars} characters):\n{transcript[:max_chars]}...\n"
        else:
            prompt += f"\nMeeting Transcript:\n{transcript}\n"

    prompt += """
Answer the user's questions about this meeting based on the transcript and summary above. Be concise, specific, and helpful. If the transcript doesn't contain enough information to answer a question, say so honestly. Do not make up information that isn't in the transcript."""

    return prompt


# API Endpoints

@router.post("/sessions/{session_id}/messages", response_model=AIResponse)
async def send_chat_message(
    session_id: str,
    request: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send a message about a meeting and get an AI response using the real LLM."""

    # Look up the recording session
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()

    if not session:
        # Try by integer id
        try:
            session = db.query(DBRecordingSession).filter(
                DBRecordingSession.id == int(session_id)
            ).first()
        except (ValueError, TypeError):
            pass

    if not session:
        raise HTTPException(status_code=404, detail="Recording session not found")

    # Load transcript and summary
    transcript = _get_transcript_text(session)
    summary = _get_summary_text(session)

    if not transcript and not summary:
        return AIResponse(
            content="This meeting doesn't have a transcript or summary yet. Please ensure the recording has been processed before asking questions about it.",
            sources=[],
            metadata={"has_transcript": False, "has_summary": False}
        )

    # Build system prompt with meeting context
    system_prompt = _build_system_prompt(session, transcript, summary)

    # Get or create chat history for this session
    if session_id not in _chat_history:
        _chat_history[session_id] = []

    # Add user message to history
    _chat_history[session_id].append({
        "role": "user",
        "content": request.message,
        "timestamp": datetime.utcnow().isoformat()
    })

    # Build user prompt including recent chat history for context
    history = _chat_history[session_id]
    if len(history) > 1:
        # Include last few exchanges for conversational context
        recent = history[-6:]  # Last 3 exchanges (user + assistant)
        history_text = "\n".join([
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in recent[:-1]  # Exclude current message
        ])
        user_prompt = f"Previous conversation:\n{history_text}\n\nUser: {request.message}"
    else:
        user_prompt = request.message

    # Call the LLM
    try:
        import time
        start_time = time.time()

        response_text = llm_service._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=800,
            temperature=0.7
        )

        inference_time = time.time() - start_time

        if not response_text:
            response_text = "I'm sorry, the AI model is currently unavailable. Please ensure the LLM service is running and try again."

        # Store assistant response in history
        _chat_history[session_id].append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Trim history if it gets too long (keep last 20 messages)
        if len(_chat_history[session_id]) > 20:
            _chat_history[session_id] = _chat_history[session_id][-20:]

        logger.info(f"AI chat response generated for session {session_id} in {inference_time:.2f}s")

        return AIResponse(
            content=response_text,
            sources=[{
                "type": "meeting",
                "id": session_id,
                "title": session.title or session.name or "Meeting",
                "has_transcript": bool(transcript),
                "has_summary": bool(summary)
            }],
            metadata={
                "response_time_ms": int(inference_time * 1000),
                "transcript_length": len(transcript),
                "history_length": len(_chat_history[session_id])
            }
        )

    except Exception as e:
        logger.error(f"Error generating AI response: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate AI response: {str(e)}")


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get chat history for a specific recording session."""
    history = _chat_history.get(session_id, [])

    messages = []
    for i, msg in enumerate(history):
        messages.append(ChatMessage(
            id=f"msg-{session_id}-{i}",
            role=msg["role"],
            content=msg["content"],
            timestamp=datetime.fromisoformat(msg["timestamp"]) if isinstance(msg["timestamp"], str) else msg["timestamp"],
            metadata=msg.get("metadata", {})
        ))

    return messages


@router.delete("/sessions/{session_id}/messages")
async def clear_chat_history(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Clear chat history for a specific recording session."""
    if session_id in _chat_history:
        del _chat_history[session_id]

    return {"message": "Chat history cleared"}
