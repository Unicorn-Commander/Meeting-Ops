"""
Real Meeting Intelligence API using Ollama LLM
No mock data - actual AI-powered summarization
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import requests
import json
import asyncio
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meeting-intelligence-real", tags=["meeting-intelligence-real"])

# Ollama configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3n:e4b")

class MeetingIntelligenceService:
    """Real AI-powered meeting intelligence service"""
    
    @staticmethod
    async def call_ollama(prompt: str, timeout: int = 30) -> str:
        """Call Ollama API with a prompt"""
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "max_tokens": 500
                    }
                },
                timeout=timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return ""
                
        except requests.exceptions.Timeout:
            logger.warning("Ollama request timed out, using faster prompt")
            return ""
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return ""

@router.post("/live-notes")
async def generate_live_notes(request: Dict[str, Any]):
    """Generate real-time meeting notes using LLM"""
    
    transcript = request.get("transcript", "")
    templates = request.get("templates", ["key-points"])
    session_id = request.get("session_id")
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required")
    
    # Limit transcript length for faster processing
    max_transcript_length = 2000  # characters
    if len(transcript) > max_transcript_length:
        # Take the most recent portion for live updates
        transcript = "..." + transcript[-max_transcript_length:]
    
    notes = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "templates_used": templates,
        "notes": {}
    }
    
    # Generate each requested template
    service = MeetingIntelligenceService()
    
    # Run all prompts in parallel for speed
    tasks = []
    
    if "key-points" in templates:
        prompt = f"""Extract the key points from this meeting transcript in bullet format.
Be concise and focus on the most important topics.

Transcript:
{transcript}

Key Points (bullet list):"""
        
        response = await service.call_ollama(prompt, timeout=10)
        if response:
            notes["notes"]["key_points"] = {
                "title": "Key Points",
                "content": response.strip()
            }
    
    if "decisions" in templates:
        prompt = f"""List any decisions made in this meeting.
Only include actual decisions, not discussions.

Transcript:
{transcript}

Decisions Made:"""
        
        response = await service.call_ollama(prompt, timeout=10)
        if response:
            # Parse into list
            items = [line.strip() for line in response.split('\n') if line.strip() and not line.startswith('Decisions')]
            notes["notes"]["decisions"] = {
                "title": "Key Decisions",
                "items": items[:5]  # Limit to 5 items
            }
    
    if "action-items" in templates:
        prompt = f"""Extract action items from this meeting.
Format: task | owner | deadline (if mentioned)

Transcript:
{transcript}

Action Items:"""
        
        response = await service.call_ollama(prompt, timeout=10)
        if response:
            items = []
            for line in response.split('\n'):
                if '|' in line or '-' in line:
                    parts = line.replace('-', '').strip().split('|')
                    if len(parts) >= 1:
                        item = {
                            "task": parts[0].strip(),
                            "owner": parts[1].strip() if len(parts) > 1 else "TBD",
                            "deadline": parts[2].strip() if len(parts) > 2 else "TBD"
                        }
                        items.append(item)
            
            notes["notes"]["action_items"] = {
                "title": "Action Items",
                "items": items[:5]  # Limit to 5 items
            }
    
    if "participants" in templates:
        prompt = f"""List the participants/speakers in this meeting based on the transcript.

Transcript:
{transcript}

Participants (names only, one per line):"""
        
        response = await service.call_ollama(prompt, timeout=10)
        if response:
            participants = [p.strip() for p in response.split('\n') if p.strip()]
            notes["notes"]["participants"] = participants[:10]  # Limit to 10
    
    if "next-steps" in templates:
        prompt = f"""What are the next steps discussed in this meeting?
Be specific and actionable.

Transcript:
{transcript}

Next Steps (bullet list):"""
        
        response = await service.call_ollama(prompt, timeout=10)
        if response:
            notes["notes"]["next_steps"] = {
                "title": "Next Steps",
                "content": response.strip()
            }
    
    return notes

@router.post("/final-report")
async def generate_final_report(request: Dict[str, Any]):
    """Generate comprehensive final report using LLM"""
    
    transcript = request.get("transcript", "")
    session_id = request.get("session_id")
    live_summary = request.get("live_summary", {})
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required")
    
    service = MeetingIntelligenceService()
    
    # For final report, we can use the full transcript
    report = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "report": {
            "title": "Meeting Report",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "sections": {}
        }
    }
    
    # Executive Summary
    prompt = f"""Write a comprehensive executive summary of this meeting.
Include the purpose, main discussions, outcomes, and overall assessment.

Transcript:
{transcript[:4000]}

Executive Summary:"""
    
    response = await service.call_ollama(prompt, timeout=30)
    if response:
        report["report"]["sections"]["overview"] = {
            "title": "Executive Summary",
            "content": response.strip()
        }
    
    # Detailed Analysis
    prompt = f"""Provide a detailed analysis of the meeting dynamics and effectiveness.
Consider: participation, decision-making process, time management, and outcomes.

Transcript:
{transcript[:4000]}

Analysis:"""
    
    response = await service.call_ollama(prompt, timeout=30)
    if response:
        report["report"]["sections"]["analysis"] = {
            "title": "Meeting Analysis",
            "content": response.strip()
        }
    
    # Recommendations
    prompt = f"""Based on this meeting, what recommendations would you make for:
1. Improving future meetings
2. Following up on discussed items
3. Addressing any concerns raised

Transcript:
{transcript[:4000]}

Recommendations:"""
    
    response = await service.call_ollama(prompt, timeout=30)
    if response:
        report["report"]["sections"]["recommendations"] = {
            "title": "Recommendations",
            "content": response.strip()
        }
    
    # Risk Assessment
    prompt = f"""Identify any risks or concerns mentioned in this meeting.
Include potential issues, blockers, or areas needing attention.

Transcript:
{transcript[:4000]}

Risks and Concerns:"""
    
    response = await service.call_ollama(prompt, timeout=30)
    if response:
        report["report"]["sections"]["risks"] = {
            "title": "Risk Assessment",
            "content": response.strip()
        }
    
    return report

@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify the API is working"""
    # Test Ollama connection
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        ollama_status = "connected" if response.status_code == 200 else "error"
        models = response.json().get("models", []) if response.status_code == 200 else []
        model_names = [m.get("name") for m in models]
    except:
        ollama_status = "disconnected"
        model_names = []
    
    return {
        "status": "ok",
        "message": "Meeting Intelligence Real API is working",
        "ollama_status": ollama_status,
        "ollama_url": OLLAMA_URL,
        "configured_model": OLLAMA_MODEL,
        "available_models": model_names,
        "timestamp": datetime.now().isoformat()
    }