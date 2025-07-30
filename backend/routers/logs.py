from fastapi import APIRouter, Query
from typing import List, Dict, Any
from services.log_management_service import log_management_service

router = APIRouter(
    prefix="/api/logs",
    tags=["Logs"]
)

@router.get("/list", response_model=List[Dict[str, Any]])
async def list_logs():
    """List all available log files"""
    return log_management_service.list_log_files()

@router.get("/{filename}", response_model=Dict[str, Any])
async def get_log_content(
    filename: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000)
):
    """Get content of a specific log file with pagination"""
    return log_management_service.get_log_file_content(filename, page, page_size)

@router.post("/rotate", response_model=Dict[str, Any])
async def rotate_logs():
    """Trigger log rotation"""
    return log_management_service.rotate_logs()

@router.delete("/{filename}", response_model=Dict[str, Any])
async def delete_log(filename: str):
    """Delete a specific log file"""
    return log_management_service.delete_log_file(filename)
