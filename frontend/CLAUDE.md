# Meeting-Ops Frontend Development Guide
Part of the Unicorn Commander Suite - Frontend Specific Instructions

## 🎯 Frontend Overview
React 19.1 + TypeScript frontend for the Meeting-Ops AI-powered meeting recording appliance. This document is specifically for AI assistants working on the frontend code only.

## 📊 Current Frontend Status (January 14, 2025)
- **Overall Completion**: 85%
- **Core Recording UI**: 95% Complete
- **Session Management**: 90% Complete  
- **Live Transcription**: 100% Complete
- **AI Features**: 95% Complete
- **Session Details/Playback**: 60% Complete (needs work)
- **Polish & UX**: 70% Complete

## 🚀 Quick Start

### Development Server
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0  # Available on network
# Or just: npm run dev  # Local only
```

### Production Build
```bash
npm run build:production  # Builds despite TypeScript errors
npm run preview -- --host 0.0.0.0 --port 7778
```

### Access Points
- **Local**: http://localhost:7778
- **Network**: http://your-server-ip:7778
- **Backend API**: http://localhost:9050

## 🔧 Key Frontend Components

### Core Pages
- `/src/pages/LiveRecording.tsx` - Main recording interface ✅ Working
- `/src/pages/SessionList.tsx` - List all sessions ✅ Working
- `/src/pages/SessionDetails.tsx` - Playback & transcript ⚠️ Needs fixes
- `/src/pages/admin/UnifiedAgent.tsx` - AI agent configuration ✅ Working

### Important Components
- `/src/components/RecordingControls.tsx` - Start/stop buttons
- `/src/components/LiveTranscriptionDisplay.tsx` - Real-time transcript
- `/src/components/AudioPlayer.tsx` - Playback controls
- `/src/components/SessionAnalysis.tsx` - AI summaries

### Context & State
- `/src/contexts/AuthContext.tsx` - JWT authentication
- `/src/config.ts` - API endpoints configuration

## ✅ What's Working

1. **Recording Interface**
   - Start/stop recording buttons
   - Timer display
   - Status indicators
   - Live transcription display

2. **Session Management**
   - List sessions from database
   - Basic session info display
   - Delete sessions
   - Export transcripts (TXT only)

3. **Live Features**
   - WebSocket transcription
   - Progressive AI summaries
   - Speaker identification
   - Word-level timestamps

4. **Authentication**
   - Login/logout
   - JWT tokens
   - Protected routes
   - Role-based navigation

## ❌ Known Frontend Issues

### High Priority
1. **Session Details Page**
   - Audio player not loading files correctly
   - Transcript not syncing with playback
   - Export buttons need PDF/DOCX support

2. **Audio Meters**
   - Not verified if showing real USB mic levels
   - WebSocket connection exists but data uncertain

3. **TypeScript Errors**
   - 42 build errors (non-blocking)
   - Type mismatches need cleanup

### Medium Priority
4. **Search & Filter**
   - No search functionality in session list
   - No date/speaker filters

5. **UI Polish**
   - Inconsistent spacing
   - Loading states missing in places
   - Error handling needs improvement

6. **Mobile Responsive**
   - Not optimized for mobile/tablet
   - Sidebar doesn't collapse

## 🎯 Priority Tasks for Frontend

### Immediate (Fix Core Features)
1. **Fix Session Details Page**
   ```tsx
   // SessionDetails.tsx needs:
   - Correct audio file path handling
   - Transcript display from database
   - Synchronized playback controls
   ```

2. **Verify Audio Meters**
   ```tsx
   // Check if WebSocket data is real:
   - Monitor /ws/audio-levels
   - Display actual mic input levels
   ```

3. **Add Export Formats**
   ```tsx
   // Add to export functionality:
   - PDF generation
   - DOCX generation
   - Formatted templates
   ```

### Next Sprint
4. **Search Implementation**
   - Full-text search across transcripts
   - Filter by date, duration, speaker

5. **TypeScript Cleanup**
   - Fix 42 build errors
   - Add proper types
   - Remove any/unknown usage

6. **UI/UX Polish**
   - Consistent spacing (use Tailwind classes)
   - Loading skeletons
   - Better error messages
   - Toast notifications

## 🔌 API Endpoints

### Recording Sessions
```typescript
// Create session
POST /api/simple/recording-sessions
Body: { name: string, description?: string }

// List sessions  
GET /api/simple/recording-sessions

// Get session details
GET /api/simple/recording-sessions/{id}

// Start recording
POST /api/simple/recording-sessions/{id}/start

// Stop recording
POST /api/simple/recording-sessions/{id}/stop

// Download audio
GET /api/simple/recording-sessions/{id}/download/audio

// Download transcript
GET /api/simple/recording-sessions/{id}/download/transcript
```

### WebSocket Connections
```typescript
// Live transcription
ws://localhost:9050/ws/transcription/{session_id}

// Audio levels
ws://localhost:9050/ws/audio-levels

// Progressive summaries
ws://localhost:9050/ws/auto-summary/{session_id}
```

## 🐛 Common Issues & Solutions

### Sessions Not Appearing
- Check backend is running: `curl http://localhost:9050/api/simple/recording-sessions`
- Verify frontend config points to correct backend
- Check browser console for API errors

### WebSocket Not Connecting
- Ensure backend supports WebSocket
- Check for CORS issues
- Verify session ID is valid

### Audio Playback Issues
- File paths may be incorrect
- Check audio file exists on server
- Verify correct MIME type

### TypeScript Errors
- Use `npm run build:production` to bypass
- Or fix types incrementally
- Add `// @ts-ignore` for urgent fixes

## 📁 Frontend File Structure
```
frontend/
├── src/
│   ├── pages/           # Main page components
│   │   ├── LiveRecording.tsx
│   │   ├── SessionList.tsx
│   │   └── SessionDetails.tsx
│   ├── components/      # Reusable components
│   │   ├── RecordingControls.tsx
│   │   ├── AudioPlayer.tsx
│   │   └── LiveTranscriptionDisplay.tsx
│   ├── contexts/        # React contexts
│   │   └── AuthContext.tsx
│   ├── config.ts        # API configuration
│   └── App.tsx          # Main app component
├── package.json
└── vite.config.ts
```

## 🎨 Styling Guidelines
- Use TailwindCSS classes
- Dark theme with purple accents
- Consistent spacing: `space-y-4` for vertical
- Card style: `bg-gray-800 rounded-lg p-6`
- Buttons: `bg-purple-600 hover:bg-purple-700`

## 🧪 Testing Components
```bash
# No tests currently implemented
# To add tests:
npm install --save-dev @testing-library/react vitest
npm run test
```

## 📝 Notes for AI Assistants

### DO:
- Use existing API endpoints (don't create new backend endpoints)
- Follow TailwindCSS styling patterns
- Handle loading and error states
- Use TypeScript (even if imperfect)
- Test changes in browser before committing

### DON'T:
- Modify backend code (this is frontend only)
- Create new API endpoints
- Use external dependencies without checking
- Ignore TypeScript errors completely
- Break existing working features

### Current Context:
- Recording system recently fixed to use database
- Sessions now persist properly
- Focus should be on displaying and playing back sessions
- Export features need PDF/DOCX support
- Search/filter functionality is missing

## 🔄 Recent Changes (January 14, 2025)
- Backend switched from in-memory to database storage
- Recording sessions now persist
- API endpoints confirmed working
- Need frontend updates to match

## 🎯 Next Steps
1. Fix SessionDetails page to display recordings
2. Implement audio playback with transcript sync
3. Add PDF/DOCX export
4. Implement search and filters
5. Fix TypeScript errors
6. Polish UI/UX

---

**For backend-specific work, refer to the main /CLAUDE.md file**