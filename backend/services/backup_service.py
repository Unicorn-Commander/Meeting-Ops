"""
Backup Service for Unicorn Commander Meeting Ops
Handles backup and restoration of critical application data.
"""
import os
import shutil
import tarfile
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class BackupService:
    def __init__(self):
        self.backup_dir = os.path.join(os.getcwd(), "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        self.db_path = os.path.join(os.getcwd(), "backend", "meeting_sessions.db")
        self.audio_storage_path = os.path.join(os.getcwd(), "backend", "storage", "audio_files")
        self.config_path = os.path.join(os.getcwd(), "backend", "config") # Assuming a config directory

    def _get_backup_filepath(self, backup_id: str) -> str:
        return os.path.join(self.backup_dir, f"unicorn_commander_backup_{backup_id}.tar.gz")

    def create_backup(self) -> Dict[str, Any]:
        """Creates a new backup of the database, audio files, and configuration."""
        backup_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filepath = self._get_backup_filepath(backup_id)

        try:
            with tarfile.open(backup_filepath, "w:gz") as tar:
                # Add database
                if os.path.exists(self.db_path):
                    tar.add(self.db_path, arcname=os.path.basename(self.db_path))
                    logger.info(f"Added database to backup: {self.db_path}")
                else:
                    logger.warning(f"Database not found, skipping backup: {self.db_path}")

                # Add audio files
                if os.path.exists(self.audio_storage_path):
                    tar.add(self.audio_storage_path, arcname=os.path.basename(self.audio_storage_path))
                    logger.info(f"Added audio storage to backup: {self.audio_storage_path}")
                else:
                    logger.warning(f"Audio storage not found, skipping backup: {self.audio_storage_path}")

                # Add configuration files (if config_path exists and is a directory)
                if os.path.exists(self.config_path) and os.path.isdir(self.config_path):
                    tar.add(self.config_path, arcname=os.path.basename(self.config_path))
                    logger.info(f"Added configuration to backup: {self.config_path}")
                else:
                    logger.warning(f"Configuration path not found or not a directory, skipping backup: {self.config_path}")

            logger.info(f"Backup created successfully: {backup_filepath}")
            return {"status": "success", "backup_id": backup_id, "filepath": backup_filepath}
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            if os.path.exists(backup_filepath):
                os.remove(backup_filepath) # Clean up incomplete backup
            return {"status": "error", "message": str(e)}

    def list_backups(self) -> List[Dict[str, Any]]:
        """Lists all available backups."""
        backups = []
        for filename in os.listdir(self.backup_dir):
            if filename.startswith("unicorn_commander_backup_") and filename.endswith(".tar.gz"):
                filepath = os.path.join(self.backup_dir, filename)
                try:
                    stat = os.stat(filepath)
                    backup_id = filename.replace("unicorn_commander_backup_", "").replace(".tar.gz", "")
                    backups.append({
                        "backup_id": backup_id,
                        "filename": filename,
                        "size": stat.st_size,
                        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception as e:
                    logger.warning(f"Could not get info for backup file {filename}: {e}")
        return sorted(backups, key=lambda x: x["created_at"], reverse=True)

    def restore_backup(self, backup_id: str) -> Dict[str, Any]:
        """Restores data from a specified backup. WARNING: This will overwrite current data."""
        backup_filepath = self._get_backup_filepath(backup_id)
        if not os.path.exists(backup_filepath):
            return {"status": "error", "message": "Backup file not found."}

        try:
            # Stop services that might be using these files before restoring
            # (This would typically be handled by the deployment system, e.g., Docker Compose down)
            logger.warning("Attempting to restore backup. Ensure application services are stopped to prevent data corruption.")

            # Extract contents
            with tarfile.open(backup_filepath, "r:gz") as tar:
                # Extract database
                db_arcname = os.path.basename(self.db_path)
                if db_arcname in tar.getnames():
                    tar.extract(db_arcname, path=os.path.dirname(self.db_path))
                    logger.info(f"Restored database: {self.db_path}")
                
                # Extract audio files
                audio_arcname = os.path.basename(self.audio_storage_path)
                if audio_arcname in tar.getnames():
                    # Remove existing audio files before restoring
                    if os.path.exists(self.audio_storage_path):
                        shutil.rmtree(self.audio_storage_path)
                    tar.extract(audio_arcname, path=os.path.dirname(self.audio_storage_path))
                    logger.info(f"Restored audio storage: {self.audio_storage_path}")

                # Extract config files
                config_arcname = os.path.basename(self.config_path)
                if config_arcname in tar.getnames():
                    if os.path.exists(self.config_path):
                        shutil.rmtree(self.config_path)
                    tar.extract(config_arcname, path=os.path.dirname(self.config_path))
                    logger.info(f"Restored configuration: {self.config_path}")

            logger.info(f"Backup {backup_id} restored successfully.")
            return {"status": "success", "message": f"Backup {backup_id} restored. Please restart the application."}
        except Exception as e:
            logger.error(f"Failed to restore backup {backup_id}: {e}")
            return {"status": "error", "message": str(e)}

    def delete_backup(self, backup_id: str) -> Dict[str, Any]:
        """Deletes a specified backup file."""
        backup_filepath = self._get_backup_filepath(backup_id)
        if not os.path.exists(backup_filepath):
            return {"status": "error", "message": "Backup file not found."}

        try:
            os.remove(backup_filepath)
            logger.info(f"Backup file {backup_filepath} deleted.")
            return {"status": "success", "message": f"Backup {backup_id} deleted successfully."}
        except Exception as e:
            logger.error(f"Failed to delete backup file {backup_filepath}: {e}")
            return {"status": "error", "message": str(e)}

backup_service = BackupService()