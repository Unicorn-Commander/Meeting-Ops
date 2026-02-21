# Meeting-Ops Frontend Development Guide

## Quick Start
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0   # Dev server on port 7778
npm run build                    # Production build (has ~42 TS errors)
npm run test                     # Run vitest tests
```

**Login**: admin / admin123
**Backend**: http://localhost:9050

## Architecture

### Router (AppRouterSimplified.tsx)
| Route | Component | Purpose |
|-------|-----------|---------|
| /login | Login.tsx (component) | Authentication |
| /record | LiveRecording.tsx | Recording + live transcription |
| /sessions | Sessions.tsx | Session list + management |
| /sessions/:id | SessionDetails.tsx | Playback + transcript + export |
| /settings | SettingsEnhanced.tsx | System settings |
| /admin/agents | AgentDashboard.tsx | AI agent management |
| /admin/agents-old | AgentConfiguration.tsx | Legacy agent config |

### Shared Components (src/components/)
- `Login.tsx` - Login form
- `ErrorMessage.tsx` - Error display
- `LoadingSpinner.tsx` - Loading indicator
- `RecordingIndicator.tsx` - Global recording status
- `SessionCreator.tsx` - Session creation dialog
- `MeetingIntelligenceDashboard.tsx` - AI insights display

### Contexts
- `AuthContext.tsx` - JWT auth state + login/logout
- `ThemeContext.tsx` - Dark/light theme
- `RecordingContext.tsx` - Recording state

### Hooks
- `useKeyboardShortcuts.ts` - Keyboard shortcut handling

### Config
- `config.ts` - API URL construction (adapts to hostname)

## API Integration
```typescript
// Recording sessions
POST /api/simple/recording-sessions           // Create
POST /api/simple/recording-sessions/{id}/start // Start recording
POST /api/simple/recording-sessions/{id}/stop  // Stop recording
GET  /api/simple/recording-sessions           // List
GET  /api/simple/recording-sessions/{id}      // Get with transcript
GET  /api/simple/recording-sessions/{id}/download/audio  // WAV file

// WebSockets
ws://host:9050/ws/transcription/{session_id}  // Live transcription
ws://host:9050/ws/audio-levels                // Audio levels
ws://host:9050/ws/auto-summary/{session_id}   // AI summaries
```

## Known Issues
1. ~42 TypeScript build errors (functionality works despite errors)
2. Audio player path handling needs verification
3. No search/filter in session list
4. PDF/DOCX export not implemented
5. Not mobile-responsive

## Styling
- TailwindCSS with dark theme, purple accents
- Cards: `bg-gray-800 rounded-lg p-6`
- Buttons: `bg-purple-600 hover:bg-purple-700`
- Spacing: `space-y-4` vertical, `gap-4` grid

## File Structure
```
frontend/src/
  App.tsx                    # Root (ThemeContext + RecordingContext)
  AppRouterSimplified.tsx    # Router (AuthContext)
  config.ts                  # API URLs
  pages/
    LiveRecording.tsx
    Sessions.tsx
    SessionDetails.tsx
    SettingsEnhanced.tsx
    admin/
      AgentDashboard.tsx
      AgentConfiguration.tsx
      AgentEditor.tsx
  components/               # 6 shared components
  contexts/                 # 3 context providers
  hooks/                    # 1 hook
```
