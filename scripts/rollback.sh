#!/bin/bash
# Enhanced Safe Rollback Script for Howdy
# Restores system installation from backup

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

BACKUP_DIR="/var/backups/howdy"
SYSTEM_HOWDY_DIR="/usr/lib/security/howdy"

print_msg() {
    echo -e "${GREEN}[ROLLBACK]${NC} $1"
}

print_err() {
    echo -e "${RED}[ERROR]${NC} $1"
}

if [ "$EUID" -ne 0 ]; then
  print_err "Please run as root"
  exit 1
fi

# Determine backup to restore
if [ -z "$1" ]; then
    # Find latest backup
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/howdy_system_backup_*.tar.gz 2>/dev/null | head -n1)
    
    if [ -z "$LATEST_BACKUP" ]; then
        print_err "No system backups found in $BACKUP_DIR"
        print_err "Try reinstalling howdy: sudo pacman -S howdy"
        exit 1
    fi
else
    LATEST_BACKUP="$BACKUP_DIR/howdy_system_backup_$1.tar.gz"
fi

if [ ! -f "$LATEST_BACKUP" ]; then
    print_err "Backup file not found: $LATEST_BACKUP"
    print_err ""
    print_err "Available backups:"
    ls -lh "$BACKUP_DIR"/howdy_system_backup_*.tar.gz 2>/dev/null || echo "  (no backups)"
    exit 1
fi

print_msg "Restoring from backup: $LATEST_BACKUP"

# Clean current installation
print_msg "Cleaning current directory $SYSTEM_HOWDY_DIR..."
if [ -d "$SYSTEM_HOWDY_DIR" ]; then
    rm -rf "$SYSTEM_HOWDY_DIR"
fi

# Unpack backup
print_msg "Unpacking archive..."
tar -xzf "$LATEST_BACKUP" -C "$(dirname $SYSTEM_HOWDY_DIR)"

# Restore permissions
chown -R root:root "$SYSTEM_HOWDY_DIR"
chmod -R 755 "$SYSTEM_HOWDY_DIR"
chmod 644 "$SYSTEM_HOWDY_DIR"/*.py 2>/dev/null || true
chmod 644 "$SYSTEM_HOWDY_DIR"/*.ini 2>/dev/null || true

print_msg "Restore completed successfully."
print_msg ""
print_msg "System Howdy installation restored from:"
print_msg "  $LATEST_BACKUP"
print_msg ""
print_msg "Try:"
print_msg "  sudo bash"
print_msg ""

exit 0
