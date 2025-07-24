import os
import shutil
import asyncio
import hashlib
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional, List, BinaryIO, Tuple
import aiofiles
import logging

logger = logging.getLogger(__name__)

class FileStorageService:
    """Service for managing audio file storage"""
    
    def __init__(self, base_path: str = "./storage/audio_files"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.recordings_path = self.base_path / "recordings"
        self.exports_path = self.base_path / "exports"
        self.temp_path = self.base_path / "temp"
        
        for path in [self.recordings_path, self.exports_path, self.temp_path]:
            path.mkdir(exist_ok=True)
    
    def get_session_directory(self, session_id: str) -> Path:
        """Get or create directory for a session"""
        session_dir = self.recordings_path / session_id
        session_dir.mkdir(exist_ok=True)
        return session_dir
    
    async def save_audio_file(
        self, 
        session_id: str, 
        audio_data: bytes,
        filename: Optional[str] = None,
        format: str = "wav"
    ) -> Tuple[str, str, int]:
        """
        Save audio file for a session
        Returns: (file_id, file_path, file_size)
        """
        try:
            # Generate file ID and name
            file_id = hashlib.md5(f"{session_id}_{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12]
            if not filename:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = f"recording_{timestamp}.{format}"
            
            # Get session directory
            session_dir = self.get_session_directory(session_id)
            file_path = session_dir / filename
            
            # Save file asynchronously
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(audio_data)
            
            file_size = len(audio_data)
            logger.info(f"Saved audio file: {file_path} ({file_size} bytes)")
            
            return file_id, str(file_path), file_size
        
        except Exception as e:
            logger.error(f"Error saving audio file: {e}")
            raise
    
    async def save_audio_stream(
        self,
        session_id: str,
        format: str = "wav"
    ):
        """
        Create a file handle for streaming audio data
        Returns a file path that can be written to incrementally
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.{format}"
        
        session_dir = self.get_session_directory(session_id)
        file_path = session_dir / filename
        
        return str(file_path)
    
    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Read a file asynchronously"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return None
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return None
    
    async def stream_file(self, file_path: str, chunk_size: int = 8192):
        """Stream a file in chunks"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                while chunk := await f.read(chunk_size):
                    yield chunk
        except Exception as e:
            logger.error(f"Error streaming file: {e}")
            raise
    
    def get_file_info(self, file_path: str) -> dict:
        """Get file metadata"""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            stat = path.stat()
            mime_type, _ = mimetypes.guess_type(str(path))
            
            return {
                "filename": path.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "mime_type": mime_type or "application/octet-stream",
                "format": path.suffix[1:] if path.suffix else None
            }
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return None
    
    def list_session_files(self, session_id: str) -> List[dict]:
        """List all files for a session"""
        session_dir = self.get_session_directory(session_id)
        if not session_dir.exists():
            return []
        
        files = []
        for file_path in session_dir.iterdir():
            if file_path.is_file():
                file_info = self.get_file_info(str(file_path))
                if file_info:
                    file_info["session_id"] = session_id
                    file_info["path"] = str(file_path)
                    files.append(file_info)
        
        return sorted(files, key=lambda x: x["created_at"], reverse=True)
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file"""
        try:
            path = Path(file_path)
            if path.exists():
                await asyncio.to_thread(path.unlink)
                logger.info(f"Deleted file: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False
    
    async def delete_session_files(self, session_id: str) -> int:
        """Delete all files for a session"""
        session_dir = self.get_session_directory(session_id)
        if not session_dir.exists():
            return 0
        
        deleted_count = 0
        try:
            for file_path in session_dir.iterdir():
                if file_path.is_file():
                    await self.delete_file(str(file_path))
                    deleted_count += 1
            
            # Remove empty directory
            await asyncio.to_thread(session_dir.rmdir)
            logger.info(f"Deleted {deleted_count} files for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error deleting session files: {e}")
        
        return deleted_count
    
    def get_storage_stats(self) -> dict:
        """Get storage statistics"""
        total_size = 0
        file_count = 0
        session_count = 0
        
        try:
            for session_dir in self.recordings_path.iterdir():
                if session_dir.is_dir():
                    session_count += 1
                    for file_path in session_dir.iterdir():
                        if file_path.is_file():
                            file_count += 1
                            total_size += file_path.stat().st_size
            
            # Get disk usage
            stat = os.statvfs(str(self.base_path))
            total_space = stat.f_blocks * stat.f_frsize
            free_space = stat.f_available * stat.f_frsize
            used_space = total_space - free_space
            
            return {
                "total_files": file_count,
                "total_sessions": session_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
                "disk_total_gb": round(total_space / (1024 * 1024 * 1024), 2),
                "disk_used_gb": round(used_space / (1024 * 1024 * 1024), 2),
                "disk_free_gb": round(free_space / (1024 * 1024 * 1024), 2),
                "disk_usage_percent": round((used_space / total_space) * 100, 2)
            }
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {}
    
    async def cleanup_old_files(self, days: int = 30) -> int:
        """Delete files older than specified days"""
        if days <= 0:
            return 0
        
        deleted_count = 0
        cutoff_time = datetime.utcnow().timestamp() - (days * 24 * 60 * 60)
        
        try:
            for session_dir in self.recordings_path.iterdir():
                if session_dir.is_dir():
                    for file_path in session_dir.iterdir():
                        if file_path.is_file():
                            if file_path.stat().st_mtime < cutoff_time:
                                await self.delete_file(str(file_path))
                                deleted_count += 1
                    
                    # Remove empty directories
                    if not any(session_dir.iterdir()):
                        await asyncio.to_thread(session_dir.rmdir)
            
            logger.info(f"Cleaned up {deleted_count} files older than {days} days")
            return deleted_count
        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return deleted_count

# Global instance
file_storage_service = FileStorageService()