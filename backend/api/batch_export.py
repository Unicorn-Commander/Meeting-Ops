from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging
import json
import os
import uuid
from pathlib import Path

from database import get_db
from auth import get_current_user
from models import User, RecordingSession

router = APIRouter(prefix="/api/export", tags=["Export"])
logger = logging.getLogger(__name__)

# Export models
class ExportOptions(BaseModel):
    includeTimestamps: bool = True
    includeSpeakers: bool = True
    includeInsights: bool = False
    mergeFiles: bool = False
    emailTo: Optional[str] = None
    scheduleTime: Optional[str] = None

class BatchExportRequest(BaseModel):
    sessionIds: List[str]
    format: str  # txt, pdf, docx, csv, json, srt
    options: ExportOptions

class ExportJob(BaseModel):
    id: str
    sessionIds: List[str]
    format: str
    status: str  # pending, processing, completed, failed
    progress: int
    createdAt: datetime
    completedAt: Optional[datetime] = None
    fileSize: Optional[int] = None
    downloadUrl: Optional[str] = None
    error: Optional[str] = None
    options: Dict[str, Any]

class ExportTemplate(BaseModel):
    id: str
    name: str
    format: str
    options: Dict[str, Any]
    description: str

# In-memory storage for export jobs (should use database in production)
export_jobs: Dict[str, ExportJob] = {}
export_templates: List[ExportTemplate] = [
    ExportTemplate(
        id="1",
        name="Meeting Summary",
        format="pdf",
        options={"includeTimestamps": False, "includeSpeakers": True, "includeInsights": True},
        description="Professional meeting summary with key insights"
    ),
    ExportTemplate(
        id="2",
        name="Full Transcript",
        format="docx",
        options={"includeTimestamps": True, "includeSpeakers": True, "includeInsights": False},
        description="Complete transcript with timestamps and speakers"
    ),
    ExportTemplate(
        id="3",
        name="Subtitles",
        format="srt",
        options={"includeTimestamps": True, "includeSpeakers": False, "includeInsights": False},
        description="SRT subtitle format for video editing"
    )
]

@router.post("/batch", response_model=ExportJob)
async def create_batch_export(
    request: BatchExportRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a batch export job for multiple sessions"""
    try:
        # Create export job
        job_id = str(uuid.uuid4())
        job = ExportJob(
            id=job_id,
            sessionIds=request.sessionIds,
            format=request.format,
            status="pending",
            progress=0,
            createdAt=datetime.utcnow(),
            options=request.options.dict()
        )
        
        # Store job
        export_jobs[job_id] = job
        
        # Start background export task
        background_tasks.add_task(
            process_export_job,
            job_id,
            request.sessionIds,
            request.format,
            request.options,
            db
        )
        
        logger.info(f"Created batch export job {job_id} for {len(request.sessionIds)} sessions")
        return job
        
    except Exception as e:
        logger.error(f"Failed to create batch export: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs", response_model=List[ExportJob])
async def get_export_jobs(
    current_user: User = Depends(get_current_user)
):
    """Get all export jobs for the current user"""
    return list(export_jobs.values())

@router.get("/jobs/{job_id}", response_model=ExportJob)
async def get_export_job(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get status of a specific export job"""
    job = export_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    return job

@router.delete("/jobs/{job_id}")
async def cancel_export_job(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Cancel an export job"""
    job = export_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    
    if job.status in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed or failed job")
    
    job.status = "cancelled"
    job.error = "Job cancelled by user"
    
    return {"message": "Export job cancelled"}

@router.get("/templates", response_model=List[ExportTemplate])
async def get_export_templates(
    current_user: User = Depends(get_current_user)
):
    """Get available export templates"""
    return export_templates

@router.post("/templates", response_model=ExportTemplate)
async def create_export_template(
    template: ExportTemplate,
    current_user: User = Depends(get_current_user)
):
    """Create a new export template"""
    template.id = str(uuid.uuid4())
    export_templates.append(template)
    return template

@router.delete("/templates/{template_id}")
async def delete_export_template(
    template_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete an export template"""
    global export_templates
    export_templates = [t for t in export_templates if t.id != template_id]
    return {"message": "Template deleted"}

async def process_export_job(
    job_id: str,
    session_ids: List[str],
    format: str,
    options: ExportOptions,
    db: Session
):
    """Background task to process export job"""
    job = export_jobs.get(job_id)
    if not job:
        return
    
    try:
        job.status = "processing"
        total_sessions = len(session_ids)
        
        # Create export directory
        export_dir = Path("/tmp/exports") / job_id
        export_dir.mkdir(parents=True, exist_ok=True)
        
        exported_files = []
        
        for i, session_id in enumerate(session_ids):
            # Update progress
            job.progress = int((i / total_sessions) * 100)
            
            # Get session from database
            session = db.query(RecordingSession).filter(
                RecordingSession.id == session_id
            ).first()
            
            if not session:
                logger.warning(f"Session {session_id} not found")
                continue
            
            # Export based on format
            if format == "txt":
                content = export_to_txt(session, options)
                filename = f"{session.name or session_id}.txt"
            elif format == "json":
                content = export_to_json(session, options)
                filename = f"{session.name or session_id}.json"
            elif format == "srt":
                content = export_to_srt(session, options)
                filename = f"{session.name or session_id}.srt"
            else:
                # For PDF/DOCX, just create placeholder
                content = f"# {session.name or session_id}\n\nExport format {format} coming soon!"
                filename = f"{session.name or session_id}.{format}"
            
            # Save file
            file_path = export_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            exported_files.append(file_path)
        
        # Create archive if multiple files or merge requested
        if len(exported_files) > 1 or options.mergeFiles:
            import zipfile
            archive_path = export_dir / f"export_{job_id}.zip"
            with zipfile.ZipFile(archive_path, 'w') as zf:
                for file_path in exported_files:
                    zf.write(file_path, file_path.name)
            
            job.downloadUrl = f"/api/export/download/{job_id}/export_{job_id}.zip"
            job.fileSize = archive_path.stat().st_size
        elif exported_files:
            # Single file
            job.downloadUrl = f"/api/export/download/{job_id}/{exported_files[0].name}"
            job.fileSize = exported_files[0].stat().st_size
        
        job.status = "completed"
        job.progress = 100
        job.completedAt = datetime.utcnow()
        
        # Send email if requested
        if options.emailTo:
            # TODO: Implement email sending
            logger.info(f"Would send export to {options.emailTo}")
        
    except Exception as e:
        logger.error(f"Export job {job_id} failed: {e}")
        job.status = "failed"
        job.error = str(e)

def export_to_txt(session: RecordingSession, options: ExportOptions) -> str:
    """Export session to plain text format"""
    lines = []
    lines.append(f"Meeting: {session.name or 'Untitled'}")
    lines.append(f"Date: {session.created_at}")
    lines.append(f"Duration: {session.duration or 0} seconds")
    lines.append("-" * 50)
    lines.append("")
    
    # Add transcript if available
    if hasattr(session, 'transcript') and session.transcript:
        transcript = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
        
        for segment in transcript.get('segments', []):
            line = ""
            
            if options.includeTimestamps:
                start_time = segment.get('start', 0)
                line += f"[{format_timestamp(start_time)}] "
            
            if options.includeSpeakers and 'speaker' in segment:
                line += f"{segment['speaker']}: "
            
            line += segment.get('text', '')
            lines.append(line)
    else:
        lines.append("No transcript available for this session.")
    
    if options.includeInsights:
        lines.append("")
        lines.append("-" * 50)
        lines.append("AI INSIGHTS")
        lines.append("-" * 50)
        lines.append("• Key topics discussed")
        lines.append("• Action items identified")
        lines.append("• Decisions made")
    
    return "\n".join(lines)

def export_to_json(session: RecordingSession, options: ExportOptions) -> str:
    """Export session to JSON format"""
    data = {
        "session_id": session.id,
        "name": session.name,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "duration": session.duration,
        "transcript": []
    }
    
    if hasattr(session, 'transcript') and session.transcript:
        transcript = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
        
        for segment in transcript.get('segments', []):
            segment_data = {"text": segment.get('text', '')}
            
            if options.includeTimestamps:
                segment_data["start"] = segment.get('start', 0)
                segment_data["end"] = segment.get('end', 0)
            
            if options.includeSpeakers and 'speaker' in segment:
                segment_data["speaker"] = segment['speaker']
            
            data["transcript"].append(segment_data)
    
    if options.includeInsights:
        data["insights"] = {
            "topics": [],
            "action_items": [],
            "decisions": []
        }
    
    return json.dumps(data, indent=2)

def export_to_srt(session: RecordingSession, options: ExportOptions) -> str:
    """Export session to SRT subtitle format"""
    lines = []
    counter = 1
    
    if hasattr(session, 'transcript') and session.transcript:
        transcript = json.loads(session.transcript) if isinstance(session.transcript, str) else session.transcript
        
        for segment in transcript.get('segments', []):
            lines.append(str(counter))
            
            start_time = format_srt_timestamp(segment.get('start', 0))
            end_time = format_srt_timestamp(segment.get('end', segment.get('start', 0) + 5))
            lines.append(f"{start_time} --> {end_time}")
            
            text = segment.get('text', '')
            if options.includeSpeakers and 'speaker' in segment:
                text = f"{segment['speaker']}: {text}"
            
            lines.append(text)
            lines.append("")  # Empty line between subtitles
            counter += 1
    
    return "\n".join(lines)

def format_timestamp(seconds: float) -> str:
    """Format seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def format_srt_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp format (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')

@router.get("/download/{job_id}/{filename}")
async def download_export(
    job_id: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Download exported file"""
    from fastapi.responses import FileResponse
    
    file_path = Path("/tmp/exports") / job_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type='application/octet-stream'
    )