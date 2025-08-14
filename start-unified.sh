#!/bin/bash
# Meeting-Ops Unified Startup Script
# Works with both local auth and SSO configurations

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
echo "║              Starting Meeting-Ops Unified Stack              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check for .env file
if [ ! -f .env ]; then
    print_warning "No .env file found. Running authentication setup..."
    ./configure-auth.sh
    if [ ! -f .env ]; then
        print_error "Setup cancelled or failed"
        exit 1
    fi
fi

# Detect authentication mode
if grep -q "AUTHENTIK_SECRET_KEY" .env 2>/dev/null && ! grep -q "DEVELOPMENT_MODE=true" .env 2>/dev/null; then
    AUTH_MODE="SSO"
    COMPOSE_FILE="docker-compose-sso.yml"
elif grep -q "DEVELOPMENT_MODE=true" .env 2>/dev/null; then
    AUTH_MODE="DEVELOPMENT"
    COMPOSE_FILE="docker-compose-full-stack.yml"
else
    AUTH_MODE="LOCAL"
    COMPOSE_FILE="docker-compose-full-stack.yml"
fi

print_info "Authentication Mode: $AUTH_MODE"

# Start appropriate Docker stack
if [ "$AUTH_MODE" = "SSO" ]; then
    print_info "Starting SSO stack with Authentik and Traefik..."
    
    # Check if SSO compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        print_error "SSO compose file not found: $COMPOSE_FILE"
        print_info "Please ensure you have the complete SSO setup"
        exit 1
    fi
    
    # Create necessary directories for SSO
    mkdir -p authentik/{media,templates,certs}
    mkdir -p traefik
    
    # Start SSO services
    docker compose -f $COMPOSE_FILE up -d
    
    print_info "Waiting for Authentik to start (this may take a minute)..."
    sleep 30
    
    print_success "SSO services started"
    print_info "Access points:"
    echo "  - Application: https://meeting-ops.local"
    echo "  - API: https://api.meeting-ops.local"
    echo "  - Auth Portal: https://auth.meeting-ops.local"
    echo "  - Traefik Dashboard: https://traefik.meeting-ops.local:8080"
    
    print_warning "Make sure DNS is configured (run ./setup-dns.sh if needed)"
    
else
    print_info "Starting local authentication stack..."
    
    # Start regular Docker services
    docker compose -f $COMPOSE_FILE up -d
    
    print_info "Waiting for services to start..."
    
    # Wait for PostgreSQL
    for i in {1..30}; do
        if docker exec meetingops-postgres pg_isready -U meetingops &>/dev/null; then
            print_success "PostgreSQL ready"
            break
        fi
        if [ $i -eq 30 ]; then
            print_error "PostgreSQL failed to start"
            exit 1
        fi
        echo -n "."
        sleep 1
    done
    
    # Wait for Redis
    if docker exec meetingops-redis redis-cli ping &>/dev/null; then
        print_success "Redis ready"
    else
        print_warning "Redis not responding"
    fi
    
    print_success "Docker services started"
fi

# Start backend
print_info "Starting backend service..."
cd backend
./start-backend.sh &
BACKEND_PID=$!
cd ..

# Give backend time to start
sleep 5

# Check if backend is running
if kill -0 $BACKEND_PID 2>/dev/null; then
    print_success "Backend started (PID: $BACKEND_PID)"
else
    print_error "Backend failed to start"
    exit 1
fi

# Start frontend
print_info "Starting frontend service..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Give frontend time to start
sleep 5

# Check if frontend is running
if kill -0 $FRONTEND_PID 2>/dev/null; then
    print_success "Frontend started (PID: $FRONTEND_PID)"
else
    print_error "Frontend failed to start"
    exit 1
fi

echo ""
print_success "Meeting-Ops is running!"
echo ""

if [ "$AUTH_MODE" = "SSO" ]; then
    print_info "SSO Authentication Active"
    echo "  First-time setup:"
    echo "  1. Go to https://auth.meeting-ops.local"
    echo "  2. Complete Authentik setup wizard"
    echo "  3. Configure OAuth providers"
    echo "  4. Access app at https://meeting-ops.local"
elif [ "$AUTH_MODE" = "DEVELOPMENT" ]; then
    print_warning "DEVELOPMENT MODE - No real authentication!"
    echo "  Access: http://localhost:7777"
    echo "  Auto-authenticated as: dev-user (admin)"
else
    print_info "Local Authentication Active"
    echo "  Access: http://localhost:7777"
    echo "  Login: admin/admin123 or user/user123"
fi

echo ""
print_info "Services:"
echo "  Frontend: http://localhost:7777"
echo "  Backend API: http://localhost:9050/docs"
echo ""
print_info "To stop: Press Ctrl+C or run ./stop-stack.sh"

# Keep script running and handle shutdown
trap "echo ''; print_info 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; docker compose -f $COMPOSE_FILE down; exit" INT TERM

# Wait for processes
wait