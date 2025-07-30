from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from services.email_service import email_service

router = APIRouter(
    prefix="/api/email",
    tags=["Email"]
)

class SMTPSettings(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str

@router.post("/configure-smtp")
async def configure_smtp(settings: SMTPSettings):
    """Configure SMTP settings"""
    email_service.update_smtp_config(
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_username,
        settings.smtp_password
    )
    return {"message": "SMTP settings updated successfully"}

@router.post("/test")
async def test_smtp_configuration(settings: SMTPSettings):
    """Test SMTP configuration"""
    result = await email_service.send_test_email(
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_username,
        settings.smtp_password
    )
    return result

@router.get("/get-smtp-config")
async def get_smtp_configuration():
    """Get current SMTP configuration (excluding password)"""
    config = email_service.get_smtp_config()
    # Do not return password for security reasons
    config['smtp_password'] = '' 
    return config

@router.post("/send-summary")
async def send_summary_email_endpoint(
    recipients: list[str],
    session_id: str,
    include_transcript: bool = True,
    include_audio: bool = False
):
    """Send a meeting summary email"""
    # Placeholder for fetching session and summary data
    # In a real app, you would fetch this from your database
    session_data = {"session_id": session_id, "name": f"Meeting {session_id}", "duration_seconds": 3600, "total_speakers": 2, "npu_accelerated": True}
    summary_data = {"executive_summary": "This is a mock summary.", "quality_metrics": {"avg_confidence": 0.9}}

    success = await email_service.send_meeting_summary(
        recipients=recipients,
        session_data=session_data,
        summary_data=summary_data,
        include_pdf=include_transcript,
        include_audio=include_audio
    )
    if success:
        return {"message": "Email queued successfully", "recipients": recipients}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")
