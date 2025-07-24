#!/bin/bash
#
# Unicorn Commander Meeting Ops - Backup Script
# Creates comprehensive backups of all system data
#

set -e

# Configuration
INSTALL_DIR="/opt/unicorn-commander"
BACKUP_DIR="/opt/unicorn-commander/backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="unicorn_backup_$TIMESTAMP"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🦄 Unicorn Commander - Backup System${NC}"
echo "===================================="

# Create backup directory
mkdir -p $BACKUP_DIR

echo -e "${YELLOW}📦 Creating backup: $BACKUP_NAME${NC}"

# Create backup directory
CURRENT_BACKUP="$BACKUP_DIR/$BACKUP_NAME"
mkdir -p $CURRENT_BACKUP

# Stop services for consistent backup
echo -e "${YELLOW}⏸️  Stopping services for backup...${NC}"
systemctl stop unicorn-commander-backend.service || true

# Backup database
echo -e "${YELLOW}🗃️  Backing up database...${NC}"
if [ -f "$INSTALL_DIR/data/meeting_sessions.db" ]; then
    cp "$INSTALL_DIR/data/meeting_sessions.db" "$CURRENT_BACKUP/meeting_sessions.db"
    echo -e "${GREEN}✅ Database backup completed${NC}"
else
    echo -e "${YELLOW}⚠️  Database file not found${NC}"
fi

# Backup configuration
echo -e "${YELLOW}⚙️  Backing up configuration...${NC}"
cp "$INSTALL_DIR/.env" "$CURRENT_BACKUP/.env" 2>/dev/null || echo "No .env file found"
cp -r "$INSTALL_DIR/nginx" "$CURRENT_BACKUP/" 2>/dev/null || echo "No nginx config found"

# Backup audio files (sample only for large directories)
echo -e "${YELLOW}🎵 Backing up audio files...${NC}"
if [ -d "$INSTALL_DIR/storage" ]; then
    # For large storage, we'll create an index and backup recent files
    find "$INSTALL_DIR/storage" -type f -name "*.wav" -mtime -7 > "$CURRENT_BACKUP/recent_audio_files.txt"
    
    # Backup recent files (last 7 days)
    mkdir -p "$CURRENT_BACKUP/storage"
    while IFS= read -r file; do
        if [ -f "$file" ]; then
            rel_path=${file#$INSTALL_DIR/storage/}
            mkdir -p "$CURRENT_BACKUP/storage/$(dirname "$rel_path")"
            cp "$file" "$CURRENT_BACKUP/storage/$rel_path"
        fi
    done < "$CURRENT_BACKUP/recent_audio_files.txt"
    
    echo -e "${GREEN}✅ Recent audio files backed up${NC}"
else
    echo -e "${YELLOW}⚠️  Storage directory not found${NC}"
fi

# Backup system information
echo -e "${YELLOW}ℹ️  Collecting system information...${NC}"
cat > "$CURRENT_BACKUP/system_info.txt" << EOF
# Unicorn Commander Backup Information
Backup Date: $(date)
Hostname: $(hostname)
OS: $(lsb_release -d 2>/dev/null | cut -f2- || uname -a)
Python Version: $(python3 --version)
Node Version: $(node --version)
NPM Version: $(npm --version)

# Service Status
$(systemctl status unicorn-commander-backend.service --no-pager || echo "Service not found")

# Disk Usage
$(df -h $INSTALL_DIR)

# Audio Devices
$(arecord -l 2>/dev/null || echo "No audio devices found")
EOF

# Create metadata
cat > "$CURRENT_BACKUP/backup_metadata.json" << EOF
{
  "backup_name": "$BACKUP_NAME",
  "timestamp": "$TIMESTAMP",
  "date": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "version": "1.0",
  "components": {
    "database": $([ -f "$CURRENT_BACKUP/meeting_sessions.db" ] && echo "true" || echo "false"),
    "configuration": $([ -f "$CURRENT_BACKUP/.env" ] && echo "true" || echo "false"),
    "audio_files": $([ -d "$CURRENT_BACKUP/storage" ] && echo "true" || echo "false"),
    "system_info": true
  }
}
EOF

# Restart services
echo -e "${YELLOW}▶️  Restarting services...${NC}"
systemctl start unicorn-commander-backend.service

# Compress backup
echo -e "${YELLOW}🗜️  Compressing backup...${NC}"
cd $BACKUP_DIR
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"

# Get backup size
BACKUP_SIZE=$(du -h "${BACKUP_NAME}.tar.gz" | cut -f1)
echo -e "${GREEN}✅ Backup completed: ${BACKUP_NAME}.tar.gz ($BACKUP_SIZE)${NC}"

# Cleanup old backups
echo -e "${YELLOW}🧹 Cleaning up old backups (older than $RETENTION_DAYS days)...${NC}"
find $BACKUP_DIR -name "unicorn_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete
OLD_COUNT=$(find $BACKUP_DIR -name "unicorn_backup_*.tar.gz" | wc -l)
echo -e "${GREEN}✅ Cleanup completed. $OLD_COUNT backups retained.${NC}"

# List recent backups
echo -e "${BLUE}📋 Recent backups:${NC}"
ls -lh $BACKUP_DIR/unicorn_backup_*.tar.gz 2>/dev/null | tail -5 || echo "No backups found"

echo ""
echo -e "${GREEN}🎉 Backup process completed successfully!${NC}"
echo -e "${BLUE}📁 Backup location: $BACKUP_DIR/${BACKUP_NAME}.tar.gz${NC}"