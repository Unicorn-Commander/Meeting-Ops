#!/bin/bash
# Create Local User Account in Authentik

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }

echo "Creating local user account in Authentik..."

# Default values
USERNAME="${1:-ucadmin}"
PASSWORD="${2:-MagicUnicorn!8-)}"
EMAIL="${3:-ucadmin@meeting-ops.local}"
NAME="${4:-UC Admin}"

print_info "Creating user: $USERNAME"

# Method 1: Via Authentik Web UI (Manual)
echo ""
echo "METHOD 1 - Via Web Interface (Recommended):"
echo "==========================================="
echo "1. Go to https://auth.meeting-ops.local/if/admin/"
echo "2. Login with your admin account"
echo "3. Navigate to Directory → Users"
echo "4. Click 'Create' button"
echo "5. Fill in:"
echo "   - Username: $USERNAME"
echo "   - Name: $NAME"
echo "   - Email: $EMAIL"
echo "   - Password: $PASSWORD"
echo "6. Check 'Is active'"
echo "7. Add to groups: 'Meeting-Ops-Users' or 'Meeting-Ops-Admins'"
echo "8. Click 'Create'"

echo ""
echo "METHOD 2 - Via Docker exec (Automated):"
echo "======================================="

# Create user via Django shell in Authentik container
cat > /tmp/create_user.py << EOF
from authentik.core.models import User, Group
from django.contrib.auth.hashers import make_password

# Create or update user
user, created = User.objects.update_or_create(
    username='$USERNAME',
    defaults={
        'email': '$EMAIL',
        'name': '$NAME',
        'is_active': True,
        'password': make_password('$PASSWORD')
    }
)

# Add to Meeting-Ops-Admins group
admin_group, _ = Group.objects.get_or_create(name='Meeting-Ops-Admins')
user.groups.add(admin_group)

# Also add to users group
users_group, _ = Group.objects.get_or_create(name='Meeting-Ops-Users')
user.groups.add(users_group)

print(f"User {'created' if created else 'updated'}: {user.username}")
print(f"Email: {user.email}")
print(f"Groups: {', '.join([g.name for g in user.groups.all()])}")
EOF

# Execute in container
print_info "Creating user in Authentik..."
docker exec -i authentik-server python -m authentik.root.shell < /tmp/create_user.py

rm /tmp/create_user.py

print_success "User account created successfully!"
echo ""
echo "Login credentials:"
echo "  URL: https://auth.meeting-ops.local"
echo "  Username: $USERNAME"
echo "  Password: $PASSWORD"
echo ""
echo "This is a REAL account - no mock/dummy authentication!"