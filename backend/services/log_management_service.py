"""
Log Management Service
"""
import os
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class LogManagementService:
    def __init__(self):
        # Use a local log directory that we have permissions for
        self.log_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(self.log_directory, exist_ok=True)

    def _get_log_files(self) -> List[str]:
        """List all log files in the log directory"""
        files = []
        for f in os.listdir(self.log_directory):
            if f.endswith(".log"):
                files.append(f)
        return sorted(files)

    def list_log_files(self) -> List[Dict[str, Any]]:
        """List available log files with metadata"""
        log_files = []
        for filename in self._get_log_files():
            filepath = os.path.join(self.log_directory, filename)
            try:
                stat = os.stat(filepath)
                log_files.append({
                    "name": filename,
                    "size": stat.st_size,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
            except Exception as e:
                logger.warning(f"Could not get info for log file {filename}: {e}")
        return log_files

    def get_log_file_content(self, filename: str, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
        """Get content of a specific log file with pagination"""
        filepath = os.path.join(self.log_directory, filename)
        if not os.path.exists(filepath):
            return {"error": "File not found"}

        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            
            paginated_lines = lines[start_index:end_index]
            
            return {
                "filename": filename,
                "total_lines": total_lines,
                "page": page,
                "page_size": page_size,
                "content": "".join(paginated_lines)
            }
        except Exception as e:
            logger.error(f"Error reading log file {filename}: {e}")
            return {"error": f"Could not read file: {e}"}

    def rotate_logs(self) -> Dict[str, Any]:
        """Trigger log rotation (placeholder for actual implementation)"""
        logger.info("Log rotation triggered. (Actual rotation depends on system configuration like logrotate)")
        return {"message": "Log rotation command sent. Check system logs for details."}

    def delete_log_file(self, filename: str) -> Dict[str, Any]:
        """Delete a specific log file"""
        filepath = os.path.join(self.log_directory, filename)
        if not os.path.exists(filepath):
            return {"error": "File not found"}
        
        try:
            os.remove(filepath)
            logger.info(f"Log file {filename} deleted.")
            return {"message": f"File {filename} deleted successfully"}
        except Exception as e:
            logger.error(f"Error deleting log file {filename}: {e}")
            return {"error": f"Could not delete file: {e}"}

log_management_service = LogManagementService()