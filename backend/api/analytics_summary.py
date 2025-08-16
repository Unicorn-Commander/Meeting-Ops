"""Analytics Summary API for dashboard"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, String
from datetime import datetime, timedelta
import logging

from database.database import get_db
from database.models import RecordingSession, Transcription

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

@router.get("/summary")
async def get_analytics_summary(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get analytics summary for dashboard"""
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get total sessions
        total_sessions = db.query(func.count(RecordingSession.id)).scalar() or 0
        
        # Get sessions in date range
        recent_sessions = db.query(RecordingSession).filter(
            RecordingSession.created_at >= start_date
        ).all()
        
        recent_count = len(recent_sessions)
        
        # Calculate total duration
        total_duration = sum(s.duration or 0 for s in recent_sessions)
        all_time_duration = db.query(func.sum(RecordingSession.duration)).scalar() or 0
        
        # Get speaker statistics
        session_ids = [str(s.id) for s in recent_sessions]
        transcriptions = db.query(Transcription).filter(
            Transcription.session_id.in_(session_ids)
        ).all()
        
        # Count unique speakers
        speakers = {}
        for trans in transcriptions:
            speaker = trans.speaker or "Unknown"
            if speaker not in speakers:
                speakers[speaker] = {
                    "name": speaker,
                    "segments": 0,
                    "total_time": 0
                }
            speakers[speaker]["segments"] += 1
            if hasattr(trans, 'start_time') and hasattr(trans, 'end_time') and trans.start_time and trans.end_time:
                speakers[speaker]["total_time"] += (trans.end_time - trans.start_time)
        
        # Get session status distribution
        status_counts = {}
        for session in recent_sessions:
            status = session.status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate averages
        avg_duration = total_duration / recent_count if recent_count > 0 else 0
        
        # Get daily session counts for chart
        daily_counts = {}
        for session in recent_sessions:
            date_key = session.created_at.strftime("%Y-%m-%d")
            daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
        
        # Format daily data for chart
        daily_data = []
        current_date = start_date
        while current_date <= end_date:
            date_key = current_date.strftime("%Y-%m-%d")
            daily_data.append({
                "date": date_key,
                "sessions": daily_counts.get(date_key, 0)
            })
            current_date += timedelta(days=1)
        
        # Get top meeting types
        meeting_types = {}
        for session in recent_sessions:
            mtype = session.meeting_type or "General"
            meeting_types[mtype] = meeting_types.get(mtype, 0) + 1
        
        # Sort speakers by speaking time
        top_speakers = sorted(
            speakers.values(),
            key=lambda x: x["total_time"],
            reverse=True
        )[:5]
        
        return {
            "summary": {
                "total_sessions": total_sessions,
                "recent_sessions": recent_count,
                "total_duration_seconds": all_time_duration,
                "recent_duration_seconds": total_duration,
                "average_duration_seconds": avg_duration,
                "unique_speakers": len(speakers),
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": days
                }
            },
            "status_distribution": status_counts,
            "meeting_types": meeting_types,
            "top_speakers": top_speakers,
            "daily_sessions": daily_data,
            "recent_activity": [
                {
                    "id": s.session_id or str(s.id),
                    "name": s.name or s.title or f"Session {s.id}",
                    "date": s.created_at.isoformat(),
                    "duration": s.duration or 0,
                    "status": s.status
                }
                for s in recent_sessions[:10]  # Last 10 sessions
            ]
        }
        
    except Exception as e:
        logger.error(f"Error generating analytics summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/speaker-stats")
async def get_speaker_statistics(
    session_id: str = None,
    db: Session = Depends(get_db)
):
    """Get detailed speaker statistics"""
    try:
        query = db.query(Transcription)
        
        if session_id:
            # Get session by session_id
            session = db.query(RecordingSession).filter(
                RecordingSession.session_id == session_id
            ).first()
            if session:
                query = query.filter(Transcription.session_id == str(session.id))
        
        transcriptions = query.all()
        
        # Aggregate by speaker
        speakers = {}
        for trans in transcriptions:
            speaker = trans.speaker or trans.speaker_id or "Unknown"
            if speaker not in speakers:
                speakers[speaker] = {
                    "name": speaker,
                    "segments": 0,
                    "total_time": 0,
                    "words": 0,
                    "average_confidence": 0,
                    "confidence_sum": 0
                }
            
            speakers[speaker]["segments"] += 1
            
            if trans.start_time and trans.end_time:
                speakers[speaker]["total_time"] += (trans.end_time - trans.start_time)
            
            if trans.text:
                speakers[speaker]["words"] += len(trans.text.split())
            
            if trans.confidence:
                speakers[speaker]["confidence_sum"] += trans.confidence
        
        # Calculate averages
        for speaker_data in speakers.values():
            if speaker_data["segments"] > 0:
                speaker_data["average_confidence"] = (
                    speaker_data["confidence_sum"] / speaker_data["segments"]
                )
            del speaker_data["confidence_sum"]  # Remove temporary field
            
            # Calculate speaking rate (words per minute)
            if speaker_data["total_time"] > 0:
                speaker_data["words_per_minute"] = (
                    speaker_data["words"] / (speaker_data["total_time"] / 60)
                )
            else:
                speaker_data["words_per_minute"] = 0
        
        # Sort by total speaking time
        sorted_speakers = sorted(
            speakers.values(),
            key=lambda x: x["total_time"],
            reverse=True
        )
        
        return {
            "total_speakers": len(speakers),
            "speakers": sorted_speakers,
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error getting speaker statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/word-frequency")
async def get_word_frequency(
    session_id: str = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get most frequent words from transcriptions"""
    try:
        import re
        from collections import Counter
        
        # Common words to exclude
        stop_words = {
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have',
            'i', 'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you',
            'do', 'at', 'this', 'but', 'his', 'by', 'from', 'is', 'was',
            'are', 'been', 'or', 'its', 'an', 'will', 'my', 'would', 'there',
            'their', 'so', 'up', 'if', 'about', 'who', 'get', 'which', 'me',
            'when', 'can', 'like', 'just', 'him', 'know', 'take', 'into',
            'year', 'your', 'some', 'could', 'them', 'see', 'other', 'than',
            'then', 'now', 'look', 'only', 'come', 'over', 'also', 'back'
        }
        
        query = db.query(Transcription)
        
        if session_id:
            session = db.query(RecordingSession).filter(
                RecordingSession.session_id == session_id
            ).first()
            if session:
                query = query.filter(Transcription.session_id == str(session.id))
        
        transcriptions = query.all()
        
        # Collect all words
        word_counter = Counter()
        
        for trans in transcriptions:
            if trans.text:
                # Extract words (alphanumeric only)
                words = re.findall(r'\b[a-zA-Z]+\b', trans.text.lower())
                # Filter stop words and short words
                meaningful_words = [
                    w for w in words 
                    if w not in stop_words and len(w) > 2
                ]
                word_counter.update(meaningful_words)
        
        # Get top words
        top_words = [
            {"word": word, "count": count}
            for word, count in word_counter.most_common(limit)
        ]
        
        return {
            "total_unique_words": len(word_counter),
            "top_words": top_words,
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error getting word frequency: {e}")
        raise HTTPException(status_code=500, detail=str(e))