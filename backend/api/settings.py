"""
Settings API endpoints for Meeting-Ops
Handles application configuration and agent settings
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, Any
import json
import os
from pathlib import Path
from datetime import datetime

from models.settings import (
    ApplicationSettings,
    AgentSettings,
    PromptTemplate,
    SettingsUpdateResponse
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Configuration file paths
CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(exist_ok=True)

APP_SETTINGS_FILE = CONFIG_DIR / "application_settings.json"
AGENT_SETTINGS_FILE = CONFIG_DIR / "agent_settings.json"


def load_json_file(file_path: Path, default_factory=None):
    """Load JSON from file or return default"""
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    if default_factory:
        return default_factory()
    return {}


def save_json_file(file_path: Path, data: Any):
    """Save data to JSON file"""
    try:
        with open(file_path, "w") as f:
            if hasattr(data, "dict"):
                json.dump(data.dict(), f, indent=2, default=str)
            else:
                json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Error saving {file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {str(e)}"
        )


# Application Settings Endpoints
@router.get("/application", response_model=ApplicationSettings)
async def get_application_settings():
    """
    Fetch current application settings
    """
    settings_data = load_json_file(APP_SETTINGS_FILE)
    
    if not settings_data:
        # Return default settings if file doesn't exist
        settings = ApplicationSettings()
        save_json_file(APP_SETTINGS_FILE, settings)
        return settings
    
    try:
        return ApplicationSettings(**settings_data)
    except Exception as e:
        print(f"Error parsing application settings: {e}")
        # Return defaults on error
        return ApplicationSettings()


@router.put("/application", response_model=SettingsUpdateResponse)
async def update_application_settings(settings: ApplicationSettings):
    """
    Update application settings
    """
    # Validate settings
    if settings.audioSampleRate not in [8000, 16000, 22050, 44100, 48000]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio sample rate. Must be one of: 8000, 16000, 22050, 44100, 48000"
        )
    
    # Save settings
    save_json_file(APP_SETTINGS_FILE, settings)
    
    # Apply settings to system (if needed)
    # TODO: Notify relevant services about settings change
    
    return SettingsUpdateResponse(
        status="success",
        message="Application settings updated successfully"
    )


# Agent Settings Endpoints
@router.get("/agents", response_model=AgentSettings)
async def get_agent_settings():
    """
    Fetch AI agent configuration
    """
    settings_data = load_json_file(AGENT_SETTINGS_FILE)
    
    if not settings_data:
        # Create default settings with sample prompts
        settings = AgentSettings()
        
        # Add default prompt templates
        default_prompts = [
            PromptTemplate(
                id="prompt-1",
                name="Meeting Summary",
                description="Generate concise meeting summary",
                prompt="Summarize the following meeting transcript focusing on key decisions, action items, and next steps:\n\n{transcript}",
                category="summarization",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow()
            ),
            PromptTemplate(
                id="prompt-2",
                name="Action Items",
                description="Extract action items from meeting",
                prompt="Extract all action items from the following meeting transcript. For each action item, identify the responsible person and deadline if mentioned:\n\n{transcript}",
                category="extraction",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow()
            ),
            PromptTemplate(
                id="prompt-3",
                name="Executive Brief",
                description="Create executive-level brief",
                prompt="Create a brief executive summary (max 3 paragraphs) of the following meeting, highlighting only the most critical decisions and outcomes:\n\n{transcript}",
                category="summarization",
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow()
            )
        ]
        
        settings.prompts = default_prompts
        save_json_file(AGENT_SETTINGS_FILE, settings)
        return settings
    
    try:
        return AgentSettings(**settings_data)
    except Exception as e:
        print(f"Error parsing agent settings: {e}")
        return AgentSettings()


@router.put("/agents", response_model=SettingsUpdateResponse)
async def update_agent_settings(settings: AgentSettings):
    """
    Update agent settings
    """
    # Update timestamps for modified prompts
    for prompt in settings.prompts:
        if not prompt.createdAt:
            prompt.createdAt = datetime.utcnow()
        prompt.updatedAt = datetime.utcnow()
    
    # Save settings
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    # TODO: Reload agent configurations in running services
    
    return SettingsUpdateResponse(
        status="success",
        message="Agent settings updated successfully"
    )


# Prompt Template Management
@router.post("/agents/prompts", response_model=PromptTemplate)
async def create_prompt_template(prompt: PromptTemplate):
    """
    Create new prompt template
    """
    # Load current settings
    settings = await get_agent_settings()
    
    # Generate ID if not provided
    if not prompt.id:
        prompt.id = f"prompt-{len(settings.prompts) + 1}"
    
    # Check for duplicate ID
    if any(p.id == prompt.id for p in settings.prompts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt with ID {prompt.id} already exists"
        )
    
    # Set timestamps
    prompt.createdAt = datetime.utcnow()
    prompt.updatedAt = datetime.utcnow()
    
    # Add to prompts
    settings.prompts.append(prompt)
    
    # Save settings
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    return prompt


@router.put("/agents/prompts/{prompt_id}", response_model=PromptTemplate)
async def update_prompt_template(prompt_id: str, prompt: PromptTemplate):
    """
    Update existing prompt template
    """
    # Load current settings
    settings = await get_agent_settings()
    
    # Find prompt
    prompt_index = next(
        (i for i, p in enumerate(settings.prompts) if p.id == prompt_id),
        None
    )
    
    if prompt_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt with ID {prompt_id} not found"
        )
    
    # Update prompt
    prompt.id = prompt_id
    prompt.updatedAt = datetime.utcnow()
    if not prompt.createdAt:
        prompt.createdAt = settings.prompts[prompt_index].createdAt
    
    settings.prompts[prompt_index] = prompt
    
    # Save settings
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    return prompt


@router.delete("/agents/prompts/{prompt_id}", response_model=SettingsUpdateResponse)
async def delete_prompt_template(prompt_id: str):
    """
    Delete prompt template
    """
    # Load current settings
    settings = await get_agent_settings()
    
    # Find and remove prompt
    initial_count = len(settings.prompts)
    settings.prompts = [p for p in settings.prompts if p.id != prompt_id]
    
    if len(settings.prompts) == initial_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt with ID {prompt_id} not found"
        )
    
    # Save settings
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    return SettingsUpdateResponse(
        status="success",
        message=f"Prompt {prompt_id} deleted successfully"
    )