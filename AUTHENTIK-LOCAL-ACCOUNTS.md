# Authentik Local Accounts (Real Authentication)

## What "Mock Auth" Actually Was
The "mock auth" or "development mode" was just a bypass that auto-authenticated everyone as "dev-user" without checking credentials. You're right to want REAL authentication instead!

## Real Local Accounts in Authentik

Authentik supports **real local user accounts** alongside SSO providers. These are:
- **Real accounts** with actual passwords
- **Stored securely** in Authentik's database  
- **Properly authenticated** with full security
- **Work alongside** Office 365, Google, LDAP logins

## Creating Local Accounts

### Option 1: Via Web Interface
1. Access Authentik admin: `https://auth.meeting-ops.local/if/admin/`
2. Go to **Directory → Users**
3. Click **Create**
4. Enter user details:
   - Username: `ucadmin`
   - Password: `MagicUnicorn!8-)`
   - Email: `ucadmin@meeting-ops.local`
   - Groups: `Meeting-Ops-Admins`

### Option 2: Via Script
```bash
# Create local user account
./create-authentik-user.sh ucadmin "MagicUnicorn!8-)" ucadmin@meeting-ops.local "UC Admin"
```

### Option 3: Bulk Import
Create multiple accounts from CSV:
```csv
username,email,name,password,groups
ucadmin,ucadmin@meeting-ops.local,UC Admin,MagicUnicorn!8-),Meeting-Ops-Admins
user1,user1@company.com,John Doe,SecurePass123!,Meeting-Ops-Users
user2,user2@company.com,Jane Smith,AnotherPass456!,Meeting-Ops-Users
```

## How Local Accounts Work

### Login Flow
1. User goes to `https://meeting-ops.local`
2. Traefik redirects to Authentik login page
3. User enters **local credentials** (not SSO)
4. Authentik validates password against its database
5. Authentik sets session cookie and headers
6. User is redirected back to app, fully authenticated

### Authentication Headers
Same headers for local and SSO users:
```
X-authentik-username: ucadmin
X-authentik-email: ucadmin@meeting-ops.local
X-authentik-name: UC Admin
X-authentik-groups: Meeting-Ops-Admins
```

## Removing Development Mode

To use ONLY real authentication (no mock/dev mode):

### Backend Configuration
Edit `.env` file:
```bash
# Remove or set to false
DEVELOPMENT_MODE=false

# Or just delete the line entirely
# (no DEVELOPMENT_MODE variable at all)
```

### Frontend Configuration
The frontend should NOT auto-login. Remove any dev bypasses:
```javascript
// DON'T DO THIS:
if (process.env.NODE_ENV === 'development') {
  autoLogin('dev-user'); // ❌ Remove this
}

// DO THIS INSTEAD:
// Always check real authentication headers
const user = getAuthHeaders();
if (!user) {
  redirectToLogin(); // ✅ Real login required
}
```

## Password Requirements

Authentik enforces password policies:
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 number
- Special characters recommended

Your password `MagicUnicorn!8-)` meets all requirements! ✅

## User Management

### Setting User Roles
In Authentik, assign users to groups:
- `Meeting-Ops-Admins` - Full admin access
- `Meeting-Ops-Managers` - Manager features
- `Meeting-Ops-Users` - Standard users
- `Meeting-Ops-Viewers` - Read-only access

### Password Reset
Users can reset passwords via:
1. "Forgot Password" link on login page
2. Admin can reset in Authentik interface
3. Self-service portal at `/if/user/`

## Security Benefits

Using real Authentik local accounts provides:
- **Password hashing** - Bcrypt/PBKDF2
- **Session management** - Secure cookies
- **Audit logging** - All logins tracked
- **MFA support** - TOTP, WebAuthn, SMS
- **Password policies** - Enforced complexity
- **Account lockout** - After failed attempts

## Testing Your Setup

1. Create the ucadmin account:
```bash
./create-authentik-user.sh ucadmin "MagicUnicorn!8-)"
```

2. Test login:
```bash
# Should redirect to login page
curl -I https://meeting-ops.local

# After login, should have auth headers
curl -I https://meeting-ops.local -H "Cookie: authentik_session=..."
```

3. Verify in app:
- Go to https://meeting-ops.local
- Login with ucadmin / MagicUnicorn!8-)
- Check user menu shows correct username
- Verify admin features are accessible

## Summary

**NO MOCK AUTHENTICATION NEEDED!** 

Authentik local accounts are:
- ✅ Real user accounts
- ✅ Secure password storage
- ✅ Proper authentication flow
- ✅ Work alongside SSO options
- ✅ Full audit trail
- ✅ Enterprise-grade security

Just create your `ucadmin` account with password `MagicUnicorn!8-)` and you have real, secure, local authentication!