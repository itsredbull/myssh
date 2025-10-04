#!/bin/bash
# SSH VPN Pro - Complete Installer
# Works on all Linux distros

set -e

echo "╔════════════════════════════════════════════════╗"
echo "║       SSH VPN Pro - Installation Script       ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run with sudo:"
    echo "   sudo ./install.sh"
    exit 1
fi

echo "✅ Running as root - system-wide install"
echo ""

# Detect package manager
if command -v apt &> /dev/null; then
    PKG="apt"
    echo "📦 Detected: Debian/Ubuntu/Mint/Pop!_OS"
elif command -v pacman &> /dev/null; then
    PKG="pacman"
    echo "📦 Detected: Arch/Manjaro/EndeavourOS"
elif command -v dnf &> /dev/null; then
    PKG="dnf"
    echo "📦 Detected: Fedora/RHEL 8+/AlmaLinux/Rocky"
elif command -v yum &> /dev/null; then
    PKG="yum"
    echo "📦 Detected: CentOS/RHEL 7/Oracle Linux"
elif command -v zypper &> /dev/null; then
    PKG="zypper"
    echo "📦 Detected: openSUSE/SLES"
elif command -v apk &> /dev/null; then
    PKG="apk"
    echo "📦 Detected: Alpine Linux"
else
    echo "❌ Unsupported Linux distribution"
    echo "   Supported: Debian, Ubuntu, Arch, Fedora, RHEL, CentOS, openSUSE, Alpine"
    echo "   You can manually install: python3, python3-tk, openssh-client, badvpn"
    exit 1
fi
echo ""

# Remove old installations from SYSTEM only
echo "🗑️  Removing old system installations..."

# Remove system files ONLY (safe for fresh installs)
rm -f /usr/local/bin/ssh-vpn-pro 2>/dev/null || true
rm -f /usr/local/bin/vpn_core.py 2>/dev/null || true
rm -rf /usr/local/bin/__pycache__ 2>/dev/null || true
rm -f /usr/share/applications/ssh-vpn-pro.desktop 2>/dev/null || true
rm -f /usr/share/applications/SSH\ VPN\ Pro.desktop 2>/dev/null || true
rm -f /usr/share/applications/ssh_vpn_pro.desktop 2>/dev/null || true

# Kill any running instances
pkill -f "ssh_vpn.*\.py" 2>/dev/null || true
pkill -f "ssh-vpn-pro" 2>/dev/null || true

echo "   Cleaned up old system files"
echo ""

# Install system dependencies
echo "📥 Installing system dependencies..."
echo ""

case $PKG in
    apt)
        apt update -qq
        apt install -y \
            python3 \
            python3-tk \
            python3-pip \
            openssh-client \
            sshpass \
            badvpn \
            stunnel4 \
            policykit-1 \
            iproute2 \
            iptables \
            gnome-shell-extension-appindicator 2>&1 | grep -v "is already" || true
        # Enable GNOME extension for system tray icons
        if command -v gnome-extensions &> /dev/null; then
            gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
        fi
        ;;
    pacman)
        pacman -Sy --noconfirm \
            python \
            python-pip \
            tk \
            openssh \
            badvpn \
            stunnel \
            polkit \
            iproute2 \
            iptables \
            expect \
            gnome-shell-extension-appindicator 2>&1 | grep -v "is up to date" || true

        # Fix OpenSSL version mismatch on Arch
        echo "🔧 Checking for OpenSSL/SSH compatibility..."
        if ssh -V 2>&1 | grep -q "OpenSSL version mismatch"; then
            echo "⚠️  Detected OpenSSL version mismatch - rebuilding openssh..."
            pacman -S --noconfirm openssh 2>&1 | grep -v "is up to date" || true
        fi

        # Enable GNOME extension for system tray icons
        if command -v gnome-extensions &> /dev/null; then
            gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
        fi
        ;;
    dnf)
        dnf install -y \
            python3 \
            python3-tkinter \
            python3-pip \
            openssh-clients \
            badvpn \
            stunnel \
            polkit \
            iproute \
            iptables \
            gnome-shell-extension-appindicator 2>&1 | grep -v "already installed" || true
        # Enable GNOME extension for system tray icons
        if command -v gnome-extensions &> /dev/null; then
            gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
        fi
        ;;
    yum)
        yum install -y \
            python3 \
            python3-tkinter \
            python3-pip \
            openssh-clients \
            stunnel \
            polkit \
            iproute \
            iptables 2>&1 | grep -v "already installed" || true
        echo "⚠️  Note: badvpn may need manual install on older systems"
        echo "⚠️  Note: For GNOME tray icons, install appindicator extension manually"
        ;;
    zypper)
        zypper refresh
        zypper install -y \
            python3 \
            python3-tk \
            python3-pip \
            openssh \
            badvpn \
            stunnel \
            polkit \
            iproute2 \
            iptables \
            gnome-shell-extension-appindicator 2>&1 | grep -v "already installed" || true
        # Enable GNOME extension for system tray icons
        if command -v gnome-extensions &> /dev/null; then
            gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
        fi
        ;;
    apk)
        apk update
        apk add \
            python3 \
            py3-tkinter \
            py3-pip \
            openssh-client \
            badvpn \
            stunnel \
            polkit \
            iproute2 \
            iptables 2>&1 | grep -v "already installed" || true
        echo "⚠️  Note: For GNOME tray icons, install appindicator extension manually"
        ;;
esac

echo ""
echo "✅ System packages installed"
echo ""

# Get script directory (need this before installing Python packages)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_FILE="$SCRIPT_DIR/ssh_vpn_pro.py"
ICON_FILE="$SCRIPT_DIR/vpn-icon.png"

# Install Python packages
echo "🐍 Installing Python packages..."
pip3 install --upgrade pip 2>&1 | tail -1 || true

# Install from requirements.txt if available, otherwise install directly
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    pip3 install -r "$SCRIPT_DIR/requirements.txt" 2>&1 | tail -1 || true
else
    pip3 install Pillow pystray 2>&1 | tail -1 || true
fi
echo "✅ Python packages installed"
echo ""

# Check if app exists
if [ ! -f "$APP_FILE" ]; then
    echo "❌ Error: ssh_vpn_pro.py not found!"
    echo "   Expected at: $APP_FILE"
    exit 1
fi

# Make app executable
chmod +x "$APP_FILE"
echo "✅ Made app executable"
echo ""

# Copy app AND vpn_core to /usr/local/bin
echo "📂 Installing to /usr/local/bin..."
cp "$APP_FILE" /usr/local/bin/ssh-vpn-pro
chmod +x /usr/local/bin/ssh-vpn-pro

# Also copy vpn_core.py and ssh_socks_simple.py if they exist
if [ -f "$SCRIPT_DIR/vpn_core.py" ]; then
    cp "$SCRIPT_DIR/vpn_core.py" /usr/local/bin/vpn_core.py
    chmod 644 /usr/local/bin/vpn_core.py
    echo "✅ Installed vpn_core.py"
else
    echo "⚠️  vpn_core.py not found"
fi

if [ -f "$SCRIPT_DIR/ssh_socks_simple.py" ]; then
    cp "$SCRIPT_DIR/ssh_socks_simple.py" /usr/local/bin/ssh_socks_simple.py
    chmod 755 /usr/local/bin/ssh_socks_simple.py
    echo "✅ Installed ssh_socks_simple.py"
else
    echo "⚠️  ssh_socks_simple.py not found"
fi
echo ""

# Copy icon to system location
if [ -f "$ICON_FILE" ]; then
    mkdir -p /usr/share/pixmaps
    cp "$ICON_FILE" /usr/share/pixmaps/ssh-vpn-pro.png
    ICON_PATH="/usr/share/pixmaps/ssh-vpn-pro.png"
    echo "✅ Icon copied to /usr/share/pixmaps"
else
    ICON_PATH="network-vpn"
    echo "⚠️  Icon not found, using default"
fi
echo ""

# Create desktop entry
echo "📱 Creating application launcher..."

cat > /usr/share/applications/ssh-vpn-pro.desktop << EOF
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
X-GNOME-UsesNotifications=true
EOF

chmod 644 /usr/share/applications/ssh-vpn-pro.desktop

echo "✅ Created launcher: /usr/share/applications/ssh-vpn-pro.desktop"
echo ""

# Update desktop database
echo "🔄 Updating desktop database..."
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications 2>/dev/null || true
    echo "✅ Desktop database updated"
else
    echo "⚠️  update-desktop-database not found (optional)"
fi
echo ""

# Update icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t /usr/share/pixmaps 2>/dev/null || true
fi

# Success message
echo "╔════════════════════════════════════════════════╗"
echo "║                                                ║"
echo "║        ✅ Installation Successful! ✅          ║"
echo "║                                                ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "🚀 How to launch:"
echo ""
echo "   Method 1: From terminal"
echo "   $ ssh-vpn-pro"
echo ""
echo "   Method 2: From app launcher"
echo "   Search for 'SSH VPN Pro' in your applications menu"
echo "   (May need to logout/login or restart for first time)"
echo ""
echo "📱 Quick Start:"
echo "   1. Open SSH VPN Pro"
echo "   2. Tap ⚙️ Config tab (bottom)"
echo "   3. Enter your SSH server details"
echo "   4. Tap 💾 to save profile"
echo "   5. Tap 🏠 Home tab"
echo "   6. TAP THE BIG BLUE BUTTON!"
echo ""
echo "🎨 Watch the animation:"
echo "   🔵 Blue → 🟠 Orange (PULSING!) → 🟢 Green (GLOWING!)"
echo ""
echo "🔔 System Tray Icon:"
echo "   Look for the VPN shield icon near WiFi/Bluetooth"
echo "   • Click to show/hide window"
echo "   • Right-click for menu"
echo ""
if command -v gnome-shell &> /dev/null; then
    echo "   📌 GNOME Users: If tray icon doesn't appear,"
    echo "      logout and login to activate the extension"
    echo ""
fi
echo "📝 Installed files:"
echo "   • /usr/local/bin/ssh-vpn-pro"
echo "   • /usr/local/bin/vpn_core.py"
echo "   • /usr/share/applications/ssh-vpn-pro.desktop"
echo "   • /usr/share/pixmaps/ssh-vpn-pro.png"
echo ""
echo "🗑️  To uninstall:"
echo "   sudo ./uninstall.sh"
echo ""
echo "Enjoy! 🎉"
echo ""
