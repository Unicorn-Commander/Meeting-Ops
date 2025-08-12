#!/bin/bash
# Meeting-Ops Installation Verification Script
# Tests all components and provides detailed diagnostics

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Counters
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNINGS=0

# Test results array
declare -a TEST_RESULTS

# Print functions
print_test() { 
    echo -e "${BLUE}[TEST]${NC} $1"
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
}

print_pass() { 
    echo -e "${GREEN}  ✓${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    TEST_RESULTS+=("PASS: $1")
}

print_fail() { 
    echo -e "${RED}  ✗${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    TEST_RESULTS+=("FAIL: $1")
}

print_warn() { 
    echo -e "${YELLOW}  ⚠${NC} $1"
    TESTS_WARNINGS=$((TESTS_WARNINGS + 1))
    TEST_RESULTS+=("WARN: $1")
}

print_info() { echo -e "${BLUE}  ℹ${NC} $1"; }

# Banner
echo -e "${PURPLE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         Meeting-Ops Installation Verification               ║"
echo "║              Comprehensive System Check                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# System Information
echo -e "${BLUE}System Information:${NC}"
echo "  OS: $(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo "  Kernel: $(uname -r)"
echo "  Architecture: $(uname -m)"
echo "  CPU: $(lscpu | grep "Model name" | cut -d':' -f2 | xargs)"
echo "  Memory: $(free -h | grep "^Mem" | awk '{print $2}') total"
echo "  Disk: $(df -h / | tail -1 | awk '{print $4}') available on /"
echo ""

# 1. Check Python Installation
print_test "Python Installation"
if command -v python3.13 >/dev/null 2>&1; then
    PY_VERSION=$(python3.13 --version | cut -d' ' -f2)
    print_pass "Python 3.13 installed ($PY_VERSION)"
    PYTHON_CMD="python3.13"
elif command -v python3.12 >/dev/null 2>&1; then
    PY_VERSION=$(python3.12 --version | cut -d' ' -f2)
    print_warn "Python 3.12 installed ($PY_VERSION) - 3.13 recommended"
    PYTHON_CMD="python3.12"
else
    print_fail "Python 3.12+ not found"
    PYTHON_CMD=""
fi

# 2. Check Node.js Installation
print_test "Node.js Installation"
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node --version)
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d'.' -f1 | sed 's/v//')
    if [ "$NODE_MAJOR" -ge 18 ]; then
        print_pass "Node.js $NODE_VERSION installed"
    else
        print_warn "Node.js $NODE_VERSION installed (v18+ recommended)"
    fi
else
    print_fail "Node.js not found"
fi

# 3. Check Docker Installation
print_test "Docker Installation"
if command -v docker >/dev/null 2>&1; then
    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | sed 's/,$//')
    print_pass "Docker $DOCKER_VERSION installed"
    
    # Check if user is in docker group
    if groups | grep -q docker; then
        print_pass "User in docker group"
    else
        print_warn "User not in docker group - may need sudo for docker commands"
    fi
else
    print_fail "Docker not found"
fi

# 4. Check PostgreSQL
print_test "PostgreSQL Database"
if systemctl is-active --quiet postgresql; then
    print_pass "PostgreSQL service running"
    
    # Test database connection
    if PGPASSWORD='MeetingOps2025!' psql -h localhost -U meetingops -d meeting_sessions -c '\q' 2>/dev/null; then
        print_pass "Database connection successful"
    else
        print_warn "Could not connect to database (may need initialization)"
    fi
else
    print_fail "PostgreSQL service not running"
fi

# 5. Check Redis
print_test "Redis Cache"
if systemctl is-active --quiet redis-server || systemctl is-active --quiet redis; then
    print_pass "Redis service running"
    
    # Test Redis connection
    if redis-cli ping 2>/dev/null | grep -q PONG; then
        print_pass "Redis connection successful"
    else
        print_warn "Could not connect to Redis"
    fi
else
    print_fail "Redis service not running"
fi

# 6. Check Nginx
print_test "Nginx Web Server"
if systemctl is-active --quiet nginx; then
    print_pass "Nginx service running"
    
    # Check configuration
    if sudo nginx -t 2>/dev/null; then
        print_pass "Nginx configuration valid"
    else
        print_warn "Nginx configuration has issues"
    fi
else
    print_fail "Nginx service not running"
fi

# 7. Check Backend Service
print_test "Backend API Service"
if systemctl is-active --quiet meeting-ops; then
    print_pass "Meeting-Ops backend service running"
else
    print_warn "Meeting-Ops backend service not running"
fi

# Test backend API
if curl -s http://localhost:9050/docs > /dev/null 2>&1; then
    print_pass "Backend API responding on port 9050"
    
    # Check API health
    if curl -s http://localhost:9050/api/health 2>/dev/null | grep -q "ok"; then
        print_pass "API health check passed"
    else
        print_info "API health endpoint not available"
    fi
else
    print_fail "Backend API not responding on port 9050"
fi

# 8. Check Frontend
print_test "Frontend Web Interface"
if curl -s http://localhost:7777 > /dev/null 2>&1; then
    print_pass "Frontend responding on port 7777"
    
    # Check if built files exist
    if [ -d "/opt/meeting-ops/frontend/dist" ]; then
        FILE_COUNT=$(find /opt/meeting-ops/frontend/dist -type f | wc -l)
        print_pass "Frontend built ($FILE_COUNT files)"
    else
        print_warn "Frontend build directory not found"
    fi
else
    print_fail "Frontend not responding on port 7777"
fi

# 9. Check Docker Services
print_test "Docker Services"

# Qdrant
if docker ps 2>/dev/null | grep -q meeting-ops-qdrant; then
    print_pass "Qdrant vector database running"
else
    print_warn "Qdrant not running (optional for semantic search)"
fi

# Ollama
if docker ps 2>/dev/null | grep -q meeting-ops-ollama; then
    print_pass "Ollama LLM service running"
    
    # Check available models
    MODELS=$(docker exec meeting-ops-ollama ollama list 2>/dev/null | tail -n +2 | wc -l || echo "0")
    if [ "$MODELS" -gt 0 ]; then
        print_pass "$MODELS LLM models available"
    else
        print_warn "No LLM models downloaded yet"
    fi
else
    print_warn "Ollama not running (required for AI features)"
fi

# 10. Check Audio System
print_test "Audio System"

# Check for audio devices
if command -v arecord >/dev/null 2>&1; then
    AUDIO_DEVICES=$(arecord -l 2>/dev/null | grep -c "card" || echo "0")
    if [ "$AUDIO_DEVICES" -gt 0 ]; then
        print_pass "$AUDIO_DEVICES audio recording devices found"
        
        # Check for USB microphone
        if arecord -l 2>/dev/null | grep -i usb; then
            print_pass "USB microphone detected"
        else
            print_warn "No USB microphone detected (using default audio device)"
        fi
    else
        print_warn "No audio recording devices found"
    fi
else
    print_fail "ALSA tools not installed (audio recording unavailable)"
fi

# 11. Check NPU Hardware
print_test "NPU Hardware Acceleration"

if [ -e "/dev/accel/accel0" ] || [ -e "/dev/npu0" ]; then
    print_pass "AMD NPU device detected"
    print_info "220x transcription speedup available!"
    
    # Check permissions
    if [ -r "/dev/accel/accel0" ] && [ -w "/dev/accel/accel0" ]; then
        print_pass "NPU device permissions OK"
    else
        print_warn "NPU device permissions may need adjustment"
    fi
elif lspci 2>/dev/null | grep -i "AMD.*AI" > /dev/null; then
    print_warn "AMD AI processor detected but NPU device not accessible"
    print_info "May need driver installation or kernel update"
else
    print_warn "No NPU hardware detected (CPU transcription will be used)"
fi

# 12. Check ROCm (for GPU acceleration)
print_test "ROCm GPU Acceleration"

if [ -d "/opt/rocm" ]; then
    if [ -x "/opt/rocm/bin/rocminfo" ]; then
        ROCM_VERSION=$(/opt/rocm/bin/rocminfo 2>/dev/null | grep "ROCm version" | head -1 | awk '{print $3}' || echo "unknown")
        print_pass "ROCm $ROCM_VERSION installed"
    else
        print_warn "ROCm directory found but tools not accessible"
    fi
else
    print_info "ROCm not installed (optional for GPU acceleration)"
fi

# 13. Check Whisper Models
print_test "Whisper Transcription Models"

WHISPER_DIR="/var/lib/meeting-ops/models/whisper"
if [ -d "$WHISPER_DIR" ]; then
    MODEL_COUNT=$(find "$WHISPER_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
    if [ "$MODEL_COUNT" -gt 0 ]; then
        print_pass "$MODEL_COUNT Whisper models installed"
        
        # Check for large-v3
        if [ -d "$WHISPER_DIR/large-v3" ]; then
            print_pass "Whisper large-v3 (recommended) installed"
        else
            print_warn "Whisper large-v3 not installed (best accuracy)"
        fi
    else
        print_warn "No Whisper models installed yet"
        print_info "Run: /opt/meeting-ops/download-models.sh"
    fi
else
    print_warn "Whisper models directory not found"
fi

# 14. Check File Permissions
print_test "File Permissions"

# Check installation directory
if [ -d "/opt/meeting-ops" ]; then
    OWNER=$(stat -c '%U' /opt/meeting-ops)
    if [ "$OWNER" = "$USER" ]; then
        print_pass "Installation directory owned by current user"
    else
        print_warn "Installation directory owned by $OWNER (expected $USER)"
    fi
else
    print_warn "Installation directory /opt/meeting-ops not found"
fi

# Check data directory
if [ -d "/var/lib/meeting-ops" ]; then
    if [ -w "/var/lib/meeting-ops" ]; then
        print_pass "Data directory writable"
    else
        print_warn "Data directory not writable"
    fi
else
    print_warn "Data directory /var/lib/meeting-ops not found"
fi

# 15. Network Connectivity
print_test "Network Connectivity"

# Check localhost connectivity
if ping -c 1 localhost > /dev/null 2>&1; then
    print_pass "Localhost connectivity OK"
else
    print_fail "Cannot ping localhost"
fi

# Check if ports are listening
for PORT in 7777 9050 5432 6379; do
    if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
        SERVICE=$(ss -tlnp 2>/dev/null | grep ":$PORT " | awk '{print $6}' | cut -d'"' -f2 | head -1)
        print_pass "Port $PORT listening${SERVICE:+ ($SERVICE)}"
    else
        if [ "$PORT" = "7777" ] || [ "$PORT" = "9050" ]; then
            print_fail "Port $PORT not listening (required)"
        else
            print_warn "Port $PORT not listening (optional)"
        fi
    fi
done

# 16. Test Authentication
print_test "Authentication System"

# Try to get JWT token
if command -v curl >/dev/null 2>&1; then
    TOKEN=$(curl -s -X POST http://localhost:9050/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin123"}' 2>/dev/null | \
        grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
    
    if [ -n "$TOKEN" ]; then
        print_pass "Authentication working (admin login successful)"
    else
        print_warn "Could not authenticate (default credentials may have been changed)"
    fi
else
    print_info "Skipping authentication test (curl not available)"
fi

# Summary
echo ""
echo -e "${PURPLE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${PURPLE}                        Test Summary                          ${NC}"
echo -e "${PURPLE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Total Tests:    ${TESTS_TOTAL}"
echo -e "Passed:         ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Failed:         ${RED}${TESTS_FAILED}${NC}"
echo -e "Warnings:       ${YELLOW}${TESTS_WARNINGS}${NC}"
echo ""

# Overall status
if [ "$TESTS_FAILED" -eq 0 ]; then
    if [ "$TESTS_WARNINGS" -eq 0 ]; then
        echo -e "${GREEN}✅ All tests passed! Meeting-Ops is fully operational.${NC}"
    else
        echo -e "${GREEN}✅ Meeting-Ops is operational with minor issues.${NC}"
        echo -e "${YELLOW}   Review warnings above for optional improvements.${NC}"
    fi
else
    echo -e "${RED}❌ Some critical tests failed. Meeting-Ops may not work properly.${NC}"
    echo -e "${RED}   Please review the failed tests above and run the installer again.${NC}"
fi

echo ""
echo -e "${BLUE}Quick Actions:${NC}"
echo -e "  • Start services:    ${GREEN}meeting-ops-start${NC}"
echo -e "  • Check status:      ${GREEN}meeting-ops-status${NC}"
echo -e "  • Download models:   ${GREEN}/opt/meeting-ops/download-models.sh${NC}"
echo -e "  • View logs:         ${GREEN}sudo journalctl -u meeting-ops -f${NC}"
echo -e "  • Access interface:  ${GREEN}http://localhost:7777${NC}"

# Save detailed report
REPORT_FILE="/tmp/meeting-ops-verification-$(date +%Y%m%d-%H%M%S).log"
{
    echo "Meeting-Ops Installation Verification Report"
    echo "Generated: $(date)"
    echo "==========================================="
    echo ""
    for result in "${TEST_RESULTS[@]}"; do
        echo "$result"
    done
} > "$REPORT_FILE"

echo ""
echo -e "${BLUE}Detailed report saved to: ${REPORT_FILE}${NC}"