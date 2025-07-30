from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from services.backup_service import backup_service

router = APIRouter(
    prefix="/api/backup",
    tags=["Backup"]
)

@router.post("/create", response_model=Dict[str, Any])
async def create_backup_endpoint():
    """Create a new backup"""
    return backup_service.create_backup()

@router.get("/list", response_model=List[Dict[str, Any]])
async def list_backups_endpoint():
    """List all available backups"""
    return backup_service.list_backups()

@router.post("/restore/{backup_id}", response_model=Dict[str, Any])
async def restore_backup_endpoint(backup_id: str):
    """Restore from a specific backup"""
    return backup_service.restore_backup(backup_id)

@router.delete("/{backup_id}", response_model=Dict[str, Any])
async def delete_backup_endpoint(backup_id: str):
    """Delete a specific backup file"""
    return backup_service.delete_backup(backup_id)
