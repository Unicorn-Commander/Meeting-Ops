# Unicorn Commander - SMB Features Plan

## Overview
Features required for Small and Medium Businesses to use Unicorn Commander effectively in a professional environment.

## 1. Authentication & Account Management

### Requirements
- Multi-user support
- Role-based access (Admin, Manager, User, Viewer)
- Secure password management
- Session management
- Optional SSO/LDAP integration

### Recommended Solution: **FastAPI-Users**
- Well-integrated with FastAPI
- Built-in user registration, login, password reset
- JWT tokens for stateless auth
- Easy to extend with custom fields
- Supports OAuth2 providers

### Alternative: **Authelia** (for enterprise)
- Standalone auth server
- 2FA support
- LDAP/AD integration
- More complex but more features

### Implementation Plan
```python
# Using FastAPI-Users
pip install fastapi-users[sqlalchemy,oauth]

# Features to implement:
- User registration (admin-only)
- Login/logout
- Password reset via email
- User profile management
- API key generation for automation
```

## 2. File Management System

### Requirements
- Browse recorded audio files
- In-browser audio playback
- Download files (single/bulk)
- Delete with confirmation
- Search and filter
- File metadata display
- Storage quota management

### Custom Implementation with Libraries
```python
# Backend libraries
pip install python-multipart  # File uploads
pip install aiofiles         # Async file operations
pip install python-magic     # File type detection

# Frontend libraries
npm install react-audio-player  # Audio playback
npm install react-dropzone      # File upload
npm install react-table         # File listing
```

### Features to Build
1. **File Browser API**
   - List files with pagination
   - File metadata (size, duration, format)
   - Search by name, date, speaker
   - Sort and filter options

2. **Audio Player Component**
   - Waveform visualization
   - Playback speed control
   - Skip to transcription timestamps
   - Download while playing

3. **Bulk Operations**
   - Select multiple files
   - Bulk download as ZIP
   - Bulk delete with confirmation
   - Bulk export transcriptions

## 3. Team & Organization Features

### Requirements
- Organization/workspace concept
- Team member invitations
- Shared sessions vs private
- Department segregation
- Usage analytics per team

### Database Schema Extensions
```python
class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    created_at = Column(DateTime)
    plan = Column(String)  # free, pro, enterprise
    storage_quota_gb = Column(Integer)
    
class UserOrganization(Base):
    __tablename__ = "user_organizations"
    user_id = Column(Integer, ForeignKey("users.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    role = Column(String)  # admin, manager, user
    joined_at = Column(DateTime)
```

## 4. Access Control & Permissions

### Requirements
- Session visibility rules
- File access permissions
- Feature access by role
- API rate limiting
- Audit trail

### Permission Matrix
| Feature | Admin | Manager | User | Viewer |
|---------|-------|---------|------|---------|
| Create Sessions | ✓ | ✓ | ✓ | ✗ |
| Delete Sessions | ✓ | ✓ | Own only | ✗ |
| View All Sessions | ✓ | ✓ | Department | Own only |
| Download Files | ✓ | ✓ | ✓ | ✓ |
| Manage Users | ✓ | ✗ | ✗ | ✗ |
| Change Settings | ✓ | ✗ | ✗ | ✗ |

### Implementation
```python
# Dependency injection for auth
async def get_current_user(token: str = Depends(oauth2_scheme)):
    # Validate token and return user
    pass

async def require_role(required_role: str):
    async def role_checker(user: User = Depends(get_current_user)):
        if user.role not in ROLE_HIERARCHY[required_role]:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return role_checker

# Usage in endpoints
@app.get("/api/admin/users", dependencies=[Depends(require_role("admin"))])
async def list_users():
    pass
```

## 5. Business Features

### 5.1 Meeting Templates
- Predefined meeting types (standup, review, interview)
- Custom fields per template
- Automatic tagging

### 5.2 Integrations
- **Calendar Integration**
  - Google Calendar API
  - Outlook/Exchange
  - Automatic session creation from calendar

- **Notification System**
  - Email notifications (SendGrid/SMTP)
  - Slack/Teams webhooks
  - Recording completed alerts

- **Export Integrations**
  - Google Drive upload
  - Dropbox sync
  - S3 compatible storage

### 5.3 Analytics Dashboard
- Usage statistics
- Popular meeting times
- Speaker participation metrics
- Storage usage trends
- User activity logs

## 6. Professional UI/UX Improvements

### Requirements
- Professional design system
- Responsive for mobile/tablet
- Accessibility (WCAG 2.1)
- Customizable branding
- Dark/light theme

### Recommended UI Libraries
```json
{
  "dependencies": {
    "@headlessui/react": "^1.7.0",      // Accessible UI components
    "@tanstack/react-table": "^8.0.0",   // Advanced tables
    "react-hook-form": "^7.0.0",         // Form management
    "recharts": "^2.0.0",                // Charts for analytics
    "@dnd-kit/sortable": "^7.0.0",       // Drag-drop for file management
    "react-hot-toast": "^2.0.0"          // Notifications
  }
}
```

## 7. Security Enhancements

### Requirements
- Input validation
- XSS protection
- CSRF tokens
- Rate limiting
- Security headers

### Implementation
```python
# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security headers
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from secure import SecureHeaders

secure_headers = SecureHeaders()
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com"])
```

## 8. Implementation Priority

### Phase 1: Core Auth (Week 1-2) ✅ COMPLETED
1. ✅ Custom auth implementation (not FastAPI-Users)
2. ✅ Basic login/logout with JWT tokens
3. ✅ User management API
4. ✅ JWT token auth (access + refresh tokens)
5. ✅ Role-based access (superuser, admin, manager, user, viewer)
6. ✅ API key support
7. ✅ Initial admin user creation
8. ✅ Audit logging foundation
9. ✅ Frontend auth integration with React Context

### Phase 2: File Management (Week 3-4)
1. File listing API
2. Audio player component
3. Download functionality
4. Basic file browser UI
5. Search and filter

### Phase 3: Teams & Permissions (Week 5-6)
1. Organization model
2. Team invitations
3. Permission system
4. Audit logging
5. Usage quotas

### Phase 4: Business Features (Week 7-8)
1. Meeting templates
2. Email notifications
3. Analytics dashboard
4. Calendar integration
5. Bulk operations

## 9. Testing Strategy

### Unit Tests
- Auth flows
- Permission checks
- File operations
- API endpoints

### Integration Tests
- Full user workflows
- File upload/download
- Team collaboration
- Security scenarios

### E2E Tests
- Cypress for UI testing
- API test automation
- Performance testing
- Security scanning

## 10. Documentation

### User Documentation
- Getting started guide
- Admin manual
- API documentation
- Video tutorials

### Developer Documentation
- Architecture overview
- API reference
- Deployment guide
- Contributing guidelines