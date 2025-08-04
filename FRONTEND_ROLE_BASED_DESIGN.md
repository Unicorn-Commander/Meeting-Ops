# Meeting-Ops Frontend Role-Based Design

## Overview
The frontend will have different interfaces based on user roles, with progressive feature access from viewer to superuser.

## Role Hierarchy & Permissions

### 1. **Viewer Role** (Read-only access)
- View recorded sessions
- Play audio recordings
- Read transcriptions
- Download allowed files
- View basic analytics (if permitted)

### 2. **User Role** (Standard user)
- All Viewer permissions plus:
- Create new recording sessions
- Start/stop/pause recordings
- Upload audio files
- Edit own sessions
- Delete own sessions
- Generate transcriptions
- Use AI features (transcription, summarization)

### 3. **Manager Role** (Team lead)
- All User permissions plus:
- View all sessions in organization
- Access analytics dashboard
- Manage team sessions
- Export bulk data
- Configure AI models
- Send email summaries
- View organization usage

### 4. **Admin Role** (Organization admin)
- All Manager permissions plus:
- User management (create, activate, deactivate)
- Organization settings
- Storage management
- Integration configuration
- Backup/restore operations
- View audit logs
- Configure webhooks

### 5. **Superuser Role** (System admin)
- All Admin permissions plus:
- Hardware configuration
- NPU management
- System monitoring
- Network configuration
- SSL certificate management
- Database administration
- Multi-organization management

## Layout Structure

### Common Components (All Roles)
```
Header
├── Logo & App Name
├── User Profile Menu
│   ├── Profile Settings
│   ├── Change Password
│   └── Logout
└── Role Indicator Badge

Sidebar
├── Dashboard (role-specific)
├── Sessions (with role-based filtering)
└── Help & Documentation
```

### Role-Specific Layouts

#### 1. Viewer Dashboard
```
Main Content Area
├── Recent Sessions List (read-only)
│   ├── Session Title
│   ├── Date/Duration
│   ├── Play Audio Button
│   └── View Transcript Button
├── Search & Filter
└── Audio Player Component
```

#### 2. User Dashboard
```
Main Content Area
├── Quick Actions Panel
│   ├── Start New Recording
│   ├── Upload Audio File
│   └── Recent Sessions
├── Active Recording Control
│   ├── Record/Pause/Stop
│   ├── Audio Level Meter
│   └── Live Transcription View
├── My Sessions Grid
│   ├── Session Cards
│   ├── Edit/Delete Actions
│   └── Export Options
└── Usage Statistics (personal)
```

#### 3. Manager Dashboard
```
Main Content Area
├── Team Overview
│   ├── Active Recordings
│   ├── Team Members Status
│   └── Today's Sessions
├── Analytics Dashboard
│   ├── Meeting Trends
│   ├── Speaker Analytics
│   ├── AI Usage Metrics
│   └── Export Reports
├── Team Sessions Management
│   ├── All Sessions Table
│   ├── Bulk Actions
│   └── Advanced Filters
└── AI Model Selection
```

#### 4. Admin Dashboard
```
Main Content Area
├── Organization Overview
│   ├── Usage Metrics
│   ├── Storage Status
│   └── Active Users
├── Admin Quick Actions
│   ├── Add User
│   ├── System Backup
│   └── View Audit Logs
├── Management Sections
│   ├── User Management
│   ├── Settings Management
│   ├── Integration Config
│   └── Email Templates
└── System Health Monitor
```

#### 5. Superuser Dashboard
```
Main Content Area
├── System Status Panel
│   ├── NPU Status & Metrics
│   ├── CPU/Memory Usage
│   ├── Network Status
│   └── Service Health
├── Hardware Control
│   ├── NPU Configuration
│   ├── Audio Device Settings
│   ├── Performance Tuning
│   └── Diagnostic Tools
├── Multi-Org Management
│   ├── Organization List
│   ├── Usage by Org
│   └── Billing/Quotas
└── Advanced Administration
    ├── Database Tools
    ├── Log Viewer
    ├── SSL Management
    └── System Updates
```

## Navigation Structure

### Viewer Menu
- Dashboard
- Sessions (Browse)
- Help

### User Menu
- Dashboard
- Record
- My Sessions
- Upload
- Help

### Manager Menu
- Dashboard
- Record
- Sessions
  - My Sessions
  - Team Sessions
- Analytics
- AI Models
- Reports
- Help

### Admin Menu
- Dashboard
- Record
- Sessions
- Analytics
- Administration
  - Users
  - Settings
  - Integrations
  - Audit Logs
- Backup & Restore
- Help

### Superuser Menu
- Dashboard
- System Monitor
- Hardware
  - NPU Control
  - Audio Devices
  - Network
- Organizations
- Administration
  - Users
  - Settings
  - Database
  - Logs
- Maintenance
  - Backup/Restore
  - SSL/Security
  - Updates
- Help

## Key Features by Role

### Recording Features
| Feature | Viewer | User | Manager | Admin | Superuser |
|---------|--------|------|---------|-------|-----------|
| View Recordings | ✓ | ✓ | ✓ | ✓ | ✓ |
| Start Recording | ✗ | ✓ | ✓ | ✓ | ✓ |
| Edit Own Sessions | ✗ | ✓ | ✓ | ✓ | ✓ |
| Edit All Sessions | ✗ | ✗ | ✓ | ✓ | ✓ |
| Delete Sessions | ✗ | Own | All | All | All |

### AI Features
| Feature | Viewer | User | Manager | Admin | Superuser |
|---------|--------|------|---------|-------|-----------|
| View Transcriptions | ✓ | ✓ | ✓ | ✓ | ✓ |
| Generate Transcriptions | ✗ | ✓ | ✓ | ✓ | ✓ |
| Configure AI Models | ✗ | ✗ | ✓ | ✓ | ✓ |
| NPU Management | ✗ | ✗ | ✗ | ✗ | ✓ |

### Administrative Features
| Feature | Viewer | User | Manager | Admin | Superuser |
|---------|--------|------|---------|-------|-----------|
| View Analytics | ✗ | Own | Team | All | All |
| User Management | ✗ | ✗ | ✗ | ✓ | ✓ |
| System Settings | ✗ | ✗ | ✗ | ✓ | ✓ |
| Hardware Config | ✗ | ✗ | ✗ | ✗ | ✓ |
| Multi-Org Mgmt | ✗ | ✗ | ✗ | ✗ | ✓ |

## Implementation Notes

1. **Authentication Flow**
   - Login returns user object with role
   - Store role in context/state
   - Use role to determine component visibility

2. **Component Guards**
   ```typescript
   <RoleGuard allowedRoles={['admin', 'superuser']}>
     <AdminPanel />
   </RoleGuard>
   ```

3. **API Integration**
   - Include auth token in all requests
   - Handle 403 Forbidden gracefully
   - Show appropriate error messages

4. **Progressive Enhancement**
   - Start with viewer features
   - Layer on additional features by role
   - Shared components with role-based props

5. **Mobile Considerations**
   - Responsive design for all roles
   - Touch-friendly recording controls
   - Simplified navigation for mobile