#!/bin/bash
# Meeting-Ops Health Check Script

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Meeting-Ops Health Check"
echo "========================"

# Function to check service
check_service() {
    local service=$1
    local port=$2
    local name=$3
    
    echo -n "Checking $name... "
    
    if systemctl is-active --quiet $service; then
        echo -e "${GREEN}Running${NC}"
        
        # Check if port is listening
        if nc -z localhost $port 2>/dev/null; then
            echo "  - Port $port: ${GREEN}Open${NC}"
        else
            echo "  - Port $port: ${RED}Closed${NC}"
        fi
    else
        echo -e "${RED}Stopped${NC}"
    fi
}

# Function to check Docker container
check_container() {
    local container=$1
    local port=$2
    local name=$3
    
    echo -n "Checking $name... "
    
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -e "${GREEN}Running${NC}"
        
        # Check container health
        health=$(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null || echo "none")
        echo "  - Health: ${health}"
        
        # Check port
        if nc -z localhost $port 2>/dev/null; then
            echo "  - Port $port: ${GREEN}Open${NC}"
        else
            echo "  - Port $port: ${YELLOW}Internal only${NC}"
        fi
    else
        echo -e "${RED}Not running${NC}"
    fi
}

# Detect deployment type
if docker ps &>/dev/null && docker ps --format '{{.Names}}' | grep -q "unicorn-"; then
    echo "Deployment: Docker Compose"
    echo ""
    
    # Check Docker containers
    check_container "unicorn-backend" 9050 "Backend API"
    check_container "unicorn-frontend" 7777 "Frontend"
    
    # Check if Ollama is running
    if docker ps --format '{{.Names}}' | grep -q "ollama"; then
        check_container "ollama" 11434 "Ollama LLM"
    fi
    
else
    echo "Deployment: Bare Metal"
    echo ""
    
    # Check systemd service
    check_service "meeting-ops" 9050 "Meeting-Ops Service"
    
    # Check Ollama if installed
    if systemctl list-unit-files | grep -q "ollama.service"; then
        check_service "ollama" 11434 "Ollama LLM"
    fi
fi

echo ""
echo "System Resources:"
echo "-----------------"

# CPU usage
cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
echo "CPU Usage: ${cpu_usage}%"

# Memory usage
mem_total=$(free -m | awk '/^Mem:/{print $2}')
mem_used=$(free -m | awk '/^Mem:/{print $3}')
mem_percent=$(awk "BEGIN {printf \"%.1f\", ($mem_used/$mem_total)*100}")
echo "Memory: ${mem_used}MB / ${mem_total}MB (${mem_percent}%)"

# Disk usage
disk_usage=$(df -h /var/lib/meeting-ops 2>/dev/null || df -h / | awk 'NR==2 {print $5}')
echo "Disk Usage: ${disk_usage}"

# NPU Status
echo ""
echo "NPU Status:"
echo "-----------"
if [ -e "/dev/accel/accel0" ]; then
    echo -e "NPU Device: ${GREEN}Available${NC}"
    
    # Check if user has access
    if [ -r "/dev/accel/accel0" ] && [ -w "/dev/accel/accel0" ]; then
        echo -e "NPU Access: ${GREEN}OK${NC}"
    else
        echo -e "NPU Access: ${RED}Permission denied${NC}"
    fi
else
    echo -e "NPU Device: ${YELLOW}Not found${NC} (CPU mode)"
fi

# API Health Check
echo ""
echo "API Health:"
echo "-----------"

# Determine port based on deployment
if docker ps --format '{{.Names}}' | grep -q "unicorn-frontend"; then
    API_PORT=7776
else
    API_PORT=9050
fi

# Check API endpoint
echo -n "API Status: "
if curl -s http://localhost:${API_PORT}/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}Healthy${NC}"
    
    # Get session count
    sessions=$(curl -s http://localhost:${API_PORT}/api/recording-sessions | jq -r 'length' 2>/dev/null || echo "N/A")
    echo "Total Sessions: ${sessions}"
else
    echo -e "${RED}Unreachable${NC}"
fi

echo ""
echo "Health check complete!"