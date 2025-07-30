from fastapi import APIRouter, Query
from typing import Dict, Any
from services.ssl_service import ssl_service

router = APIRouter(
    prefix="/api/ssl",
    tags=["SSL"]
)

@router.get("/status", response_model=Dict[str, Any])
async def get_ssl_status(domain: str = Query(..., description="Domain name to check SSL status for")):
    """Get the SSL certificate status for a given domain"""
    return ssl_service.get_certificate_status(domain)

@router.post("/renew", response_model=Dict[str, Any])
async def trigger_ssl_renewal():
    """Trigger a manual SSL certificate renewal attempt"""
    return ssl_service.trigger_renewal()
