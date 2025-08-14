#!/bin/bash
# Meeting-Ops Authentication Configuration Helper

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }

echo -e "${PURPLE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        Meeting-Ops Authentication Configuration              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo "Choose your authentication mode:"
echo ""
echo "1) Local Authentication (Simple JWT - default)"
echo "   - Username/password stored locally"
echo "   - Quick setup, no external dependencies"
echo "   - Good for testing and small deployments"
echo ""
echo "2) SSO with Authentik (Enterprise)"
echo "   - Local accounts (username/password in Authentik)"
echo "   - Office 365, Google Workspace, LDAP/AD"
echo "   - Centralized user management"
echo "   - Enterprise-grade security"
echo ""
echo "3) Development Mode (BYPASS - Not Recommended)"
echo "   - Skips authentication entirely"
echo "   - Auto-authenticates without password"
echo "   - ONLY for isolated development"
echo ""

read -p "Select mode [1-3]: " mode

case $mode in
    1)
        print_info "Configuring LOCAL authentication mode..."
        
        # Remove SSO configuration if present
        if [ -f .env ]; then
            grep -v "AUTHENTIK\|AZURE\|GOOGLE\|LDAP\|TRAEFIK" .env > .env.tmp || true
            mv .env.tmp .env
        fi
        
        # Ensure basic configuration
        if ! grep -q "DATABASE_URL" .env 2>/dev/null; then
            echo "DATABASE_URL=postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions" >> .env
        fi
        if ! grep -q "REDIS_URL" .env 2>/dev/null; then
            echo "REDIS_URL=redis://localhost:6379" >> .env
        fi
        
        print_success "Local authentication configured"
        print_info "Start with: ./start-meeting-ops.sh"
        print_info "Default users: admin/admin123, user/user123"
        ;;
        
    2)
        print_info "Configuring SSO authentication mode..."
        
        if [ ! -f .env.sso ]; then
            print_error ".env.sso template not found!"
            exit 1
        fi
        
        # Copy SSO template if no .env exists
        if [ ! -f .env ]; then
            print_info "Creating .env from SSO template..."
            cp .env.sso .env
            
            # Generate secure secret key
            print_info "Generating secure Authentik secret key..."
            SECRET=$(openssl rand -base64 32)
            sed -i "s/please-change-this-to-a-secure-random-key/$SECRET/g" .env
            
            print_success "SSO configuration created"
            print_warning "Please edit .env to add your OAuth provider credentials:"
            echo ""
            echo "  - AZURE_CLIENT_ID, AZURE_CLIENT_SECRET (for Office 365)"
            echo "  - GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET (for Google)"
            echo "  - LDAP settings (for Active Directory)"
            echo ""
            print_info "Then run: ./start-sso.sh"
        else
            print_warning ".env already exists. To switch to SSO:"
            echo "  1. Backup current .env: mv .env .env.backup"
            echo "  2. Copy SSO template: cp .env.sso .env"
            echo "  3. Edit .env with your OAuth credentials"
            echo "  4. Run: ./start-sso.sh"
        fi
        ;;
        
    3)
        print_info "Configuring DEVELOPMENT mode (mock auth)..."
        
        # Add development mode flag
        if ! grep -q "DEVELOPMENT_MODE" .env 2>/dev/null; then
            echo "DEVELOPMENT_MODE=true" >> .env
        else
            sed -i 's/DEVELOPMENT_MODE=.*/DEVELOPMENT_MODE=true/g' .env
        fi
        
        # Add minimal Authentik config to trigger SSO code path
        if ! grep -q "AUTHENTIK_SECRET_KEY" .env 2>/dev/null; then
            echo "AUTHENTIK_SECRET_KEY=dev-mode-key" >> .env
        fi
        
        print_success "Development mode configured"
        print_warning "⚠️  NO REAL AUTHENTICATION - Development only!"
        print_info "All requests authenticated as: dev-user (admin)"
        print_info "Start with: ./start-meeting-ops.sh"
        ;;
        
    *)
        print_error "Invalid selection"
        exit 1
        ;;
esac

echo ""
print_info "Current authentication configuration:"
echo ""

if grep -q "AUTHENTIK_SECRET_KEY" .env 2>/dev/null; then
    if grep -q "DEVELOPMENT_MODE=true" .env 2>/dev/null; then
        echo "  Mode: DEVELOPMENT (mock auth)"
    else
        echo "  Mode: SSO with Authentik"
        if grep -q "AZURE_CLIENT_ID=." .env 2>/dev/null; then
            echo "  - Office 365: Configured"
        fi
        if grep -q "GOOGLE_CLIENT_ID=." .env 2>/dev/null; then
            echo "  - Google Workspace: Configured"
        fi
        if grep -q "LDAP_SERVER_URI=ldap" .env 2>/dev/null && ! grep -q "your-domain-controller" .env 2>/dev/null; then
            echo "  - LDAP/AD: Configured"
        fi
    fi
else
    echo "  Mode: LOCAL (JWT authentication)"
fi

echo ""
print_success "Configuration complete!"