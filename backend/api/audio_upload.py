"""
Audio Upload API for existing sessions
Allows uploading audio files to sessions that don't have recordings
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import RecordingSession as DBRecordingSession
import os
import shutil
import uuid
from datetime import datetime, timezone
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simple/recording-sessions", tags=["audio-upload"])

# Maximum file size (500MB)
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB in bytes

@router.post("/{session_id}/upload-audio")
async def upload_audio(
    session_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload audio file to an existing session and trigger processing"""
    
    # Validate session exists
    session = db.query(DBRecordingSession).filter(
        DBRecordingSession.session_id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if session already has audio
    if session.audio_file and os.path.exists(session.audio_file):
        raise HTTPException(status_code=400, detail="Session already has audio file")
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")
    
    # Validate file size
    file_size = 0
    from services.working_audio_service import audio_service as _as
    audio_dir = _as.RECORDINGS_DIR
    os.makedirs(audio_dir, exist_ok=True)
    
    # Generate unique filename
    file_extension = os.path.splitext(file.filename)[1] or ".wav"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_filename = f"uploaded_{session_id}_{timestamp}{file_extension}"
    audio_path = os.path.normpath(os.path.join(audio_dir, audio_filename))
    
    try:
        # Save uploaded file
        with open(audio_path, "wb") as buffer:
            while chunk := await file.read(8192):  # Read in 8KB chunks
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    os.remove(audio_path)  # Clean up partial file
                    raise HTTPException(status_code=413, detail="File too large (max 500MB)")
                buffer.write(chunk)
        
        # Update session with audio file path
        session.audio_file = audio_path
        session.status = "processing"
        session.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info(f"Audio uploaded for session {session_id}: {audio_path}")
        logger.info(f"File size: {file_size / (1024*1024):.2f} MB")
        
        # Trigger background processing (transcription and summarization)
        background_tasks.add_task(
            process_uploaded_audio,
            session_id=session_id,
            audio_file=audio_path,
            db_session_id=session.id
        )
        
        return {
            "status": "success",
            "message": "Audio uploaded successfully, processing started",
            "session_id": session_id,
            "file_size": file_size,
            "audio_file": audio_path
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Clean up file on error
        if os.path.exists(audio_path):
            os.remove(audio_path)
        logger.error(f"Failed to upload audio: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload audio: {str(e)}")

async def process_uploaded_audio(session_id: str, audio_file: str, db_session_id: int):
    """Process uploaded audio file - transcribe and summarize"""
    from database.database import SessionLocal
    from services.real_whisper_service import real_whisper_service
    from services.unified_agent_service import unified_agent_service
    import json
    import time
    
    processing_start = time.time()
    db = SessionLocal()
    
    try:
        # Get session from database
        session = db.query(DBRecordingSession).filter(
            DBRecordingSession.id == db_session_id
        ).first()
        
        if not session:
            logger.error(f"Session {db_session_id} not found in database")
            return
        
        logger.info(f"Starting processing for uploaded audio: {audio_file}")
        
        # Step 1: Transcribe audio with NPU acceleration
        try:
            logger.info(f"Starting transcription for uploaded file: {audio_file}")
            
            transcription_result = await asyncio.wait_for(
                asyncio.to_thread(
                    real_whisper_service.transcribe_file,
                    audio_file,
                    diarize=True  # Enable speaker diarization
                ),
                timeout=600  # 10 minute timeout for large files
            )
            
            if transcription_result and "segments" in transcription_result:
                # Save full diarized transcript
                session.transcript_diarized = transcription_result
                
                # Save simple text transcript
                simple_text = " ".join([s.get("text", "") for s in transcription_result.get("segments", [])])
                session.transcript_simple = simple_text
                
                # Legacy field
                session.transcript = json.dumps(transcription_result)
                
                logger.info(f"Transcription complete: {len(transcription_result.get('segments', []))} segments")
            else:
                logger.warning("No transcription segments generated")
                session.transcript = json.dumps({"text": "Transcription failed", "segments": []})
                
        except asyncio.TimeoutError:
            logger.error(f"Transcription timed out for uploaded audio {session_id}")
            session.transcript = json.dumps({"text": "Transcription timed out", "segments": []})
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            session.transcript = json.dumps({"text": f"Transcription error: {str(e)}", "segments": []})
        
        # Step 2: Generate AI summary
        try:
            if transcription_result and "segments" in transcription_result:
                full_text = " ".join([s.get("text", "") for s in transcription_result["segments"]])
                
                if full_text.strip():
                    logger.info(f"Starting AI analysis for uploaded audio {session_id}")
                    
                    summary_result = await asyncio.wait_for(
                        unified_agent_service.analyze_meeting(
                            session_id=str(session.id),
                            transcript=full_text
                        ),
                        timeout=180  # 3 minute timeout
                    )
                    
                    if summary_result and summary_result.get("success"):
                        analysis = summary_result.get("analysis", {})
                        
                        # Save comprehensive final summary
                        final_summary = {
                            "executive": analysis.get("executive", ""),
                            "bullets": analysis.get("bullets", []),
                            "actions": analysis.get("actions", []),
                            "decisions": analysis.get("decisions", []),
                            "title": analysis.get("title", ""),
                            "generated_at": datetime.now(timezone.utc).isoformat()
                        }
                        session.final_summary = final_summary
                        session.summary = json.dumps(analysis)
                        session.ai_insights = analysis
                        
                        # Auto-generate title
                        if "title" in analysis and analysis["title"]:
                            session.title = analysis["title"][:200]
                            logger.info(f"Auto-generated title: {analysis['title']}")
                            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
        
        # Step 3: Update metadata
        processing_end = time.time()
        processing_duration = processing_end - processing_start
        
        # Calculate word count and duration
        word_count = 0
        if session.transcript_simple:
            word_count = len(session.transcript_simple.split())
        
        # Get audio duration (approximate from file size)
        import wave
        try:
            with wave.open(audio_file, 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                session.duration = duration
        except:
            # Fallback duration estimate
            file_size = os.path.getsize(audio_file)
            session.duration = file_size / (44100 * 2)  # Approximate for 44.1kHz 16-bit mono
        
        # Update metadata
        metadata = session.processing_metadata or {}
        metadata.update({
            "word_count": word_count,
            "upload_processed": True,
            "processing_time_ms": int(processing_duration * 1000),
            "transcription_model": "whisper-large-v3",
            "ai_model": "granite3.3:8b",
            "processing_completed_at": datetime.now(timezone.utc).isoformat()
        })
        session.processing_metadata = metadata
        
        # Mark as completed
        session.status = "completed"
        session.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        logger.info(f"✅ Successfully processed uploaded audio for session {session_id}")
        logger.info(f"   Processing time: {processing_duration:.1f}s")
        logger.info(f"   Word count: {word_count}")
        logger.info(f"   Duration: {session.duration:.1f}s")
        
    except Exception as e:
        logger.error(f"Critical error processing uploaded audio: {e}")
        try:
            session.status = "error"
            session.updated_at = datetime.now(timezone.utc)
            db.commit()
        except:
            pass
    finally:
        db.close()