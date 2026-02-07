#!/bin/bash
# Enhanced Safe Deployment Script for Howdy
# Works with SYSTEM installation in /usr/lib/security/howdy

set -e

# Get script directory and repo root to fix path issues
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Paths - IMPORTANT: working with system installation
SYSTEM_HOWDY_DIR="/usr/lib/security/howdy"
BACKUP_DIR="/var/backups/howdy"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SRC_DIR="$REPO_ROOT/howdy/src"
GTK_SRC_DIR="$REPO_ROOT/howdy-gtk/src"
VENV_DIR="/tmp/howdy_test_venv"

print_msg() {
    echo -e "${GREEN}[DEPLOY]${NC} $1"
}

print_err() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

cleanup() {
    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
    fi
}

rollback() {
    print_err "Error detected! Starting rollback..."
    cleanup
    # Call rollback script with absolute path
    "$SCRIPT_DIR/rollback.sh" "$TIMESTAMP"
    exit 1
}

# Trap errors
trap 'rollback' ERR

# Check root
if [ "$EUID" -ne 0 ]; then
  print_err "Please run as root"
  exit 1
fi

print_warn "WARNING: This script will modify the SYSTEM Howdy installation"
print_warn "Directory: $SYSTEM_HOWDY_DIR"
print_warn "Backup will be created at: $BACKUP_DIR"
echo ""

# Determine where howdy-gtk is installed or should be installed
if [ -d "/usr/lib/security/howdy-gtk" ]; then
    SYSTEM_GTK_DIR="/usr/lib/security/howdy-gtk"
elif [ -d "/opt/howdy-gtk" ]; then
    SYSTEM_GTK_DIR="/opt/howdy-gtk"
else
    # Default location if not found
    SYSTEM_GTK_DIR="/usr/lib/security/howdy-gtk"
    print_warn "howdy-gtk not found, will install to $SYSTEM_GTK_DIR"
fi

# 1. Backup SYSTEM installation
print_msg "Creating backup of system Howdy installation..."
mkdir -p "$BACKUP_DIR"

if [ -d "$SYSTEM_HOWDY_DIR" ]; then
    # Save the ENTIRE directory
    tar -czf "$BACKUP_DIR/howdy_system_backup_$TIMESTAMP.tar.gz" -C "$(dirname $SYSTEM_HOWDY_DIR)" "$(basename $SYSTEM_HOWDY_DIR)"
    print_msg "Backup saved: $BACKUP_DIR/howdy_system_backup_$TIMESTAMP.tar.gz"
else
    print_err "System Howdy installation not found at $SYSTEM_HOWDY_DIR"
    print_err "Please install howdy first (e.g. via pacman)"
    exit 1
fi

if [ -d "$SYSTEM_GTK_DIR" ]; then
    tar -czf "$BACKUP_DIR/howdy_gtk_backup_$TIMESTAMP.tar.gz" -C "$(dirname $SYSTEM_GTK_DIR)" "$(basename $SYSTEM_GTK_DIR)"
    print_msg "GTK Backup saved: $BACKUP_DIR/howdy_gtk_backup_$TIMESTAMP.tar.gz"
fi


# 2. Setup test environment
print_msg "Preparing test environment..."
python3 -m venv --system-site-packages "$VENV_DIR"
source "$VENV_DIR/bin/activate"

print_msg "Installing test dependencies..."
pip install python-daemon lockfile numpy opencv-python-headless > /dev/null 2>&1 || {
    print_warn "Failed to install some dependencies"
}

# 2.5 Install runtime dependencies to system
# Note: On Arch Linux, use pacman instead: sudo pacman -S python-numpy python-opencv
print_msg "Runtime dependencies for howdy-gtk should be installed via system package manager"
print_msg "  Arch: sudo pacman -S python-numpy python-opencv"
print_msg "  Debian/Ubuntu: sudo apt install python3-numpy python3-opencv"

# 3. Check syntax BEFORE deploy
print_msg "Checking syntax of new files..."
if ! python3 -m compileall "$SRC_DIR" > /dev/null 2>&1; then
    print_err "Syntax error in source files!"
    cleanup
    exit 1
fi

# 4. Check imports in isolated environment
print_msg "Testing module imports..."

# Copy paths.py from system installation for testing
if [ -f "$SYSTEM_HOWDY_DIR/paths.py" ]; then
    cp "$SYSTEM_HOWDY_DIR/paths.py" "$SRC_DIR/paths.py"
    PATHS_COPIED=true
else
    print_warn "paths.py not found in system installation, skipping import tests"
    PATHS_COPIED=false
fi

if [ "$PATHS_COPIED" = true ]; then
    export PYTHONPATH="$SRC_DIR"
    if ! python3 -c "import liveness_detection; import model_daemon; import frequency_analyzer" 2>/dev/null; then
        print_err "Failed to import new modules!"
        python3 -c "import liveness_detection; import model_daemon; import frequency_analyzer" || true
        rm -f "$SRC_DIR/paths.py"
        cleanup
        exit 1
    fi
    
    # Remove temporary paths.py
    rm -f "$SRC_DIR/paths.py"
    print_msg "Import tests passed."
else
    print_msg "Skipped import tests (paths.py unavailable)."
fi

print_msg "Preliminary tests passed."

# 5. Patching system config for compatibility
print_msg "Checking and fixing configuration..."

# IMPORTANT: The canonical config location is /etc/howdy/config.ini
# pam.py reads from $SYSTEM_HOWDY_DIR/config.ini, so we need a symlink
CANONICAL_CONFIG="/etc/howdy/config.ini"
LOCAL_CONFIG="$SYSTEM_HOWDY_DIR/config.ini"

if [ -f "$CANONICAL_CONFIG" ]; then
    # Canonical config exists - ensure local config is a symlink to it
    if [ -L "$LOCAL_CONFIG" ]; then
        print_msg "Config symlink already exists"
    elif [ -f "$LOCAL_CONFIG" ]; then
        print_msg "Creating symlink: $LOCAL_CONFIG -> $CANONICAL_CONFIG"
        mv "$LOCAL_CONFIG" "$LOCAL_CONFIG.bak.$(date +%s)"
        ln -s "$CANONICAL_CONFIG" "$LOCAL_CONFIG"
    else
        print_msg "Creating symlink: $LOCAL_CONFIG -> $CANONICAL_CONFIG"
        ln -s "$CANONICAL_CONFIG" "$LOCAL_CONFIG"
    fi
    CONFIG_FILE="$CANONICAL_CONFIG"
else
    # No canonical config - use local config directly
    print_msg "Using local config: $LOCAL_CONFIG"
    CONFIG_FILE="$LOCAL_CONFIG"
fi

# Add missing options in [core] for compatibility
print_msg "Adding missing options to [core]..."

declare -A REQUIRED_OPTIONS=(
    ["disabled"]="false"
    ["ignore_ssh"]="true"
    ["ignore_closed_lid"]="true"
    ["detection_notice"]="false"
    ["suppress_unknown"]="false"
    ["no_confirmation"]="true"
)

for option in "${!REQUIRED_OPTIONS[@]}"; do
    if ! grep -q "^${option}\s*=" "$CONFIG_FILE"; then
        print_msg "  Adding option: $option = ${REQUIRED_OPTIONS[$option]}"
        sed -i "/^\[core\]/a ${option} = ${REQUIRED_OPTIONS[$option]}" "$CONFIG_FILE"
    fi
done

# Add [security] section if missing
if ! grep -q "\[security\]" "$CONFIG_FILE"; then
    print_msg "Adding [security] section..."
    cat >> "$CONFIG_FILE" << 'EOF'

[security]
# Anti-spoofing protection
liveness_check = false
security_level = medium
active_challenge = false
frequency_analysis = false
temporal_analysis = false
EOF
fi

# Add [daemon] section if missing
if ! grep -q "\[daemon\]" "$CONFIG_FILE"; then
    print_msg "Adding [daemon] section..."
    cat >> "$CONFIG_FILE" << 'EOF'

[daemon]
enabled = false
socket_path = /tmp/howdy_daemon.sock
preload_models = true
model_cache_size = 50
EOF
fi

print_msg "Configuration updated."

# Check camera config
if grep -q "^device_path = none" "$CONFIG_FILE"; then
    print_warn "⚠️  WARNING: device_path is not set!"
    print_warn "Found cameras:"
    v4l2-ctl --list-devices 2>/dev/null || ls -l /dev/video* 2>/dev/null || true
    print_warn ""
    print_warn "After deploy, configure camera using:"
    print_warn "  sudo nano $CONFIG_FILE"
    print_warn "Or automatically (example for /dev/video0):"
    print_warn "  sudo sed -i 's|device_path = none|device_path = /dev/video0|' $CONFIG_FILE"
fi

# 6. Deploy to system directory
print_msg "Copying new files to $SYSTEM_HOWDY_DIR..."

# Copy only new/modified Python files, leave config.ini and models alone
cp -f "$SRC_DIR/liveness_detection.py" "$SYSTEM_HOWDY_DIR/"
cp -f "$SRC_DIR/frequency_analyzer.py" "$SYSTEM_HOWDY_DIR/"
cp -f "$SRC_DIR/model_daemon.py" "$SYSTEM_HOWDY_DIR/"
cp -f "$SRC_DIR/compare.py" "$SYSTEM_HOWDY_DIR/"
# Update CLI to include --plain flag support
cp -f "$SRC_DIR/cli.py" "$SYSTEM_HOWDY_DIR/"
# Copy CLI subcommands
cp -rf "$SRC_DIR/cli" "$SYSTEM_HOWDY_DIR/"
# Copy recorders (video_capture.py with USB wake fix)
cp -rf "$SRC_DIR/recorders" "$SYSTEM_HOWDY_DIR/"
# Copy PAM toggle script and wrapper
if [ -f "$SRC_DIR/pam_toggle.py" ]; then
    cp -f "$SRC_DIR/pam_toggle.py" "$SYSTEM_HOWDY_DIR/"
    chmod 755 "$SYSTEM_HOWDY_DIR/pam_toggle.py"
    print_msg "PAM toggle script installed"
fi

if [ -f "$SRC_DIR/pam_toggle_wrapper.c" ]; then
    # Compile C wrapper for better pkexec compatibility
    print_msg "Compiling PAM toggle wrapper..."
    gcc "$SRC_DIR/pam_toggle_wrapper.c" -o "/usr/bin/howdy-pam-toggle"
    chmod 755 "/usr/bin/howdy-pam-toggle"
    print_msg "PAM toggle binary wrapper installed to /usr/bin/howdy-pam-toggle"
elif [ -f "$SRC_DIR/pam-toggle-wrapper.sh" ]; then
    # Fallback to bash wrapper
    cp -f "$SRC_DIR/pam-toggle-wrapper.sh" "/usr/bin/howdy-pam-toggle"
    chmod 755 "/usr/bin/howdy-pam-toggle"
    print_msg "PAM toggle bash wrapper installed to /usr/bin/howdy-pam-toggle"
fi

# Set permissions RECURSIVELY
print_msg "Setting permissions..."

find "$SYSTEM_HOWDY_DIR" -type d -exec chmod 755 {} \;
find "$SYSTEM_HOWDY_DIR" -type f -name "*.py" -exec chmod 644 {} \;

# CRITICAL: cli.py, pam_toggle.py and wrapper must be executable
chmod 755 "$SYSTEM_HOWDY_DIR/cli.py" 2>/dev/null || true
chmod 755 "$SYSTEM_HOWDY_DIR/pam_toggle.py" 2>/dev/null || true
# Wrapper is now in /usr/bin, chmod handled during install

# Set permissions for other files (exclude .sh scripts)
find "$SYSTEM_HOWDY_DIR" -type f ! -name "*.py" ! -name "*.dat" ! -name "*.sh" -exec chmod 644 {} \;

chown -R root:root "$SYSTEM_HOWDY_DIR"

# CRITICAL: dlib data permissions
find "$SYSTEM_HOWDY_DIR/dlib-data" -type f -name "*.dat" -exec chmod 644 {} \; 2>/dev/null || true

# User models permissions
find "$SYSTEM_HOWDY_DIR/models" -type f -name "*.dat" -exec chmod 644 {} \; 2>/dev/null || true

print_msg "Files copied, permissions set."

# 6.4 Install polkit policy for pam_toggle.py
print_msg "Installing polkit policy..."
if [ -f "$REPO_ROOT/howdy/polkit/org.freedesktop.policykit.pkexec.run-howdy-pam-toggle.policy" ]; then
    cp -f "$REPO_ROOT/howdy/polkit/org.freedesktop.policykit.pkexec.run-howdy-pam-toggle.policy" \
        /usr/share/polkit-1/actions/
    chmod 644 /usr/share/polkit-1/actions/org.freedesktop.policykit.pkexec.run-howdy-pam-toggle.policy
    print_msg "✓ Polkit policy installed"
else
    print_warn "Polkit policy file not found, skipping"
fi

if [ -f "$REPO_ROOT/howdy/polkit/50-howdy-pam-toggle.rules" ]; then
    cp -f "$REPO_ROOT/howdy/polkit/50-howdy-pam-toggle.rules" \
        /etc/polkit-1/rules.d/
    chmod 644 /etc/polkit-1/rules.d/50-howdy-pam-toggle.rules
    print_msg "✓ Polkit rules installed"
fi

# 6.5 Deploy GTK Interface
print_msg "Deploying GTK interface to $SYSTEM_GTK_DIR..."

mkdir -p "$SYSTEM_GTK_DIR"

# Copy python files
cp -f "$GTK_SRC_DIR"/*.py "$SYSTEM_GTK_DIR/"
# Copy UI files and images
cp -f "$GTK_SRC_DIR"/*.glade "$SYSTEM_GTK_DIR/"
cp -f "$GTK_SRC_DIR"/*.png "$SYSTEM_GTK_DIR/"

# Generate paths.py for system installation
cat > "$SYSTEM_GTK_DIR/paths.py" << EOF
import os
from pathlib import PurePath

# System paths
config_dir = PurePath("$SYSTEM_HOWDY_DIR")
dlib_data_dir = PurePath("$SYSTEM_HOWDY_DIR/dlib-data")
user_models_dir = PurePath("$SYSTEM_HOWDY_DIR/models")

# Local paths (GTK resources are in the same directory)
data_dir = PurePath(os.path.dirname(os.path.realpath(__file__)))
EOF

# Set permissions for GTK
find "$SYSTEM_GTK_DIR" -type d -exec chmod 755 {} \;
find "$SYSTEM_GTK_DIR" -type f -exec chmod 644 {} \;

# Create launcher script
LAUNCHER="/usr/bin/howdy-gtk"
cat > "$LAUNCHER" << EOF
#!/bin/bash
cd "$SYSTEM_GTK_DIR"
exec python3 init.py "\$@"
EOF
chmod 755 "$LAUNCHER"

# Install Desktop Entry
if [ -d "/usr/share/applications" ]; then
    cp -f "$REPO_ROOT/howdy-gtk/howdy-gtk-tray.desktop" "/usr/share/applications/"
    chmod 644 "/usr/share/applications/howdy-gtk-tray.desktop"
fi

print_msg "GTK interface deployed."

# 7. Verify system installation
print_msg "Testing system installation..."

cd "$SYSTEM_HOWDY_DIR"
if ! python3 -c "import sys; sys.path.insert(0, '$SYSTEM_HOWDY_DIR'); import liveness_detection; import frequency_analyzer; print('New modules OK')" 2>/dev/null; then
    print_err "New modules failed to load in system installation!"
    python3 -c "import sys; sys.path.insert(0, '$SYSTEM_HOWDY_DIR'); import liveness_detection; import frequency_analyzer" || true
    exit 1
fi

if ! python3 -c "import sys; sys.path.insert(0, '$SYSTEM_HOWDY_DIR'); from recorders.video_capture import VideoCapture; print('Old modules OK')" 2>/dev/null; then
    print_warn "Old modules might be incompatible, but proceeding..."
fi

print_msg "System installation is operational."

trap - ERR
cleanup

# Restart howdy-gtk to load new version
print_msg "Restarting howdy-gtk..."

# Kill all howdy-gtk processes (running as user)
# Process names are "python3 init.py --minimized" or "python3 init.py --start-auth-ui"
if [ -n "$SUDO_USER" ]; then
    pkill -u "$SUDO_USER" -f "init.py --minimized" 2>/dev/null || true
    pkill -u "$SUDO_USER" -f "init.py --start-auth-ui" 2>/dev/null || true
    pkill -u "$SUDO_USER" -f "howdy-gtk" 2>/dev/null || true
else
    pkill -f "init.py --minimized" 2>/dev/null || true
    pkill -f "init.py --start-auth-ui" 2>/dev/null || true
fi

sleep 1

# Check if any howdy-gtk still running
remaining=$(pgrep -c -f "init.py --(minimized|start-auth-ui)" 2>/dev/null || echo "0")
if [ "$remaining" -gt 0 ]; then
    print_warn "$remaining howdy-gtk process(es) still running"
    print_warn "Kill them manually: pkill -f 'init.py --'"
fi

# Check if user wants to auto-start
if pgrep -u "$SUDO_USER" -x "plasmashell\|gnome-shell\|xfce4-panel" > /dev/null 2>&1; then
    print_msg "Desktop environment detected, you can start howdy-gtk manually:"
    print_msg "  howdy-gtk --minimized &"
fi

print_msg "=========================================="
print_msg "Deployment successfully completed!"
print_msg "=========================================="
print_msg ""
print_msg "New modules installed in: $SYSTEM_HOWDY_DIR"
print_msg "Backup: $BACKUP_DIR/howdy_system_backup_$TIMESTAMP.tar.gz"
print_msg ""
print_msg "To rollback, use:"
print_msg "  sudo $SCRIPT_DIR/rollback.sh $TIMESTAMP"
print_msg ""
print_msg "To enable new features edit:"
print_msg "  sudo nano $SYSTEM_HOWDY_DIR/config.ini"
print_msg ""
print_msg "Add to the end of file:"
print_msg ""
print_msg "[security]"
print_msg "liveness_check = true"
print_msg "security_level = medium"
print_msg "active_challenge = true"
print_msg "frequency_analysis = true"
print_msg ""
