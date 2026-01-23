#!/bin/bash
#
# Script to disable howdy in PAM
# Creates backup files with timestamp before modification
#

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PAM_FILES=(
    "/etc/pam.d/kscreenlocker"
    "/etc/pam.d/lightdm"
    "/etc/pam.d/sddm"
    "/etc/pam.d/sudo"
    "/etc/pam.d/login"
    "/etc/pam.d/kde"
    "/etc/pam.d/system-login"
)

echo "🔴 Disabling howdy in PAM..."
echo ""

for pam_file in "${PAM_FILES[@]}"; do
    if [ -f "$pam_file" ]; then
        # Check if there's an active howdy line
        if grep -q "^auth.*pam_python\.so.*howdy" "$pam_file" 2>/dev/null; then
            echo "📝 Processing: $pam_file"
            # Create backup
            sudo cp "$pam_file" "${pam_file}.bak.${TIMESTAMP}"
            # Comment out howdy line
            sudo sed -i "s/^auth\(.*\)pam_python\.so\(.*\)howdy/#auth\1pam_python.so\2howdy/" "$pam_file"
            echo "   ✓ Disabled (backup: ${pam_file}.bak.${TIMESTAMP})"
        else
            echo "⏭️  Skipping: $pam_file (already disabled or not found)"
        fi
    fi
done

echo ""
echo "✅ Howdy disabled in PAM"
echo "💡 To enable, run: ./howdy_enable.sh"
