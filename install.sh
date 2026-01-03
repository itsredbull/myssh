#!/usr/bin/env bash
# installer - improved cross-distro install, consistent permissions, installs files into /usr/local/lib/ssh-vpn-pro
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ssh-vpn-pro"
BIN_WRAPPER="/usr/local/bin/ssh-vpn-pro"
ICON_FILE="$SCRIPT_DIR/vpn-icon.png"
DESKTOP_FILE="/usr/share/applications/ssh-vpn-pro.desktop"

if [ "$EUID" -ne 0 ]; then
    echo "This installer needs root. Re-run with sudo."
    echo "Example: sudo $0"
    exit 1
fi

echo "--- Pre-installation Cleanup ---"
# remove old files to ensure a clean install
rm -rf "/usr/local/lib/ssh-vpn-pro"
rm -f "/usr/local/bin/ssh-vpn-pro"
rm -f "/usr/share/applications/ssh-vpn-pro.desktop"
rm -f "/usr/share/pixmaps/ssh-vpn-pro.png"
echo "--- Cleanup Complete ---"
echo ""

echo "Installing SSH VPN Pro to $LIB_DIR ..."

# create lib dir
mkdir -p "$LIB_DIR"

# Copy Python files and resources into lib dir with predictable permissions
# - modules: 644
# - executables (main script, helper scripts): 755
for f in "$SCRIPT_DIR"/*.py; do
    [ -e "$f" ] || continue
    base="$(basename "$f")"
    if [ "$base" = "ssh_vpn_pro.py" ] || [ "$base" = "ssh_socks_simple.py" ]; then
        install -m 755 "$f" "$LIB_DIR/$base"
    else
        install -m 644 "$f" "$LIB_DIR/$base"
    fi
done

# Copy data files
if [ -f "$ICON_FILE" ]; then
    install -m 644 "$ICON_FILE" "$LIB_DIR/$(basename "$ICON_FILE")"
fi

# Create wrapper in /usr/local/bin that executes the program using files in /usr/local/lib/ssh-vpn-pro
cat > "$BIN_WRAPPER" <<'EOF'
#!/usr/bin/env bash
# wrapper to ensure vpn_core and helpers are on Python path
LIB_DIR="/usr/local/lib/ssh-vpn-pro"
export PYTHONPATH="$LIB_DIR:${PYTHONPATH:-}"
exec python3 "$LIB_DIR/ssh_vpn_pro.py" "$@"
EOF
chmod 755 "$BIN_WRAPPER"

# Install icon to system pixmaps
if [ -f "$ICON_FILE" ]; then
    mkdir -p /usr/share/pixmaps
    install -m 644 "$ICON_FILE" /usr/share/pixmaps/ssh-vpn-pro.png
    ICON_PATH="/usr/share/pixmaps/ssh-vpn-pro.png"
else
    ICON_PATH="network-vpn"
fi

# Desktop entry
mkdir -p /usr/share/applications
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SSH VPN Pro
GenericName=VPN Client
Comment=Secure SSH Tunnel VPN
Exec=/usr/local/bin/ssh-vpn-pro
Icon=$ICON_PATH
Terminal=false
Categories=Network;System;
Keywords=vpn;ssh;tunnel;proxy;security;network;
StartupNotify=true
EOF
chmod 644 "$DESKTOP_FILE"

echo "Files installed."

echo "Installing dependencies (attempting distro packages first where sensible)..."

# Helper: try distro package managers to install python-paramiko and python-pillow
if command -v pacman &>/dev/null; then
    pacman -Syu --noconfirm --needed python-paramiko python-pillow || true
elif command -v apt-get &>/dev/null; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3-paramiko python3-pil || true
elif command -v dnf &>/dev/null; then
    dnf install -y python3-paramiko python3-pillow || true
elif command -v zypper &>/dev/null; then
    zypper install -y python3-paramiko python3-pillow || true
else
    echo "No supported package manager found for distro packages. Will try pip for everything."
fi

# Ensure pip installed packages available (pystray plus any missing)
echo "Installing Python packages from requirements.txt via pip..."
python3 -m pip install --upgrade pip setuptools wheel 2>/dev/null || true
python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || true

echo "Installation complete. You can launch from the menu or run: ssh-vpn-pro"
