# API Delta Document - Frontend vs Backend Requirements
Generated: January 13, 2025

## Overview
This document outlines all the API endpoints that the frontend expects but are either missing or need to be implemented/updated in the backend.

## 🔴 MISSING ENDPOINTS (Critical)

### 1. Application Settings
**Frontend Component**: `ApplicationSettingsPage.tsx`

#### GET /api/settings/application
- **Purpose**: Fetch current application settings
- **Expected Response**:
```json
{
  "defaultLLMProvider": "ollama",
  "transcriptionLanguage": "en",
  "transcriptionModel": "large-v3",
  "autoSaveInterval": 30,
  "enableNPUAcceleration": true,
  "audioSampleRate": 16000,
  "audioInputDevice": "default",
  "chunkDuration": 10,
  "enableVAD": true,
  "vadThreshold": 0.5,
  "maxRecordingDuration": 7200,
  "enableAutoTranscription": true,
  "enableSpeakerDiarization": true,
  "maxSpeakers": 4,
  "notificationSettings": {
    "onRecordingStart": true,
    "onRecordingStop": true,
    "onTranscriptionComplete": true,
    "onReportGenerated": false
  },
  "storageSettings": {
    "retentionDays": 90,
    "autoArchive": true,
    "compressionEnabled": false
  }
}
```

#### PUT /api/settings/application
- **Purpose**: Update application settings
- **Request Body**: Same as GET response
- **Expected Response**: `{ "status": "success", "message": "Settings updated" }`

### 2. Agent Settings
**Frontend Component**: `AgentSettingsPage.tsx`

#### GET /api/settings/agents
- **Purpose**: Fetch AI agent configuration
- **Expected Response**:
```json
{
  "defaultAgent": "summarization",
  "agents": {
    "transcription": {
      "temperature": 0.3,
      "maxTokens": 4096,
      "topP": 0.9,
      "frequencyPenalty": 0,
      "presencePenalty": 0,
      "timeout": 30
    },
    "summarization": { ... },
    "analysis": { ... },
    "extraction": { ... }
  },
  "prompts": [
    {
      "id": "prompt-1",
      "name": "Meeting Summary",
      "description": "Generate concise meeting summary",
      "prompt": "Summarize the following meeting transcript...",
      "isActive": true,
      "category": "summarization"
    }
  ],
  "features": {
    "autoSummarization": true,
    "actionItemExtraction": true,
    "sentimentAnalysis": false,
    "topicModeling": false,
    "speakerIdentification": true,
    "keywordExtraction": true
  },
  "processingRules": {
    "minTranscriptLength": 100,
    "maxProcessingTime": 300,
    "retryAttempts": 3,
    "chunkSize": 4000
  }
}
```

#### PUT /api/settings/agents
- **Purpose**: Update agent settings
- **Request Body**: Same as GET response

#### POST /api/settings/agents/prompts
- **Purpose**: Create new prompt template
- **Request Body**: Single prompt object

#### PUT /api/settings/agents/prompts/{promptId}
- **Purpose**: Update existing prompt

#### DELETE /api/settings/agents/prompts/{promptId}
- **Purpose**: Delete prompt template

### 3. Vocabulary Management
**Frontend Component**: `VocabularyManagement.tsx`

#### GET /api/vocabulary
- **Purpose**: Fetch vocabulary terms and sets
- **Expected Response**:
```json
{
  "terms": [
    {
      "id": "1",
      "term": "NPU",
      "expansion": "Neural Processing Unit",
      "category": "technology",
      "priority": 10,
      "contextHints": ["hardware", "acceleration", "AI"],
      "isActive": true,
      "createdAt": "2025-01-13T10:00:00Z",
      "updatedAt": "2025-01-13T10:00:00Z"
    }
  ],
  "sets": [
    {
      "id": "1",
      "name": "Defense Acronyms",
      "description": "Military and defense industry acronyms",
      "industry": "defense",
      "isActive": true,
      "termCount": 156,
      "lastUpdated": "2025-01-13T10:00:00Z"
    }
  ]
}
```

#### POST /api/vocabulary/terms
- **Purpose**: Add new vocabulary term

#### PUT /api/vocabulary/terms/{termId}
- **Purpose**: Update existing term

#### DELETE /api/vocabulary/terms/{termId}
- **Purpose**: Delete vocabulary term

#### PUT /api/vocabulary/sets/{setId}/toggle
- **Purpose**: Enable/disable vocabulary set

#### POST /api/vocabulary/import
- **Purpose**: Import vocabulary from JSON file
- **Request**: Multipart form data with JSON file

#### GET /api/vocabulary/export
- **Purpose**: Export vocabulary as JSON

### 4. Live Meeting Intelligence
**Frontend Components**: `RealtimeSummarization.tsx`, `LiveMeetingTemplates.tsx`

#### GET /api/meeting-intelligence-real/live-templates/{sessionId}
- **Purpose**: Get live-generated templates during meeting
- **Expected Response**:
```json
{
  "executive_summary": "Meeting focused on...",
  "action_items": "1. John to review...",
  "key_decisions": "Approved budget for...",
  "participants": "John Smith (PM), Jane Doe (Dev)...",
  "next_steps": "Schedule follow-up for...",
  "risks_issues": "Potential delay in..."
}
```

#### POST /api/meeting-intelligence-real/generate-template
- **Purpose**: Generate template from transcript
- **Request Body**:
```json
{
  "session_id": "session-123",
  "template_id": "executive-summary"
}
```

### 5. Session Templates
**Frontend Component**: `LiveMeetingTemplates.tsx`

#### GET /api/sessions/{sessionId}/templates
- **Purpose**: Get saved templates for a session
- **Expected Response**: Object with template IDs as keys and content as values

#### PUT /api/sessions/{sessionId}/templates/{templateId}
- **Purpose**: Save/update template content
- **Request Body**: `{ "content": "Template content..." }`

### 6. Real-time WebSocket Endpoints
**Frontend Components**: `NewUltimateDashboard.tsx`, WebSocket contexts

#### WS /ws/transcription/{sessionId}
- **Purpose**: Live transcription streaming
- **Expected Messages**:
```json
{
  "type": "transcription",
  "segment": {
    "id": "seg-123",
    "text": "This is the transcribed text",
    "timestamp": "2025-01-13T10:00:00Z",
    "speaker": "Speaker 1",
    "confidence": 0.95
  }
}
```

## 🟡 EXISTING BUT NEEDS UPDATE

### 1. Summarization Templates
**Current**: `/api/summarization-templates`
**Issue**: Response format doesn't match frontend expectations
**Required Update**: Return array of template objects with proper structure

### 2. Meeting Intelligence Live Notes
**Current**: `/api/meeting-intelligence-real/live-notes`
**Issue**: May need to handle content-based triggers
**Required Update**: Support word count thresholds for triggering

## 🟢 WORKING (Verified)

### Already Implemented
- ✅ `/api/simple/recording-sessions` - Session CRUD
- ✅ `/api/simple/recording-sessions/{id}/start` - Start recording
- ✅ `/api/simple/recording-sessions/{id}/stop` - Stop recording
- ✅ `/api/appliance/*` - Network, WiFi, Backup, Updates (complete)
- ✅ `/api/llm-settings/*` - LLM provider settings

## 📋 Implementation Priority

### Phase 1: Critical Settings (Highest Priority)
1. Application Settings endpoints - Core system configuration
2. Agent Settings endpoints - AI behavior configuration
3. Vocabulary Management - Customer requirement for acronyms

### Phase 2: Live Features
1. WebSocket transcription endpoint fixes
2. Live template generation
3. Content-based summarization triggers

### Phase 3: Data Management
1. Session templates storage
2. Export improvements
3. Batch operations

## 🔧 Backend Implementation Guide

### For Each Missing Endpoint:
1. **Create Pydantic Models** for request/response validation
2. **Add Database Tables** if persistent storage needed
3. **Implement Service Layer** for business logic
4. **Add Router Endpoints** in appropriate API modules
5. **Update OpenAPI Schema** documentation
6. **Add Authentication** where required

### Example Implementation Pattern:
```python
# models/settings.py
from pydantic import BaseModel
from typing import Optional, Dict

class ApplicationSettings(BaseModel):
    defaultLLMProvider: str
    transcriptionLanguage: str
    transcriptionModel: str
    # ... other fields
    
# api/settings.py
from fastapi import APIRouter, Depends
from models.settings import ApplicationSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])

@router.get("/application", response_model=ApplicationSettings)
async def get_application_settings():
    # Load from database or config file
    return ApplicationSettings(...)

@router.put("/application")
async def update_application_settings(settings: ApplicationSettings):
    # Save to database or config file
    return {"status": "success", "message": "Settings updated"}
```

## 📊 Testing Checklist

### For Backend Team:
- [ ] All endpoints return expected JSON structure
- [ ] WebSocket connections properly handle reconnection
- [ ] Settings persist across server restarts
- [ ] Vocabulary import/export handles large datasets
- [ ] Live features work with multiple concurrent sessions
- [ ] Authentication properly enforced on admin endpoints

### For Frontend Validation:
- [ ] Settings save and load correctly
- [ ] Live transcription displays in real-time
- [ ] Summarization triggers on content thresholds
- [ ] Vocabulary management CRUD operations work
- [ ] Templates generate and save properly

## 🚀 Next Steps

1. **Backend Team**: Implement Phase 1 endpoints first
2. **Testing**: Set up integration tests for new endpoints
3. **Documentation**: Update OpenAPI spec as endpoints are added
4. **Validation**: Frontend team validates each endpoint
5. **Deployment**: Roll out incrementally with feature flags

## 📝 Notes

- All endpoints should support CORS for cross-origin requests
- Consider rate limiting for resource-intensive operations
- Implement proper error responses with meaningful messages
- WebSocket endpoints need reconnection logic
- Settings should have validation for acceptable ranges/values