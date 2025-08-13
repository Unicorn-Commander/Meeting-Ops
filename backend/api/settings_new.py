"""
New Settings API endpoints for Meeting-Ops (as per API Delta Document)
Handles application configuration, agent settings, and vocabulary management
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, status, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
import json
import uuid
from pathlib import Path
from datetime import datetime
import io

from database.database import get_db
from models.settings import (
    ApplicationSettings,
    AgentSettings,
    PromptTemplate,
    VocabularyTerm,
    VocabularySet,
    VocabularyResponse,
    SettingsUpdateResponse,
    LiveTemplateContent,
    GenerateTemplateRequest,
    UpdateTemplateRequest
)

router = APIRouter(tags=["settings"])

# Configuration file paths
CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(exist_ok=True)

APP_SETTINGS_FILE = CONFIG_DIR / "application_settings.json"
AGENT_SETTINGS_FILE = CONFIG_DIR / "agent_settings.json"
VOCAB_DIR = Path("data/vocabulary")
VOCAB_DIR.mkdir(parents=True, exist_ok=True)
TERMS_FILE = VOCAB_DIR / "terms.json"
SETS_FILE = VOCAB_DIR / "sets.json"

# Session templates storage
TEMPLATES_DIR = Path("data/session_templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


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
            detail=f"Failed to save: {str(e)}"
        )


# ==================== APPLICATION SETTINGS ====================

@router.get("/api/settings/application", response_model=ApplicationSettings)
async def get_application_settings():
    """Fetch current application settings"""
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
        return ApplicationSettings()


@router.put("/api/settings/application", response_model=SettingsUpdateResponse)
async def update_application_settings(settings: ApplicationSettings):
    """Update application settings"""
    # Validate settings
    if settings.audioSampleRate not in [8000, 16000, 22050, 44100, 48000]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio sample rate"
        )
    
    # Save settings
    save_json_file(APP_SETTINGS_FILE, settings)
    
    return SettingsUpdateResponse(
        status="success",
        message="Settings updated"
    )


# ==================== AGENT SETTINGS ====================

@router.get("/api/settings/agents", response_model=AgentSettings)
async def get_agent_settings():
    """Fetch AI agent configuration"""
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
                isActive=True,
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow()
            ),
            PromptTemplate(
                id="prompt-2",
                name="Action Items",
                description="Extract action items from meeting",
                prompt="Extract all action items from the following meeting transcript. For each action item, identify the responsible person and deadline if mentioned:\n\n{transcript}",
                category="extraction",
                isActive=True,
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow()
            ),
            PromptTemplate(
                id="prompt-3",
                name="Key Decisions",
                description="Identify key decisions made",
                prompt="Identify and list all key decisions made during this meeting:\n\n{transcript}",
                category="analysis",
                isActive=True,
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


@router.put("/api/settings/agents", response_model=SettingsUpdateResponse)
async def update_agent_settings(settings: AgentSettings):
    """Update agent settings"""
    # Update timestamps for modified prompts
    for prompt in settings.prompts:
        if not prompt.createdAt:
            prompt.createdAt = datetime.utcnow()
        prompt.updatedAt = datetime.utcnow()
    
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    return SettingsUpdateResponse(
        status="success",
        message="Settings updated"
    )


@router.post("/api/settings/agents/prompts", response_model=PromptTemplate)
async def create_prompt_template(prompt: PromptTemplate):
    """Create new prompt template"""
    settings = await get_agent_settings()
    
    if not prompt.id:
        prompt.id = f"prompt-{len(settings.prompts) + 1}"
    
    if any(p.id == prompt.id for p in settings.prompts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt with ID {prompt.id} already exists"
        )
    
    prompt.createdAt = datetime.utcnow()
    prompt.updatedAt = datetime.utcnow()
    
    settings.prompts.append(prompt)
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    return prompt


@router.put("/api/settings/agents/prompts/{prompt_id}", response_model=PromptTemplate)
async def update_prompt_template(prompt_id: str, prompt: PromptTemplate):
    """Update existing prompt template"""
    settings = await get_agent_settings()
    
    prompt_index = next(
        (i for i, p in enumerate(settings.prompts) if p.id == prompt_id),
        None
    )
    
    if prompt_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt with ID {prompt_id} not found"
        )
    
    prompt.id = prompt_id
    prompt.updatedAt = datetime.utcnow()
    if not prompt.createdAt:
        prompt.createdAt = settings.prompts[prompt_index].createdAt
    
    settings.prompts[prompt_index] = prompt
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    return prompt


@router.delete("/api/settings/agents/prompts/{prompt_id}", response_model=SettingsUpdateResponse)
async def delete_prompt_template(prompt_id: str):
    """Delete prompt template"""
    settings = await get_agent_settings()
    
    initial_count = len(settings.prompts)
    settings.prompts = [p for p in settings.prompts if p.id != prompt_id]
    
    if len(settings.prompts) == initial_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt with ID {prompt_id} not found"
        )
    
    save_json_file(AGENT_SETTINGS_FILE, settings)
    
    return SettingsUpdateResponse(
        status="success",
        message=f"Prompt {prompt_id} deleted successfully"
    )


# ==================== VOCABULARY MANAGEMENT ====================

class VocabularyManager:
    """Manages vocabulary terms and sets"""
    
    def __init__(self):
        self.terms = self.load_terms()
        self.sets = self.load_sets()
    
    def load_terms(self) -> List[VocabularyTerm]:
        """Load vocabulary terms from storage"""
        if TERMS_FILE.exists():
            try:
                with open(TERMS_FILE, "r") as f:
                    data = json.load(f)
                    return [VocabularyTerm(**term) for term in data]
            except Exception as e:
                print(f"Error loading terms: {e}")
        return []
    
    def load_sets(self) -> List[VocabularySet]:
        """Load vocabulary sets from storage"""
        if SETS_FILE.exists():
            try:
                with open(SETS_FILE, "r") as f:
                    data = json.load(f)
                    return [VocabularySet(**vset) for vset in data]
            except Exception as e:
                print(f"Error loading sets: {e}")
        
        # Create default sets if none exist
        return [
            VocabularySet(
                id="set-1",
                name="Technology Acronyms",
                description="Common technology and IT acronyms",
                industry="technology",
                isActive=True,
                termCount=0,
                lastUpdated=datetime.utcnow()
            ),
            VocabularySet(
                id="set-2",
                name="Defense Acronyms",
                description="Military and defense industry acronyms",
                industry="defense",
                isActive=False,
                termCount=0,
                lastUpdated=datetime.utcnow()
            )
        ]
    
    def save_terms(self):
        """Save terms to storage"""
        with open(TERMS_FILE, "w") as f:
            data = [term.dict() for term in self.terms]
            json.dump(data, f, indent=2, default=str)
    
    def save_sets(self):
        """Save sets to storage"""
        with open(SETS_FILE, "w") as f:
            data = [vset.dict() for vset in self.sets]
            json.dump(data, f, indent=2, default=str)
    
    def update_set_counts(self):
        """Update term counts for each set"""
        for vset in self.sets:
            count = sum(
                1 for term in self.terms 
                if term.isActive and term.category == vset.industry
            )
            vset.termCount = count
            vset.lastUpdated = datetime.utcnow()


vocab_manager = VocabularyManager()


@router.get("/api/vocabulary", response_model=VocabularyResponse)
async def get_vocabulary():
    """Fetch vocabulary terms and sets"""
    vocab_manager.update_set_counts()
    return VocabularyResponse(
        terms=vocab_manager.terms,
        sets=vocab_manager.sets
    )


@router.post("/api/vocabulary/terms", response_model=VocabularyTerm)
async def add_vocabulary_term(term: VocabularyTerm):
    """Add new vocabulary term"""
    if not term.id:
        term.id = str(uuid.uuid4())
    
    if any(t.term.lower() == term.term.lower() for t in vocab_manager.terms):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Term '{term.term}' already exists"
        )
    
    term.createdAt = datetime.utcnow()
    term.updatedAt = datetime.utcnow()
    
    vocab_manager.terms.append(term)
    vocab_manager.save_terms()
    vocab_manager.update_set_counts()
    vocab_manager.save_sets()
    
    return term


@router.put("/api/vocabulary/terms/{term_id}", response_model=VocabularyTerm)
async def update_vocabulary_term(term_id: str, term: VocabularyTerm):
    """Update existing vocabulary term"""
    term_index = next(
        (i for i, t in enumerate(vocab_manager.terms) if t.id == term_id),
        None
    )
    
    if term_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Term with ID {term_id} not found"
        )
    
    term.id = term_id
    term.updatedAt = datetime.utcnow()
    if not term.createdAt:
        term.createdAt = vocab_manager.terms[term_index].createdAt
    
    vocab_manager.terms[term_index] = term
    vocab_manager.save_terms()
    vocab_manager.update_set_counts()
    vocab_manager.save_sets()
    
    return term


@router.delete("/api/vocabulary/terms/{term_id}", response_model=SettingsUpdateResponse)
async def delete_vocabulary_term(term_id: str):
    """Delete vocabulary term"""
    initial_count = len(vocab_manager.terms)
    vocab_manager.terms = [t for t in vocab_manager.terms if t.id != term_id]
    
    if len(vocab_manager.terms) == initial_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Term with ID {term_id} not found"
        )
    
    vocab_manager.save_terms()
    vocab_manager.update_set_counts()
    vocab_manager.save_sets()
    
    return SettingsUpdateResponse(
        status="success",
        message=f"Term {term_id} deleted successfully"
    )


@router.put("/api/vocabulary/sets/{set_id}/toggle", response_model=VocabularySet)
async def toggle_vocabulary_set(set_id: str):
    """Enable/disable vocabulary set"""
    vset = next((s for s in vocab_manager.sets if s.id == set_id), None)
    
    if not vset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Set with ID {set_id} not found"
        )
    
    vset.isActive = not vset.isActive
    vset.lastUpdated = datetime.utcnow()
    vocab_manager.save_sets()
    
    # Also activate/deactivate all terms in this set
    for term in vocab_manager.terms:
        if term.category == vset.industry:
            term.isActive = vset.isActive
    
    vocab_manager.save_terms()
    
    return vset


@router.post("/api/vocabulary/import")
async def import_vocabulary(file: UploadFile = File(...)):
    """Import vocabulary from JSON file"""
    if not file.filename.endswith('.json'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JSON files are supported"
        )
    
    try:
        content = await file.read()
        data = json.loads(content)
        
        imported_terms = 0
        imported_sets = 0
        
        if "terms" in data:
            for term_data in data["terms"]:
                try:
                    term = VocabularyTerm(**term_data)
                    if not term.id:
                        term.id = str(uuid.uuid4())
                    
                    if not any(t.term.lower() == term.term.lower() for t in vocab_manager.terms):
                        term.createdAt = datetime.utcnow()
                        term.updatedAt = datetime.utcnow()
                        vocab_manager.terms.append(term)
                        imported_terms += 1
                except Exception as e:
                    print(f"Error importing term: {e}")
        
        if "sets" in data:
            for set_data in data["sets"]:
                try:
                    vset = VocabularySet(**set_data)
                    if not vset.id:
                        vset.id = f"set-{len(vocab_manager.sets) + 1}"
                    
                    if not any(s.name == vset.name for s in vocab_manager.sets):
                        vset.lastUpdated = datetime.utcnow()
                        vocab_manager.sets.append(vset)
                        imported_sets += 1
                except Exception as e:
                    print(f"Error importing set: {e}")
        
        vocab_manager.save_terms()
        vocab_manager.update_set_counts()
        vocab_manager.save_sets()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": f"Imported {imported_terms} terms and {imported_sets} sets",
                "imported_terms": imported_terms,
                "imported_sets": imported_sets
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}"
        )


@router.get("/api/vocabulary/export")
async def export_vocabulary():
    """Export vocabulary as JSON file"""
    export_data = {
        "export_date": datetime.utcnow().isoformat(),
        "version": "1.0",
        "terms": [term.dict() for term in vocab_manager.terms],
        "sets": [vset.dict() for vset in vocab_manager.sets]
    }
    
    json_content = json.dumps(export_data, indent=2, default=str)
    
    return StreamingResponse(
        io.BytesIO(json_content.encode()),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=vocabulary_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        }
    )