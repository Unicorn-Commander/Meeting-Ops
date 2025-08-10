"""
AI-powered meeting insights API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging
import json

from database.database import get_db
from database.models import RecordingSession, Transcription
from auth.dependencies import get_current_user
from auth.models import User
from services.gemma_custom_service import GemmaCustomService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/simple/recording-sessions", tags=["insights"])

# Initialize Gemma service
gemma_service = GemmaCustomService()

class ActionItem(BaseModel):
    id: str
    text: str
    assignee: Optional[str] = None
    priority: str = "medium"
    dueDate: Optional[str] = None
    completed: bool = False
    category: str = "general"

class KeywordTrend(BaseModel):
    word: str
    frequency: int
    trend: str = "stable"
    category: str = "topic"

class SpeakerInsight(BaseModel):
    speaker: str
    talkTime: int
    wordCount: int
    sentiment: str = "neutral"
    engagement: float = 0.5
    keyTopics: List[str] = []

class MeetingInsightsResponse(BaseModel):
    summary: str
    keywords: List[KeywordTrend]
    action_items: List[ActionItem]
    speaker_insights: List[SpeakerInsight]
    sentiment: Dict[str, float]
    duration: int
    topics: List[str]
    key_decisions: List[str]
    follow_ups: List[str]

@router.get("/{session_id}/insights", response_model=MeetingInsightsResponse)
async def get_meeting_insights(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get AI-generated insights for a recording session"""
    try:
        # Get the session
        session = db.query(RecordingSession).filter(
            RecordingSession.id == session_id,
            RecordingSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get all transcriptions for the session
        transcriptions = db.query(Transcription).filter(
            Transcription.session_id == session_id
        ).order_by(Transcription.start_time).all()
        
        if not transcriptions:
            # Return default insights if no transcription yet
            return {
                "summary": "No transcription available yet. Insights will be generated once the recording has content.",
                "keywords": [],
                "action_items": [],
                "speaker_insights": [],
                "sentiment": {"positive": 0, "neutral": 100, "negative": 0},
                "duration": session.duration or 0,
                "topics": [],
                "key_decisions": [],
                "follow_ups": []
            }
        
        # Build full transcript text
        full_transcript = "\n".join([
            f"[{t.speaker_id or 'Unknown'}]: {t.text}"
            for t in transcriptions if t.text
        ])
        
        # Generate insights using Gemma
        insights = await generate_ai_insights(full_transcript, transcriptions, session)
        
        return insights
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get insights for session {session_id}: {e}")
        # Return basic insights on error
        return {
            "summary": "Unable to generate AI insights at this time.",
            "keywords": [],
            "action_items": [],
            "speaker_insights": [],
            "sentiment": {"positive": 0, "neutral": 100, "negative": 0},
            "duration": 0,
            "topics": [],
            "key_decisions": [],
            "follow_ups": []
        }

async def generate_ai_insights(
    transcript: str,
    transcriptions: List[Transcription],
    session: RecordingSession
) -> MeetingInsightsResponse:
    """Generate AI insights from transcript using Gemma"""
    
    # Calculate basic statistics
    duration = session.duration or 0
    
    # Extract speaker statistics
    speaker_stats = {}
    for t in transcriptions:
        speaker = t.speaker_id or "Unknown"
        if speaker not in speaker_stats:
            speaker_stats[speaker] = {
                "time": 0,
                "words": 0,
                "segments": []
            }
        
        # Calculate speaking time
        if t.end_time and t.start_time:
            speaker_stats[speaker]["time"] += (t.end_time - t.start_time)
        
        # Count words
        if t.text:
            speaker_stats[speaker]["words"] += len(t.text.split())
            speaker_stats[speaker]["segments"].append(t.text)
    
    # Generate summary using Gemma
    try:
        summary_prompt = f"""
        Analyze this meeting transcript and provide a concise summary (2-3 sentences):
        
        {transcript[:3000]}  # Limit to first 3000 chars for performance
        
        Focus on key points, decisions, and outcomes.
        """
        
        summary = await gemma_service.generate_summary(
            transcript=transcript[:3000],
            prompt=summary_prompt,
            max_length=200
        )
    except Exception as e:
        logger.warning(f"Failed to generate AI summary: {e}")
        summary = "Meeting discussion covered multiple topics. AI summary generation in progress."
    
    # Extract action items using Gemma
    try:
        action_prompt = f"""
        Extract action items from this meeting transcript.
        Format each as: "Action: [description] (Priority: high/medium/low)"
        
        {transcript[:3000]}
        """
        
        action_response = await gemma_service.generate_summary(
            transcript=transcript[:3000],
            prompt=action_prompt,
            max_length=500
        )
        
        # Parse action items from response
        action_items = []
        for line in action_response.split('\n'):
            if 'Action:' in line:
                text = line.split('Action:')[1].split('(')[0].strip()
                priority = 'medium'
                if 'high' in line.lower():
                    priority = 'high'
                elif 'low' in line.lower():
                    priority = 'low'
                
                action_items.append({
                    "id": f"action_{len(action_items) + 1}",
                    "text": text,
                    "priority": priority,
                    "completed": False,
                    "category": "meeting"
                })
    except Exception as e:
        logger.warning(f"Failed to extract action items: {e}")
        action_items = []
    
    # Extract keywords (simple frequency analysis)
    word_freq = {}
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                   'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
                   'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                   'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
                   'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who',
                   'when', 'where', 'why', 'how', 'not', 'no', 'yes', 'so', 'okay', 'um', 'uh'}
    
    for t in transcriptions:
        if t.text:
            words = t.text.lower().split()
            for word in words:
                # Clean word and filter
                word = word.strip('.,!?;:"')
                if len(word) > 3 and word not in common_words:
                    word_freq[word] = word_freq.get(word, 0) + 1
    
    # Get top keywords
    keywords = []
    for word, freq in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:15]:
        category = 'topic'
        if word in ['urgent', 'important', 'critical', 'priority']:
            category = 'action'
        elif word in ['happy', 'concerned', 'worried', 'excited']:
            category = 'sentiment'
        elif word in ['code', 'api', 'database', 'system', 'server']:
            category = 'technical'
        
        keywords.append({
            "word": word,
            "frequency": freq,
            "trend": "stable",
            "category": category
        })
    
    # Build speaker insights
    speaker_insights = []
    for speaker, stats in speaker_stats.items():
        # Simple sentiment analysis (can be enhanced with AI)
        sentiment = "neutral"
        positive_words = sum(1 for seg in stats["segments"] for word in ['good', 'great', 'excellent', 'happy', 'success'] if word in seg.lower())
        negative_words = sum(1 for seg in stats["segments"] for word in ['problem', 'issue', 'concern', 'bad', 'failure'] if word in seg.lower())
        
        if positive_words > negative_words * 1.5:
            sentiment = "positive"
        elif negative_words > positive_words * 1.5:
            sentiment = "negative"
        
        # Extract key topics for speaker
        speaker_topics = []
        speaker_text = " ".join(stats["segments"])
        for keyword in keywords[:5]:
            if keyword["word"] in speaker_text.lower():
                speaker_topics.append(keyword["word"])
        
        speaker_insights.append({
            "speaker": speaker,
            "talkTime": stats["time"],
            "wordCount": stats["words"],
            "sentiment": sentiment,
            "engagement": min(1.0, stats["words"] / 1000),  # Simple engagement metric
            "keyTopics": speaker_topics[:3]
        })
    
    # Calculate overall sentiment
    total_segments = len(transcriptions)
    positive_count = sum(1 for t in transcriptions if any(word in (t.text or '').lower() for word in ['good', 'great', 'excellent', 'happy']))
    negative_count = sum(1 for t in transcriptions if any(word in (t.text or '').lower() for word in ['problem', 'issue', 'concern', 'bad']))
    neutral_count = total_segments - positive_count - negative_count
    
    sentiment_dist = {
        "positive": (positive_count * 100 / total_segments) if total_segments > 0 else 0,
        "neutral": (neutral_count * 100 / total_segments) if total_segments > 0 else 100,
        "negative": (negative_count * 100 / total_segments) if total_segments > 0 else 0
    }
    
    # Extract topics (top keyword categories)
    topics = list(set([k["word"] for k in keywords[:10]]))
    
    # Extract key decisions (using AI if available)
    key_decisions = []
    follow_ups = []
    
    try:
        decision_prompt = f"""
        Extract key decisions made in this meeting. List only the decisions, one per line:
        
        {transcript[:2000]}
        """
        
        decision_response = await gemma_service.generate_summary(
            transcript=transcript[:2000],
            prompt=decision_prompt,
            max_length=300
        )
        
        for line in decision_response.split('\n'):
            if line.strip() and len(line.strip()) > 10:
                if 'follow' in line.lower() or 'next' in line.lower():
                    follow_ups.append(line.strip())
                else:
                    key_decisions.append(line.strip())
    except Exception as e:
        logger.warning(f"Failed to extract decisions: {e}")
    
    return {
        "summary": summary,
        "keywords": keywords,
        "action_items": action_items,
        "speaker_insights": speaker_insights,
        "sentiment": sentiment_dist,
        "duration": duration,
        "topics": topics[:5],
        "key_decisions": key_decisions[:5],
        "follow_ups": follow_ups[:5]
    }

@router.post("/{session_id}/insights/regenerate")
async def regenerate_insights(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Force regeneration of AI insights for a session"""
    # This would clear any cached insights and regenerate
    return await get_meeting_insights(session_id, db, current_user)