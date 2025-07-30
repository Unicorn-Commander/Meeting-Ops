from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import os
import json
import logging

from database.models import RecordingSession as SessionModel, Transcription, Speaker
from database.database import get_db

logger = logging.getLogger(__name__)

class SessionManager:
    """Manages meeting sessions, transcriptions, and storage"""
    
    def __init__(self):
        self.active_sessions: Dict[str, SessionModel] = {}
        self.storage_path = "./recordings"
        os.makedirs(self.storage_path, exist_ok=True)
    
    def create_session(self, name: str, description: str = None, meeting_type: str = None) -> SessionModel:
        """Create a new recording session"""
        db = next(get_db())
        try:
            session_id = f"session_{int(datetime.now().timestamp())}_{str(uuid.uuid4())[:8]}"
            
            # Store description and meeting_type in extra_data JSON field
            extra_data = {}
            if description:
                extra_data['description'] = description
            if meeting_type:
                extra_data['meeting_type'] = meeting_type
            
            session = SessionModel(
                session_id=session_id,
                name=name,
                extra_data=extra_data,
                status="active"
            )
            
            db.add(session)
            db.commit()
            db.refresh(session)
            
            self.active_sessions[session_id] = session
            
            print(f"🎙️ Created new session: {session_id} - {name}")
            return session
        finally:
            db.close()
    
    def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Get session by ID"""
        db = next(get_db())
        try:
            return db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
        finally:
            db.close()
    
    def update_session_status(self, session_id: str, status: str) -> Optional[SessionModel]:
        """Update session status (active, paused, completed, failed)"""
        db = next(get_db())
        try:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if session:
                session.status = status
                if status == "completed":
                    # Calculate duration from created_at to now
                    end_time = datetime.utcnow()
                    session.duration = (end_time - session.created_at).total_seconds()
                    # Remove from active sessions
                    self.active_sessions.pop(session_id, None)
                
                db.commit()
                db.refresh(session)
                print(f"📝 Updated session {session_id} status to: {status}")
                return session
        finally:
            db.close()
    
    def add_transcription(self, session_id: str, text: str, confidence: float = 0.0, 
                         processing_time_ms: float = 0.0, npu_accelerated: bool = False,
                         speaker_id: str = None, speaker_confidence: float = 0.0,
                         start_time_seconds: float = 0.0, end_time_seconds: float = 0.0) -> Optional[Transcription]:
        """Add a transcription to a session"""
        db = next(get_db())
        try:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if not session:
                print(f"❌ Session {session_id} not found")
                return None
            
            transcription = Transcription(
                session_id=session.id,
                text=text,
                confidence=confidence,
                timestamp=datetime.utcnow(),
                start_time_seconds=start_time_seconds,
                end_time_seconds=end_time_seconds,
                duration_seconds=end_time_seconds - start_time_seconds,
                processing_time_ms=processing_time_ms,
                npu_accelerated=npu_accelerated,
                speaker_id=speaker_id,
                speaker_confidence=speaker_confidence
            )
            
            db.add(transcription)
            
            # Update session transcription count
            session.total_transcriptions += 1
            if npu_accelerated:
                session.npu_accelerated = True
            
            db.commit()
            db.refresh(transcription)
            
            # Index transcription in vector search if available
            try:
                from services.vector_search import get_vector_search_service
                vector_service = get_vector_search_service()
                
                # Generate unique segment ID
                segment_id = f"{session_id}_{transcription.id}"
                
                # Index the segment
                vector_service.index_transcription_segment(
                    segment_id=segment_id,
                    text=text,
                    session_id=session_id,
                    speaker=speaker_id,
                    timestamp=int(datetime.utcnow().timestamp()),
                    metadata={
                        "transcription_id": transcription.id,
                        "confidence": confidence,
                        "start_time": start_time_seconds,
                        "end_time": end_time_seconds,
                        "npu_accelerated": npu_accelerated
                    }
                )
                logger.info(f"Indexed transcription {transcription.id} in vector search")
            except Exception as e:
                logger.warning(f"Failed to index transcription in vector search: {e}")
                # Don't fail the transcription if vector indexing fails
            
            # Add or update speaker if provided (after committing transcription)
            if speaker_id:
                # Use a new database session for speaker update
                speaker_db = next(get_db())
                try:
                    self.add_speaker(
                        session_id=session_id,
                        speaker_id=speaker_id,
                        display_name=speaker_id,  # Use speaker_id as default display name
                        total_speaking_time=end_time_seconds - start_time_seconds,
                        total_segments=1,
                        first_appearance=start_time_seconds,
                        last_appearance=end_time_seconds,
                        confidence=speaker_confidence
                    )
                finally:
                    speaker_db.close()
            
            print(f"📝 Added transcription to session {session_id}: {text[:50]}...")
            return transcription
        finally:
            db.close()
    
    def add_speaker(self, session_id: str, speaker_id: str, display_name: str = None,
                   total_speaking_time: float = 0.0, total_segments: int = 0,
                   first_appearance: float = 0.0, last_appearance: float = 0.0,
                   confidence: float = 0.0) -> Optional[Speaker]:
        """Add or update speaker information for a session"""
        db = next(get_db())
        try:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if not session:
                return None
            
            # Check if speaker already exists
            speaker = db.query(Speaker).filter(
                Speaker.session_id == session.id,
                Speaker.speaker_id == speaker_id
            ).first()
            
            if speaker:
                # Update existing speaker
                speaker.total_speaking_time += total_speaking_time
                speaker.total_segments += total_segments
                speaker.last_appearance = max(speaker.last_appearance, last_appearance)
                if display_name:
                    speaker.display_name = display_name
            else:
                # Create new speaker
                speaker = Speaker(
                    session_id=session.id,
                    speaker_id=speaker_id,
                    display_name=display_name or speaker_id,
                    total_speaking_time=total_speaking_time,
                    total_segments=total_segments,
                    first_appearance=first_appearance,
                    last_appearance=last_appearance,
                    confidence=confidence
                )
                db.add(speaker)
                
                # Update session speaker count
                session.total_speakers = db.query(Speaker).filter(Speaker.session_id == session.id).count() + 1
            
            db.commit()
            db.refresh(speaker)
            return speaker
        finally:
            db.close()
    
    def get_sessions(self, limit: int = 50, offset: int = 0, status: str = None) -> List[SessionModel]:
        """Get list of sessions with optional filtering"""
        db = next(get_db())
        try:
            query = db.query(SessionModel)
            if status:
                query = query.filter(SessionModel.status == status)
            
            return query.order_by(SessionModel.created_at.desc()).offset(offset).limit(limit).all()
        finally:
            db.close()
    
    def get_session_transcriptions(self, session_id: str) -> List[Transcription]:
        """Get all transcriptions for a session"""
        db = next(get_db())
        try:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if not session:
                return []
            
            return db.query(Transcription).filter(
                Transcription.session_id == session.id
            ).order_by(Transcription.timestamp.asc()).all()
        finally:
            db.close()
    
    def get_session_speakers(self, session_id: str) -> List[Speaker]:
        """Get all speakers for a session"""
        db = next(get_db())
        try:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if not session:
                return []
            
            return db.query(Speaker).filter(
                Speaker.session_id == session.id
            ).order_by(Speaker.total_speaking_time.desc()).all()
        finally:
            db.close()
    
    def export_session(self, session_id: str, format: str = "json") -> Optional[Dict[str, Any]]:
        """Export session data in specified format"""
        db = next(get_db())
        try:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if not session:
                return None
            
            transcriptions = self.get_session_transcriptions(session_id)
            speakers = self.get_session_speakers(session_id)
            
            export_data = {
                "session": session.to_dict(),
                "transcriptions": [t.to_dict() for t in transcriptions],
                "speakers": [s.to_dict() for s in speakers],
                "export_timestamp": datetime.utcnow().isoformat(),
                "format_version": "1.0"
            }
            
            if format == "txt":
                # Convert to text format
                text_content = f"Meeting: {session.name}\n"
                text_content += f"Date: {session.created_at}\n"
                text_content += f"Duration: {session.duration}s\n\n"
                
                for transcription in transcriptions:
                    speaker_info = f"[{transcription.speaker_id}] " if transcription.speaker_id else ""
                    text_content += f"{speaker_info}{transcription.text}\n"
                
                return {"content": text_content, "format": "text"}
            
            return export_data
        finally:
            db.close()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all related data"""
        db = next(get_db())
        try:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if not session:
                return False
            
            # Remove from active sessions
            self.active_sessions.pop(session_id, None)
            
            # Delete the session (cascades to transcriptions, speakers, etc.)
            db.delete(session)
            db.commit()
            
            print(f"🗑️ Deleted session: {session_id}")
            return True
        finally:
            db.close()
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get overall session statistics"""
        db = next(get_db())
        try:
            total_sessions = db.query(SessionModel).count()
            active_sessions = db.query(SessionModel).filter(SessionModel.status == "active").count()
            completed_sessions = db.query(SessionModel).filter(SessionModel.status == "completed").count()
            total_transcriptions = db.query(Transcription).count()
            
            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "completed_sessions": completed_sessions,
                "total_transcriptions": total_transcriptions,
                "storage_path": self.storage_path
            }
        finally:
            db.close()

# Global session manager instance
session_manager = SessionManager()