from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func
from typing import List, Optional
import logging
from datetime import datetime, timedelta

from database.database import get_db
from database.models import AudioFile, RecordingSession
from services.file_storage_service import file_storage_service
from auth.dependencies import get_current_user, require_permission
from auth.models import User
from auth.service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

@router.get("", response_model=List[dict])
async def list_files(
    session_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    format: Optional[str] = None,
    sort_by: str = Query("created_at", regex="^(created_at|filename|file_size|duration)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(require_permission("file.download")),
    db: DBSession = Depends(get_db)
):
    """List audio files with optional filtering"""
    try:
        query = db.query(AudioFile).filter(AudioFile.deleted_at.is_(None))
        
        # Filter by session if specified
        if session_id:
            query = query.filter(AudioFile.session_id == session_id)
        
        # Filter by format if specified
        if format:
            query = query.filter(AudioFile.file_format == format.lower())
        
        # Apply sorting
        sort_column = getattr(AudioFile, sort_by)
        if order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        files = query.offset(offset).limit(limit).all()
        
        # Log access
        AuthService.log_action(
            db, current_user.id, "files.list",
            details={"session_id": session_id, "count": len(files)}
        )
        
        return {
            "files": [f.to_dict() for f in files],
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{file_id}")
async def get_file_info(
    file_id: str,
    current_user: User = Depends(require_permission("file.download")),
    db: DBSession = Depends(get_db)
):
    """Get file metadata"""
    try:
        file = db.query(AudioFile).filter(
            AudioFile.file_id == file_id,
            AudioFile.deleted_at.is_(None)
        ).first()
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Update access count and timestamp
        file.access_count += 1
        file.last_accessed = datetime.utcnow()
        db.commit()
        
        # Get additional file info from filesystem
        file_info = file_storage_service.get_file_info(file.file_path)
        
        result = file.to_dict()
        if file_info:
            result.update({
                "actual_size": file_info["size"],
                "modified_at": file_info["modified_at"]
            })
        
        # Log access
        AuthService.log_action(
            db, current_user.id, "files.view", "audio_file", file_id,
            details={"filename": file.filename}
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    current_user: User = Depends(require_permission("file.download")),
    db: DBSession = Depends(get_db)
):
    """Download an audio file"""
    try:
        file = db.query(AudioFile).filter(
            AudioFile.file_id == file_id,
            AudioFile.deleted_at.is_(None)
        ).first()
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if file exists on disk
        file_info = file_storage_service.get_file_info(file.file_path)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        # Update access count
        file.access_count += 1
        file.last_accessed = datetime.utcnow()
        db.commit()
        
        # Log download
        AuthService.log_action(
            db, current_user.id, "files.download", "audio_file", file_id,
            details={"filename": file.filename, "size": file.file_size}
        )
        
        # Return file
        return FileResponse(
            path=file.file_path,
            filename=file.filename,
            media_type=file.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file.filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{file_id}/stream")
async def stream_file(
    file_id: str,
    current_user: User = Depends(require_permission("file.download")),
    db: DBSession = Depends(get_db)
):
    """Stream an audio file for playback"""
    try:
        file = db.query(AudioFile).filter(
            AudioFile.file_id == file_id,
            AudioFile.deleted_at.is_(None)
        ).first()
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if file exists on disk
        file_info = file_storage_service.get_file_info(file.file_path)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        # Log streaming
        AuthService.log_action(
            db, current_user.id, "files.stream", "audio_file", file_id,
            details={"filename": file.filename}
        )
        
        # Stream file
        async def file_streamer():
            async for chunk in file_storage_service.stream_file(file.file_path):
                yield chunk
        
        return StreamingResponse(
            file_streamer(),
            media_type=file.mime_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file.file_size),
                "Content-Disposition": f'inline; filename="{file.filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    permanent: bool = Query(False, description="Permanently delete file"),
    current_user: User = Depends(require_permission("file.delete")),
    db: DBSession = Depends(get_db)
):
    """Delete an audio file (soft delete by default)"""
    try:
        file = db.query(AudioFile).filter(
            AudioFile.file_id == file_id,
            AudioFile.deleted_at.is_(None)
        ).first()
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        if permanent:
            # Permanently delete file from disk
            success = await file_storage_service.delete_file(file.file_path)
            if success:
                db.delete(file)
                action = "files.delete_permanent"
            else:
                raise HTTPException(status_code=500, detail="Failed to delete file from disk")
        else:
            # Soft delete
            file.deleted_at = datetime.utcnow()
            file.status = "deleted"
            action = "files.delete_soft"
        
        db.commit()
        
        # Log deletion
        AuthService.log_action(
            db, current_user.id, action, "audio_file", file_id,
            details={"filename": file.filename, "permanent": permanent}
        )
        
        return {"message": "File deleted successfully", "permanent": permanent}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/session/{session_id}")
async def list_session_files(
    session_id: str,
    current_user: User = Depends(require_permission("file.download")),
    db: DBSession = Depends(get_db)
):
    """List all files for a specific session"""
    try:
        # Check if session exists
        session = db.query(RecordingSession).filter(
            RecordingSession.session_id == session_id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get files from database
        files = db.query(AudioFile).filter(
            AudioFile.session_id == session_id,
            AudioFile.deleted_at.is_(None)
        ).order_by(AudioFile.created_at.desc()).all()
        
        # Also check filesystem for any untracked files
        fs_files = file_storage_service.list_session_files(session_id)
        
        return {
            "session_id": session_id,
            "session_name": session.name,
            "files": [f.to_dict() for f in files],
            "filesystem_files": fs_files,
            "total": len(files)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing session files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{file_id}/tags")
async def update_file_tags(
    file_id: str,
    tags: List[str],
    current_user: User = Depends(require_permission("file.upload")),
    db: DBSession = Depends(get_db)
):
    """Update file tags"""
    try:
        file = db.query(AudioFile).filter(
            AudioFile.file_id == file_id,
            AudioFile.deleted_at.is_(None)
        ).first()
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        file.tags = tags
        file.updated_at = datetime.utcnow()
        db.commit()
        
        # Log update
        AuthService.log_action(
            db, current_user.id, "files.update_tags", "audio_file", file_id,
            details={"tags": tags}
        )
        
        return {"message": "Tags updated successfully", "tags": tags}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating file tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage/stats")
async def get_storage_stats(
    current_user: User = Depends(require_permission("settings.read")),
    db: DBSession = Depends(get_db)
):
    """Get storage statistics"""
    try:
        stats = file_storage_service.get_storage_stats()
        
        # Add database stats
        total_db_files = db.query(AudioFile).filter(
            AudioFile.deleted_at.is_(None)
        ).count()
        
        total_db_size = db.query(
            func.sum(AudioFile.file_size)
        ).filter(
            AudioFile.deleted_at.is_(None)
        ).scalar() or 0
        
        stats.update({
            "database_files": total_db_files,
            "database_size_bytes": total_db_size,
            "database_size_gb": round(total_db_size / (1024 ** 3), 2)
        })
        
        return stats
    except Exception as e:
        logger.error(f"Error getting storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup")
async def cleanup_old_files(
    days: int = Query(30, ge=1, le=365),
    dry_run: bool = Query(True, description="Preview what would be deleted"),
    current_user: User = Depends(require_permission("file.delete")),
    db: DBSession = Depends(get_db)
):
    """Clean up old files"""
    try:
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=403,
                detail="Only superusers can perform cleanup operations"
            )
        
        if dry_run:
            # Just count files that would be deleted
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            count = db.query(AudioFile).filter(
                AudioFile.created_at < cutoff_date,
                AudioFile.deleted_at.is_(None)
            ).count()
            
            return {
                "dry_run": True,
                "files_to_delete": count,
                "days": days,
                "message": f"Would delete {count} files older than {days} days"
            }
        else:
            # Perform actual cleanup
            deleted_count = await file_storage_service.cleanup_old_files(days)
            
            # Log cleanup
            AuthService.log_action(
                db, current_user.id, "files.cleanup",
                details={"days": days, "deleted_count": deleted_count}
            )
            
            return {
                "dry_run": False,
                "files_deleted": deleted_count,
                "days": days,
                "message": f"Deleted {deleted_count} files older than {days} days"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))