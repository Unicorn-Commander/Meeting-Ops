#!/bin/bash
#
# Unicorn Commander Meeting Ops - Restore Script
# Restores system from backup archives
#

set -e

# Configuration
INSTALL_DIR="/opt/unicorn-commander"
BACKUP_DIR="/opt/unicorn-commander/backups"
USER="unicorn"
GROUP="unicorn"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🦄 Unicorn Commander - Restore System${NC}"
echo "===================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   exit 1
fi

# Function to list available backups
list_backups() {
    echo -e "${BLUE}📋 Available backups:${NC}"
    if [ ! -d "$BACKUP_DIR" ]; then
        echo -e "${RED}❌ Backup directory not found: $BACKUP_DIR${NC}"
        exit 1
    fi
    
    ls -lh $BACKUP_DIR/unicorn_backup_*.tar.gz 2>/dev/null || {
        echo -e "${RED}❌ No backup files found${NC}"
        exit 1
    }
}

# Function to restore from backup
restore_backup() {
    local backup_file="$1"
    
    if [ ! -f "$backup_file" ]; then
        echo -e "${RED}❌ Backup file not found: $backup_file${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}📦 Restoring from: $(basename $backup_file)${NC}"
    
    # Create temporary restore directory
    TEMP_DIR=$(mktemp -d)
    echo -e "${YELLOW}📁 Extracting to temporary directory: $TEMP_DIR${NC}"
    
    # Extract backup
    cd $(dirname $backup_file)
    tar -xzf "$backup_file" -C "$TEMP_DIR"
    
    # Find the backup directory inside
    BACKUP_CONTENT=$(find "$TEMP_DIR" -name "unicorn_backup_*" -type d | head -1)
    
    if [ ! -d "$BACKUP_CONTENT" ]; then
        echo -e "${RED}❌ Invalid backup structure${NC}"
        rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Show backup metadata
    if [ -f "$BACKUP_CONTENT/backup_metadata.json" ]; then
        echo -e "${BLUE}📋 Backup Information:${NC}"
        cat "$BACKUP_CONTENT/backup_metadata.json" | python3 -m json.tool 2>/dev/null || cat "$BACKUP_CONTENT/backup_metadata.json"
        echo ""
    fi
    
    # Confirm restore
    echo -e "${YELLOW}⚠️  This will overwrite current data. Continue? (y/N)${NC}"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}ℹ️  Restore cancelled${NC}"
        rm -rf "$TEMP_DIR"
        exit 0
    fi
    
    # Stop services
    echo -e "${YELLOW}⏸️  Stopping services...${NC}"
    systemctl stop unicorn-commander-backend.service || true
    
    # Backup current data
    CURRENT_BACKUP="$INSTALL_DIR/data/pre_restore_backup_$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}💾 Creating safety backup: $CURRENT_BACKUP${NC}"
    mkdir -p "$CURRENT_BACKUP"
    cp -r "$INSTALL_DIR/data" "$CURRENT_BACKUP/" 2>/dev/null || true
    cp "$INSTALL_DIR/.env" "$CURRENT_BACKUP/" 2>/dev/null || true
    
    # Restore database
    if [ -f "$BACKUP_CONTENT/meeting_sessions.db" ]; then
        echo -e "${YELLOW}🗃️  Restoring database...${NC}"
        mkdir -p "$INSTALL_DIR/data"
        cp "$BACKUP_CONTENT/meeting_sessions.db" "$INSTALL_DIR/data/"
        chown $USER:$GROUP "$INSTALL_DIR/data/meeting_sessions.db"
        echo -e "${GREEN}✅ Database restored${NC}"
    fi
    
    # Restore configuration
    if [ -f "$BACKUP_CONTENT/.env" ]; then
        echo -e "${YELLOW}⚙️  Restoring configuration...${NC}"
        cp "$BACKUP_CONTENT/.env" "$INSTALL_DIR/"
        chown $USER:$GROUP "$INSTALL_DIR/.env"
        echo -e "${GREEN}✅ Configuration restored${NC}"
    fi
    
    # Restore nginx configuration
    if [ -d "$BACKUP_CONTENT/nginx" ]; then
        echo -e "${YELLOW}🌐 Restoring nginx configuration...${NC}"
        cp -r "$BACKUP_CONTENT/nginx" "$INSTALL_DIR/"
        chown -R $USER:$GROUP "$INSTALL_DIR/nginx"
        echo -e "${GREEN}✅ Nginx configuration restored${NC}"
    fi
    
    # Restore audio files
    if [ -d "$BACKUP_CONTENT/storage" ]; then
        echo -e "${YELLOW}🎵 Restoring audio files...${NC}"
        mkdir -p "$INSTALL_DIR/storage"
        cp -r "$BACKUP_CONTENT/storage"/* "$INSTALL_DIR/storage/" 2>/dev/null || true
        chown -R $USER:$GROUP "$INSTALL_DIR/storage"
        echo -e "${GREEN}✅ Audio files restored${NC}"
    fi
    
    # Cleanup temporary directory
    rm -rf "$TEMP_DIR"
    
    # Start services
    echo -e "${YELLOW}▶️  Starting services...${NC}"
    systemctl start unicorn-commander-backend.service
    
    # Wait for service to start
    echo -e "${YELLOW}⏳ Waiting for services to start...${NC}"
    sleep 10
    
    # Test service
    if systemctl is-active --quiet unicorn-commander-backend.service; then
        echo -e "${GREEN}✅ Service started successfully${NC}"
        
        # Test API
        if curl -f -s http://localhost:9050/api/status > /dev/null; then
            echo -e "${GREEN}✅ API is responding${NC}"
        else
            echo -e "${YELLOW}⚠️  API may still be starting up${NC}"
        fi
    else
        echo -e "${RED}❌ Service failed to start${NC}"
        echo -e "${YELLOW}📋 Service status:${NC}"
        systemctl status unicorn-commander-backend.service --no-pager
    fi
    
    echo ""
    echo -e "${GREEN}🎉 Restore completed successfully!${NC}"
    echo -e "${BLUE}💾 Safety backup created at: $CURRENT_BACKUP${NC}"
    echo -e "${BLUE}🌐 Access the system at: http://$(hostname -I | awk '{print $1}')${NC}"
}

# Main script
if [ $# -eq 0 ]; then
    list_backups
    echo ""
    echo -e "${BLUE}Usage: $0 <backup_file.tar.gz>${NC}"
    echo -e "${BLUE}   or: $0 latest   # Restore from most recent backup${NC}"
    exit 0
fi

if [ "$1" = "latest" ]; then
    LATEST_BACKUP=$(ls -t $BACKUP_DIR/unicorn_backup_*.tar.gz 2>/dev/null | head -1)
    if [ -z "$LATEST_BACKUP" ]; then
        echo -e "${RED}❌ No backups found${NC}"
        exit 1
    fi
    restore_backup "$LATEST_BACKUP"
else
    # Check if it's a full path or just filename
    if [[ "$1" = /* ]]; then
        restore_backup "$1"
    else
        restore_backup "$BACKUP_DIR/$1"
    fi
fi