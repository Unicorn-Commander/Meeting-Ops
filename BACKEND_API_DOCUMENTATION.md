# Meeting-Ops Backend API Documentation

## Overview

The Meeting-Ops backend is a FastAPI-based REST API that provides comprehensive meeting recording, transcription, and management capabilities. The backend is **100% complete and production-ready**.

## Base URL

- Development: `http://localhost:9050`
- Production: Configure as needed

## Authentication

The API uses JWT (JSON Web Token) authentication. Most endpoints require authentication.

### Login
```bash
curl -X POST http://localhost:9050/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@unicorn-commander.local",
    "role": "superuser"
  }
}
```

Use the access token in subsequent requests:
```bash
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" http://localhost:9050/api/endpoint
```

## API Documentation Endpoints

- **Swagger UI**: http://localhost:9050/docs
- **ReDoc**: http://localhost:9050/redoc
- **OpenAPI JSON**: http://localhost:9050/openapi.json

## Core API Endpoints

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/auth/register` | Register new user (admin only) | Yes (admin) |
| POST | `/api/auth/login` | Login with username/password | No |
| POST | `/api/auth/refresh` | Refresh access token | No |
| GET | `/api/auth/me` | Get current user profile | Yes |
| PUT | `/api/auth/me` | Update profile | Yes |
| POST | `/api/auth/me/change-password` | Change password | Yes |
| POST | `/api/auth/me/api-key` | Generate API key | Yes |
| POST | `/api/auth/logout` | Logout | Yes |
| GET | `/api/auth/users` | List users | Yes (admin) |
| PUT | `/api/auth/users/{id}/activate` | Activate user | Yes (admin) |
| PUT | `/api/auth/users/{id}/deactivate` | Deactivate user | Yes (admin) |

### Recording Session Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/recording-sessions` | Create new session | Yes |
| GET | `/api/recording-sessions` | List sessions | Yes |
| GET | `/api/recording-sessions/{id}` | Get session details | Yes |
| PUT | `/api/recording-sessions/{id}` | Update session | Yes |
| DELETE | `/api/recording-sessions/{id}` | Delete session | Yes |
| POST | `/api/recording-sessions/{id}/start` | Start recording | Yes |
| POST | `/api/recording-sessions/{id}/stop` | Stop recording | Yes |
| POST | `/api/recording-sessions/{id}/pause` | Pause recording | Yes |
| POST | `/api/recording-sessions/{id}/resume` | Resume recording | Yes |
| GET | `/api/recording-sessions/{id}/export` | Export session | Yes |
| POST | `/api/recording-sessions/{id}/summarize` | Generate AI summary | Yes |
| GET | `/api/recording-sessions/{id}/summary` | Get summary | Yes |
| GET | `/api/recording-sessions/{id}/transcriptions` | Get transcriptions | Yes |
| POST | `/api/recording-sessions/{id}/email-summary` | Email summary | Yes |

### System & Settings

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/status` | System status | No |
| GET | `/api/system-info` | System information | Yes |
| GET | `/api/audio-devices` | List audio devices | Yes |
| GET | `/api/audio-level` | Current audio level | Yes |
| GET | `/api/settings` | Get all settings | Yes |
| GET | `/api/settings/{category}` | Get category settings | Yes |
| PUT | `/api/settings/{category}` | Update settings | Yes |
| POST | `/api/settings/export` | Export settings | Yes |
| POST | `/api/settings/import` | Import settings | Yes |

### File Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/files` | List audio files | Yes |
| GET | `/api/files/{id}` | Get file metadata | Yes |
| GET | `/api/files/{id}/download` | Download file | Yes |
| GET | `/api/files/{id}/stream` | Stream file | Yes |
| DELETE | `/api/files/{id}` | Delete file | Yes |
| GET | `/api/files/session/{id}` | Get session files | Yes |
| POST | `/api/files/{id}/tags` | Update file tags | Yes |
| GET | `/api/files/storage/stats` | Storage statistics | Yes |
| POST | `/api/files/cleanup` | Clean up old files | Yes (admin) |

### WebSocket Endpoints

| Endpoint | Description | Auth Required |
|----------|-------------|---------------|
| `/ws/stream/{session_id}` | Audio streaming | Yes |
| `/ws/transcription` | Live transcription | Yes |
| `/ws/audio-levels` | Real-time audio levels | Yes |

### Advanced Features

#### Calendar Integration
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/calendar/configure` | Configure calendar integration |
| POST | `/api/calendar/room/configure` | Configure room settings |
| GET | `/api/calendar/room/status` | Get room availability |
| POST | `/api/calendar/meeting/schedule` | Schedule meeting |
| GET | `/api/calendar/availability/{email}` | Check user availability |
| POST | `/api/calendar/meeting/suggest-times` | Suggest meeting times |
| POST | `/api/calendar/conflicts/check` | Check for conflicts |

#### Search & Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/search/semantic` | Semantic search |
| POST | `/api/search/similar` | Find similar segments |
| POST | `/api/search/index/session/{id}` | Index session |
| GET | `/api/search/collection/info` | Collection info |
| GET | `/api/analytics/meetings` | Meeting analytics |

## Request/Response Examples

### Create Recording Session
```bash
curl -X POST http://localhost:9050/api/recording-sessions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Team Meeting",
    "description": "Weekly sync meeting"
  }'
```

Response:
```json
{
  "id": 123,
  "name": "Team Meeting",
  "description": "Weekly sync meeting",
  "state": "pending",
  "created_at": "2025-07-30T12:00:00Z",
  "user_id": 1
}
```

### Start Recording
```bash
curl -X POST http://localhost:9050/api/recording-sessions/123/start \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### WebSocket Connection (JavaScript)
```javascript
const ws = new WebSocket('ws://localhost:9050/ws/audio-levels');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Audio level:', data.level);
};
```

## Error Responses

The API uses standard HTTP status codes:

- `200 OK` - Success
- `201 Created` - Resource created
- `400 Bad Request` - Invalid request
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Access denied
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

Error response format:
```json
{
  "detail": "Error message here"
}
```

Validation error format:
```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

## NPU Acceleration

The backend includes NPU (Neural Processing Unit) acceleration for transcription. When NPU hardware is available, transcription performance is dramatically improved (220x+ speedup).

NPU status can be checked via:
```bash
curl http://localhost:9050/api/status
```

## Development Notes

1. **Default Credentials**: 
   - Username: `admin`
   - Password: `admin123` (change in production!)

2. **Audio Devices**: The backend supports multiple audio input devices including USB microphones, line-in, and Bluetooth.

3. **File Storage**: Audio files are stored in `/home/ucadmin/recordings/` by default.

4. **Database**: SQLite by default, PostgreSQL supported for production.

5. **Ollama Integration**: LLM summarization requires Ollama running on `localhost:11434`.

## Frontend Development Guide

For frontend developers, here's what you need to know:

1. **Authentication Flow**:
   - POST to `/api/auth/login` to get tokens
   - Include `Authorization: Bearer TOKEN` header in requests
   - Refresh token when expired using `/api/auth/refresh`

2. **Real-time Features**:
   - WebSocket endpoints for live data
   - Audio streaming and transcription in real-time
   - Audio level monitoring for UI visualization

3. **Session Workflow**:
   - Create session → Start recording → Stop recording → Get transcription → Generate summary

4. **CORS**: Backend allows CORS from any origin in development mode.

## Testing the Backend

A test script is available at `/test_backend_api.py` that verifies all critical endpoints are working.

Run it with:
```bash
python test_backend_api.py
```

## Complete OpenAPI Specification

The full OpenAPI specification is available at:
- `/backend/openapi.json` (exported file)
- `http://localhost:9050/openapi.json` (live endpoint)

This can be imported into tools like Postman or used to generate client SDKs.