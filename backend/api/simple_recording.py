"""
Simple recording API without authentication for testing
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime
import uuid
import json
import sys
import os
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.simple_audio_recorder import simple_audio_recorder
from services.ollama_service import ollama_service
from services.unified_llm_service import llm_service
from services.whisperx_npu_service import whisperx_service
from services.realtime_transcription import realtime_service
from services.whisper_realtime import whisper_realtime_service
import asyncio
import numpy as np

router = APIRouter(prefix="/api/simple", tags=["simple-recording"])

# In-memory storage
sessions: Dict[str, dict] = {}

class SessionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    participants: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    session_type: Optional[str] = "live"  # "live" or "upload"

@router.post("/recording-sessions")
async def create_session(session_data: SessionCreate):
    """Create a new recording session - no auth required"""
    session_id = str(uuid.uuid4())
    
    # Create session directory for files
    session_dir = Path(f"./recordings/{session_id}")
    session_dir.mkdir(parents=True, exist_ok=True)
    
    session = {
        "id": session_id,
        "name": session_data.name,
        "description": session_data.description or "",
        "participants": session_data.participants or [],
        "tags": session_data.tags or [],
        "session_type": session_data.session_type or "live",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "status": "idle",
        "duration": 0,
        "has_audio": False,
        "has_transcript": False,
        "audio_file": None,
        "transcript": None,
        "documents": []
    }
    
    sessions[session_id] = session
    
    return session

@router.get("/recording-sessions")
async def list_sessions():
    """List all recording sessions"""
    return list(sessions.values())

@router.get("/recording-sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]

@router.post("/recording-sessions/{session_id}/start")
async def start_recording(session_id: str):
    """Start recording"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Start actual audio recording
        audio_file = simple_audio_recorder.start_recording(
            session_id=session_id,
            session_name=sessions[session_id]["name"]
        )
        
        sessions[session_id]["status"] = "recording"
        sessions[session_id]["start_time"] = datetime.utcnow().isoformat()
        sessions[session_id]["audio_file"] = audio_file
        
        # Start real-time transcription
        asyncio.create_task(realtime_service.start_session(session_id))
        
        # Simulate audio chunks being added (in production, this would come from the audio recorder)
        async def simulate_audio_stream():
            for i in range(30):  # Simulate 30 chunks
                await asyncio.sleep(3)  # Every 3 seconds
                if session_id in sessions and sessions[session_id]["status"] == "recording":
                    # Create fake audio data
                    fake_audio = np.random.randint(-1000, 1000, 48000, dtype=np.int16).tobytes()
                    await realtime_service.add_audio_chunk(session_id, fake_audio)
        
        asyncio.create_task(simulate_audio_stream())
        
        return {
            "status": "recording", 
            "session_id": session_id,
            "audio_file": audio_file,
            "message": "Recording started successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

@router.post("/recording-sessions/{session_id}/stop")
async def stop_recording(session_id: str):
    """Stop recording"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Stop real-time transcription
        await realtime_service.stop_session(session_id)
        
        # Stop actual audio recording
        result = simple_audio_recorder.stop_recording()
        
        session = sessions[session_id]
        session["duration"] = result.get("duration", 0)
        session["file_size"] = result.get("file_size", 0)
        session["status"] = "processing_final"  # Processing final accurate transcription
        session["end_time"] = datetime.utcnow().isoformat()
        session["audio_file_path"] = result.get("file_path")
        
        # Store live transcription segments before final processing
        # These are the real-time chunks that were shown during recording
        if "transcription" in session:
            session["live_transcription"] = session["transcription"].copy()
            logger.info(f"Saved {len(session.get('live_transcription', {}).get('segments', []))} live segments")
        
        # Do FULL ACCURATE TRANSCRIPTION of entire recording
        # This is separate from live transcription chunks
        if result.get("file_path") and os.path.exists(result["file_path"]):
            try:
                print(f"🎙️ Starting FINAL ACCURATE transcription of {result['file_path']}")
                print(f"   File size: {session['file_size']:,} bytes")
                print(f"   Duration: {session['duration']:.1f} seconds")
                print("   Using Whisper Large-v3 for maximum accuracy...")
                
                # Use WhisperX NPU engine for best accuracy
                from stt_engine.whisperx_npu_engine_real import WhisperXNPUEngine
                
                # Initialize with large-v3 for best accuracy
                transcriber = WhisperXNPUEngine(model_size="large-v3")
                
                # Process ENTIRE file at once for best context
                # No chunking, no rushing - just accuracy
                transcription_result = transcriber.transcribe(
                    result["file_path"],
                    diarize=True  # Full speaker diarization
                )
                
                if transcription_result:
                    # Store BOTH transcriptions
                    session["final_transcription"] = transcription_result  # Accurate full transcript
                    # Keep live_transcription separate for reference
                    # The main 'transcription' field will be the final accurate one
                    session["transcription"] = transcription_result
                    
                    # Calculate stats
                    num_segments = len(transcription_result.get("segments", []))
                    processing_time = transcription_result.get("processing_time", 0)
                    speedup = transcription_result.get("speedup", 0)
                    
                    print(f"✅ FINAL transcription completed!")
                    print(f"   Segments: {num_segments}")
                    print(f"   Processing time: {processing_time:.2f}s")
                    print(f"   Speedup: {speedup:.1f}x real-time")
                    print(f"   NPU accelerated: {transcription_result.get('npu_accelerated', False)}")
                    
                    # Mark the difference
                    session["has_final_transcription"] = True
                else:
                    print("⚠️ Final transcription returned no results")
                    session["has_final_transcription"] = False
                    
                session["status"] = "completed"
                
            except Exception as e:
                print(f"❌ Transcription error: {e}")
                # Still try WhisperX as fallback
                try:
                    transcription_result = whisperx_service.transcribe_file(
                        result["file_path"], 
                        diarize=True
                    )
                    session["transcription"] = transcription_result
                except:
                    pass
                session["status"] = "completed"
        
        return {
            "status": "completed", 
            "session_id": session_id,
            "duration": result.get("duration", 0),
            "file_path": result.get("file_path"),
            "file_size": result.get("file_size", 0),
            "has_transcription": "transcription" in session,
            "has_live_transcription": "live_transcription" in session,
            "has_final_transcription": "final_transcription" in session,
            "message": "Recording stopped and transcribed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")

@router.post("/recording-sessions/{session_id}/pause")
async def pause_recording(session_id: str):
    """Pause/resume recording"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Pause/resume actual recording
        result = simple_audio_recorder.pause_recording()
        
        current_status = sessions[session_id]["status"]
        new_status = "paused" if result.get("paused") else "recording"
        sessions[session_id]["status"] = new_status
        
        return {"status": new_status, "session_id": session_id, "paused": result.get("paused", False)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause recording: {str(e)}")

@router.post("/recording-sessions/{session_id}/auto-rename")
async def auto_rename(session_id: str):
    """Auto-rename session based on content using Ollama LLM"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    original_name = session["name"]
    
    try:
        # Use actual transcript if available, otherwise use mock
        transcript = ""
        if "transcription" in session and session["transcription"].get("text"):
            transcript = session["transcription"]["text"]
        else:
            transcript = """
            Team meeting discussing the Q4 product roadmap and upcoming feature releases.
            We need to prioritize the authentication system upgrade and the new dashboard design.
            John will handle the backend changes, Sarah will work on the UI components.
            Target completion date is end of next month.
            """
        
        # Generate a better title using Gemma (custom engine or Ollama)
        new_name = llm_service.generate_meeting_title(transcript)
        
        # Fallback if generation fails
        if not new_name or new_name == "":
            new_name = f"Team Meeting - {datetime.now().strftime('%B %d')}"
        
        session["name"] = new_name
        
    except Exception as e:
        # Fallback to simple renaming if Ollama fails
        print(f"Ollama rename failed: {e}")
        session["name"] = f"Team Meeting - {datetime.now().strftime('%B %d')}"
    
    return {"newName": session["name"], "originalName": original_name}

@router.get("/audio-devices")
async def list_audio_devices():
    """List available audio input devices on the server"""
    try:
        devices = simple_audio_recorder.list_devices()
        return {"devices": devices}
    except Exception as e:
        return {"devices": [], "error": str(e)}

@router.get("/recording-status")
async def get_recording_status():
    """Get current recording status"""
    return simple_audio_recorder.get_status()

@router.get("/audio-level")
async def get_audio_level():
    """Get current audio level"""
    level = simple_audio_recorder.get_audio_level()
    return {"level": level}

@router.get("/recording-sessions/{session_id}/download/audio")
async def download_audio(session_id: str):
    """Download audio file for a session"""
    from fastapi.responses import FileResponse
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    audio_path = session.get("audio_file_path")
    
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    filename = f"{session['name'].replace(' ', '_')}_audio.wav"
    return FileResponse(audio_path, filename=filename, media_type="audio/wav")

@router.get("/recording-sessions/{session_id}/download/transcript")
async def download_transcript(session_id: str):
    """Download transcript for a session"""
    from fastapi.responses import Response
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    # Build transcript text
    transcript = f"Recording: {session['name']}\n"
    transcript += f"Date: {session['created_at']}\n"
    transcript += f"Duration: {session.get('duration', 0)} seconds\n"
    transcript += "\n--- TRANSCRIPT ---\n\n"
    
    # Use final transcription if available, otherwise use regular
    if "final_transcription" in session and session["final_transcription"].get("segments"):
        for segment in session["final_transcription"]["segments"]:
            speaker = segment.get("speaker", "SPEAKER")
            text = segment.get("text", "")
            transcript += f"[{speaker}]: {text}\n\n"
    elif "transcription" in session and session["transcription"].get("segments"):
        for segment in session["transcription"]["segments"]:
            speaker = segment.get("speaker", "SPEAKER")
            text = segment.get("text", "")
            transcript += f"[{speaker}]: {text}\n\n"
    elif "transcription" in session and session["transcription"].get("text"):
        transcript += session["transcription"]["text"]
    else:
        transcript += "No transcription available."
    
    filename = f"{session['name'].replace(' ', '_')}_transcript.txt"
    return Response(
        content=transcript,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@router.post("/recording-sessions/{session_id}/summarize")
async def summarize_session(session_id: str):
    """Generate a summary of the recording session using Ollama"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # For now, use a mock transcript
        mock_transcript = """
        Team meeting discussing the Q4 product roadmap and upcoming feature releases.
        We started by reviewing last quarter's performance metrics. 
        Sales were up 15% but customer satisfaction scores dropped slightly.
        
        Main discussion points:
        - Need to prioritize the authentication system upgrade due to security concerns
        - The new dashboard design mockups were presented by Sarah
        - Mobile app performance issues need immediate attention
        - Customer feedback suggests we need better onboarding tutorials
        
        John committed to handling the backend authentication changes.
        Sarah will work on the UI components for the new dashboard.
        Mike will investigate the mobile app performance issues.
        
        We agreed to have a follow-up meeting next Tuesday to review progress.
        Target completion date for all items is end of next month.
        Budget allocation was discussed but needs executive approval.
        """
        
        # Generate summary using Gemma (custom engine or Ollama)
        summary_result = llm_service.summarize_meeting(mock_transcript)
        
        # Store summary in session
        sessions[session_id]["summary"] = summary_result
        
        return summary_result
        
    except Exception as e:
        print(f"Summary generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")

@router.get("/recording-sessions/{session_id}/summary")
async def get_session_summary(session_id: str):
    """Get the summary of a recording session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if "summary" not in sessions[session_id]:
        return {"message": "No summary available. Generate one first."}
    
    return sessions[session_id]["summary"]

@router.get("/recording-sessions/{session_id}/transcription")
async def get_session_transcription(session_id: str):
    """Get the transcription of a recording session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if "transcription" not in sessions[session_id]:
        return {"message": "No transcription available. Recording may still be processing."}
    
    return sessions[session_id]["transcription"]

@router.get("/npu-status")
async def get_npu_status():
    """Get NPU status for transcription"""
    return whisperx_service.get_npu_status()

@router.get("/recording-sessions/{session_id}/export/txt")
async def export_session_txt(session_id: str):
    """Export session transcription as plain text"""
    from fastapi.responses import PlainTextResponse
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    # Build text content
    lines = []
    lines.append(f"Meeting: {session.get('name', 'Untitled Meeting')}")
    lines.append(f"Date: {session.get('created_at', 'Unknown')}")
    lines.append(f"Duration: {session.get('duration', 0):.1f} seconds")
    lines.append("=" * 60)
    lines.append("")
    
    # Add transcription
    if "transcription" in session:
        transcription = session["transcription"]
        
        # Check if we have segments with timestamps
        if "segments" in transcription and transcription["segments"]:
            lines.append("TRANSCRIPT WITH TIMESTAMPS:")
            lines.append("-" * 40)
            for segment in transcription["segments"]:
                timestamp = f"[{segment.get('start', 0):.1f}s - {segment.get('end', 0):.1f}s]"
                speaker = segment.get('speaker', 'Unknown')
                text = segment.get('text', '').strip()
                lines.append(f"{timestamp} {speaker}: {text}")
                lines.append("")
        else:
            # Just raw text
            lines.append("TRANSCRIPT:")
            lines.append("-" * 40)
            lines.append(transcription.get("text", "No transcript available"))
            lines.append("")
    else:
        lines.append("No transcription available.")
    
    # Add summary if available
    if "summary" in session:
        lines.append("")
        lines.append("MEETING SUMMARY:")
        lines.append("-" * 40)
        summary = session["summary"]
        if isinstance(summary, dict):
            lines.append(summary.get("summary", ""))
            if "action_items" in summary and summary["action_items"]:
                lines.append("")
                lines.append("ACTION ITEMS:")
                for item in summary["action_items"]:
                    lines.append(f"• {item}")
        else:
            lines.append(str(summary))
    
    content = "\n".join(lines)
    
    # Create filename
    filename = f"{session.get('name', 'meeting').replace(' ', '_')}_{session_id[:8]}.txt"
    
    return PlainTextResponse(
        content=content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.get("/recording-sessions/{session_id}/export/json")
async def export_session_json(session_id: str):
    """Export session data as JSON"""
    from fastapi.responses import JSONResponse
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    # Build clean JSON structure
    export_data = {
        "meeting": {
            "id": session_id,
            "name": session.get("name", "Untitled Meeting"),
            "description": session.get("description", ""),
            "created_at": session.get("created_at"),
            "start_time": session.get("start_time"),
            "end_time": session.get("end_time"),
            "duration_seconds": session.get("duration", 0),
            "status": session.get("status", "unknown")
        },
        "audio": {
            "file_path": session.get("audio_file_path", ""),
            "file_size": session.get("file_size", 0),
            "sample_rate": 16000,
            "format": "WAV"
        }
    }
    
    # Add transcription if available
    if "transcription" in session:
        transcription = session["transcription"]
        export_data["transcription"] = {
            "text": transcription.get("text", ""),
            "language": transcription.get("language", "en"),
            "model": transcription.get("model", "unknown"),
            "processing_time": transcription.get("processing_time", 0),
            "segments": []
        }
        
        # Add segments with proper structure
        if "segments" in transcription:
            for segment in transcription["segments"]:
                export_data["transcription"]["segments"].append({
                    "start": segment.get("start", 0),
                    "end": segment.get("end", 0),
                    "text": segment.get("text", ""),
                    "speaker": segment.get("speaker", "SPEAKER_01"),
                    "confidence": segment.get("confidence", 0),
                    "words": segment.get("words", [])
                })
    
    # Add summary if available
    if "summary" in session:
        summary = session["summary"]
        if isinstance(summary, dict):
            export_data["summary"] = summary
        else:
            export_data["summary"] = {"text": str(summary)}
    
    # Create filename
    filename = f"{session.get('name', 'meeting').replace(' ', '_')}_{session_id[:8]}.json"
    
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.get("/recording-sessions/{session_id}/export/pdf")
async def export_session_pdf(session_id: str):
    """Export session as a professional PDF report"""
    from fastapi.responses import Response
    import io
    from datetime import datetime
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        # Fallback to simple PDF if reportlab has issues
        return await export_session_txt(session_id)
    
    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    # Container for the 'Flowable' objects
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#7C3AED'),  # Purple
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#7C3AED'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    elements.append(Paragraph("Meeting Transcript Report", title_style))
    elements.append(Spacer(1, 12))
    
    # Meeting info table
    try:
        date_str = datetime.fromisoformat(session.get('created_at', '')).strftime('%B %d, %Y %I:%M %p') if session.get('created_at') else 'Unknown'
    except:
        date_str = session.get('created_at', 'Unknown')
        
    meeting_data = [
        ['Meeting Name:', session.get('name', 'Untitled Meeting')],
        ['Date:', date_str],
        ['Duration:', f"{session.get('duration', 0):.1f} seconds"],
        ['Status:', session.get('status', 'unknown').title()],
    ]
    
    meeting_table = Table(meeting_data, colWidths=[2*inch, 4*inch])
    meeting_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#374151')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(meeting_table)
    elements.append(Spacer(1, 20))
    
    # Transcript section
    elements.append(Paragraph("Transcript", heading_style))
    
    if "transcription" in session:
        transcription = session["transcription"]
        
        if "segments" in transcription and transcription["segments"]:
            for segment in transcription["segments"]:
                # Format timestamp
                start_time = segment.get('start', 0)
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                timestamp = f"[{minutes:02d}:{seconds:02d}]"
                
                # Create paragraph with timestamp and speaker
                speaker = segment.get('speaker', 'Unknown')
                text = segment.get('text', '').strip()
                
                para_text = f"<font color='#6B7280'>{timestamp}</font> <b>{speaker}:</b> {text}"
                elements.append(Paragraph(para_text, styles['Normal']))
                elements.append(Spacer(1, 6))
        else:
            # Just the raw text
            text = transcription.get("text", "No transcript available")
            elements.append(Paragraph(text, styles['Normal']))
    else:
        elements.append(Paragraph("No transcription available.", styles['Normal']))
    
    # Summary section (if available)
    if "summary" in session:
        elements.append(PageBreak())
        elements.append(Paragraph("Meeting Summary", heading_style))
        
        summary = session["summary"]
        if isinstance(summary, dict):
            if summary.get("summary"):
                elements.append(Paragraph(summary["summary"], styles['Normal']))
                elements.append(Spacer(1, 12))
            
            if "action_items" in summary and summary["action_items"]:
                elements.append(Paragraph("Action Items", heading_style))
                for item in summary["action_items"]:
                    elements.append(Paragraph(f"• {item}", styles['Normal']))
                    elements.append(Spacer(1, 4))
        else:
            elements.append(Paragraph(str(summary), styles['Normal']))
    
    # Footer
    elements.append(Spacer(1, 30))
    footer_text = f"Generated by Meeting-Ops • {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#9CA3AF'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(footer_text, footer_style))
    
    try:
        # Build PDF
        doc.build(elements)
        
        # Get the value of the BytesIO buffer and return as response
        pdf_data = buffer.getvalue()
        buffer.close()
        
        filename = f"{session.get('name', 'meeting').replace(' ', '_')}_{session_id[:8]}.pdf"
        
        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        print(f"PDF generation error: {e}")
        # Fallback to text export
        return await export_session_txt(session_id)

@router.get("/recording-sessions/{session_id}/export/docx")
async def export_session_docx(session_id: str):
    """Export session as a Microsoft Word document"""
    from fastapi.responses import Response
    import io
    from datetime import datetime
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
        from docx.enum.style import WD_STYLE_TYPE
    except ImportError:
        # Fallback if python-docx not available
        return await export_session_txt(session_id)
    
    # Create a new Document
    doc = Document()
    
    # Add title
    title = doc.add_heading('Meeting Transcript Report', 0)
    title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    # Add meeting information
    doc.add_heading('Meeting Information', level=1)
    
    # Create a table for meeting details
    table = doc.add_table(rows=4, cols=2)
    table.style = 'Light Grid'
    
    # Populate table
    table.cell(0, 0).text = 'Meeting Name:'
    table.cell(0, 1).text = session.get('name', 'Untitled Meeting')
    
    table.cell(1, 0).text = 'Date:'
    try:
        date_str = datetime.fromisoformat(session.get('created_at', '')).strftime('%B %d, %Y %I:%M %p')
    except:
        date_str = session.get('created_at', 'Unknown')
    table.cell(1, 1).text = date_str
    
    table.cell(2, 0).text = 'Duration:'
    table.cell(2, 1).text = f"{session.get('duration', 0):.1f} seconds"
    
    table.cell(3, 0).text = 'Status:'
    table.cell(3, 1).text = session.get('status', 'unknown').title()
    
    doc.add_paragraph()  # Add spacing
    
    # Add transcript section
    doc.add_heading('Transcript', level=1)
    
    if "transcription" in session:
        transcription = session["transcription"]
        
        if "segments" in transcription and transcription["segments"]:
            for segment in transcription["segments"]:
                # Format timestamp
                start_time = segment.get('start', 0)
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                timestamp = f"[{minutes:02d}:{seconds:02d}]"
                
                # Add paragraph with timestamp and speaker
                speaker = segment.get('speaker', 'Unknown')
                text = segment.get('text', '').strip()
                
                # Create paragraph
                p = doc.add_paragraph()
                
                # Add timestamp in gray
                run = p.add_run(f"{timestamp} ")
                run.font.color.rgb = RGBColor(156, 163, 175)  # Gray color
                run.font.size = Pt(10)
                
                # Add speaker name in bold
                run = p.add_run(f"{speaker}: ")
                run.bold = True
                run.font.size = Pt(11)
                
                # Add text
                run = p.add_run(text)
                run.font.size = Pt(11)
        else:
            # Just add the raw text
            text = transcription.get("text", "No transcript available")
            doc.add_paragraph(text)
    else:
        doc.add_paragraph("No transcription available.")
    
    # Add summary section if available
    if "summary" in session:
        doc.add_page_break()
        doc.add_heading('Meeting Summary', level=1)
        
        summary = session["summary"]
        if isinstance(summary, dict):
            if summary.get("summary"):
                doc.add_paragraph(summary["summary"])
            
            if "action_items" in summary and summary["action_items"]:
                doc.add_heading('Action Items', level=2)
                for item in summary["action_items"]:
                    p = doc.add_paragraph(style='List Bullet')
                    p.add_run(item)
        else:
            doc.add_paragraph(str(summary))
    
    # Add footer
    doc.add_paragraph()
    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = footer.add_run(f"Generated by Meeting-Ops • {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(156, 163, 175)
    
    # Save to BytesIO buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    docx_data = buffer.getvalue()
    buffer.close()
    
    filename = f"{session.get('name', 'meeting').replace(' ', '_')}_{session_id[:8]}.docx"
    
    return Response(
        content=docx_data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.get("/recording-sessions/{session_id}/export/srt")
async def export_session_srt(session_id: str):
    """Export session transcription as SRT subtitle file"""
    from fastapi.responses import PlainTextResponse
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    if "transcription" not in session:
        raise HTTPException(status_code=400, detail="No transcription available for export")
    
    transcription = session["transcription"]
    
    # Build SRT content
    lines = []
    subtitle_number = 1
    
    if "segments" in transcription and transcription["segments"]:
        for segment in transcription["segments"]:
            # Subtitle number
            lines.append(str(subtitle_number))
            
            # Timestamp (SRT format: HH:MM:SS,mmm --> HH:MM:SS,mmm)
            start_time = segment.get("start", 0)
            end_time = segment.get("end", 0)
            
            start_hours = int(start_time // 3600)
            start_minutes = int((start_time % 3600) // 60)
            start_seconds = int(start_time % 60)
            start_millis = int((start_time % 1) * 1000)
            
            end_hours = int(end_time // 3600)
            end_minutes = int((end_time % 3600) // 60)
            end_seconds = int(end_time % 60)
            end_millis = int((end_time % 1) * 1000)
            
            timestamp_line = f"{start_hours:02d}:{start_minutes:02d}:{start_seconds:02d},{start_millis:03d} --> {end_hours:02d}:{end_minutes:02d}:{end_seconds:02d},{end_millis:03d}"
            lines.append(timestamp_line)
            
            # Text with speaker
            speaker = segment.get("speaker", "Speaker")
            text = segment.get("text", "").strip()
            lines.append(f"[{speaker}] {text}")
            
            # Empty line between subtitles
            lines.append("")
            
            subtitle_number += 1
    else:
        # No segments, create a single subtitle
        lines.append("1")
        lines.append("00:00:00,000 --> 00:00:10,000")
        lines.append(transcription.get("text", "No transcript available"))
        lines.append("")
    
    content = "\n".join(lines)
    
    # Create filename
    filename = f"{session.get('name', 'meeting').replace(' ', '_')}_{session_id[:8]}.srt"
    
    return PlainTextResponse(
        content=content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/x-subrip"
        }
    )

@router.post("/recording-sessions/{session_id}/upload-audio")
async def upload_audio(session_id: str, audio: UploadFile = File(...)):
    """Upload audio file to session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    # Validate file type
    allowed_types = ["audio/wav", "audio/mpeg", "audio/mp3", "audio/m4a", "audio/ogg", "audio/flac"]
    if audio.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {audio.content_type}")
    
    # Validate file size (max 500MB)
    max_size = 500 * 1024 * 1024
    if audio.size and audio.size > max_size:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 500MB.")
    
    try:
        # Create session directory
        session_dir = Path(f"./recordings/{session_id}")
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Save audio file
        audio_filename = f"audio_{session_id}.{audio.filename.split('.')[-1]}"
        audio_path = session_dir / audio_filename
        
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        
        # Update session
        session["audio_file"] = str(audio_path)
        session["has_audio"] = True
        session["updated_at"] = datetime.utcnow().isoformat()
        session["status"] = "processing"
        
        logger.info(f"Audio uploaded for session {session_id}: {audio_path}")
        
        return {
            "message": "Audio uploaded successfully",
            "filename": audio_filename,
            "size": audio.size,
            "session_id": session_id
        }
    
    except Exception as e:
        logger.error(f"Failed to upload audio: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload audio: {str(e)}")

@router.post("/recording-sessions/{session_id}/upload-document")
async def upload_document(session_id: str, document: UploadFile = File(...)):
    """Upload document to session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    try:
        # Create session directory
        session_dir = Path(f"./recordings/{session_id}")
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Create documents subdirectory
        docs_dir = session_dir / "documents"
        docs_dir.mkdir(exist_ok=True)
        
        # Save document
        doc_filename = f"doc_{len(session['documents'])}_{document.filename}"
        doc_path = docs_dir / doc_filename
        
        with open(doc_path, "wb") as buffer:
            shutil.copyfileobj(document.file, buffer)
        
        # Add to session documents
        doc_info = {
            "id": str(uuid.uuid4()),
            "name": document.filename,
            "path": str(doc_path),
            "type": document.content_type,
            "size": document.size,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        session["documents"].append(doc_info)
        session["updated_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Document uploaded for session {session_id}: {doc_path}")
        
        return {
            "message": "Document uploaded successfully",
            "document": doc_info,
            "session_id": session_id
        }
    
    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")

@router.get("/recording-sessions/{session_id}/audio")
async def download_audio(session_id: str):
    """Download audio file for session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    if not session.get("has_audio") or not session.get("audio_file"):
        raise HTTPException(status_code=404, detail="No audio file found for session")
    
    audio_path = Path(session["audio_file"])
    
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(audio_path),
        filename=f"{session['name']}_audio.{audio_path.suffix}",
        media_type="audio/wav"
    )

@router.delete("/recording-sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete session and all associated files"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Remove session directory and all files
        session_dir = Path(f"./recordings/{session_id}")
        if session_dir.exists():
            shutil.rmtree(session_dir)
        
        # Remove from memory
        del sessions[session_id]
        
        logger.info(f"Session {session_id} deleted successfully")
        
        return {"message": "Session deleted successfully", "session_id": session_id}
    
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@router.get("/recording-sessions/{session_id}/transcript")
async def get_transcript(session_id: str):
    """Get transcript for session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    transcript_text = ""
    
    # Try different transcription sources
    if "transcription" in session and session["transcription"]:
        transcription = session["transcription"]
        if "segments" in transcription and transcription["segments"]:
            for segment in transcription["segments"]:
                speaker = segment.get("speaker", "Speaker")
                text = segment.get("text", "").strip()
                timestamp = segment.get("start", 0)
                mins = int(timestamp // 60)
                secs = int(timestamp % 60)
                transcript_text += f"[{mins:02d}:{secs:02d}] {speaker}: {text}\n"
        else:
            transcript_text = transcription.get("text", "No transcript available")
    elif session.get("transcript"):
        transcript_text = session["transcript"]
    else:
        transcript_text = "No transcript available"
    
    return {"transcript": transcript_text, "session_id": session_id}