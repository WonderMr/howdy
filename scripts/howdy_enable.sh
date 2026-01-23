#!/bin/bash
#
# Script to enable howdy in PAM
# Uncomments howdy lines
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

echo "🟢 Enabling howdy in PAM..."
echo ""

for pam_file in "${PAM_FILES[@]}"; do
    if [ -f "$pam_file" ]; then
        # Check if there's a commented howdy line
        if grep -q "^#auth.*pam_python\.so.*howdy" "$pam_file" 2>/dev/null; then
            echo "📝 Processing: $pam_file"
            # Create backup
            sudo cp "$pam_file" "${pam_file}.bak.${TIMESTAMP}"
            # Uncomment howdy line
            sudo sed -i "s/^#auth\(.*\)pam_python\.so\(.*\)howdy/auth\1pam_python.so\2howdy/" "$pam_file"
            echo "   ✓ Enabled (backup: ${pam_file}.bak.${TIMESTAMP})"
        else
            echo "⏭️  Skipping: $pam_file (already enabled or not found)"
        fi
    fi
done

echo ""
echo "✅ Howdy enabled in PAM"
echo "💡 To disable, run: ./howdy_disable.sh"
