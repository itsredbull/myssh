#!/bin/bash
# SSH VPN Pro - Complete Uninstaller
# Removes ALL old installations

echo "╔════════════════════════════════════════════════╗"
echo "║      SSH VPN Pro - Uninstall Script           ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo "⚠️  Running without sudo - will only remove user files"
    echo ""
    SUDO=false
else
    echo "✅ Running with sudo - complete removal"
    echo ""
    SUDO=true
fi

echo "🗑️  Removing SSH VPN Pro..."
echo ""

# Remove from /usr/local/bin
if [ "$SUDO" = true ]; then
    rm -f /usr/local/bin/ssh-vpn-pro 2>/dev/null
    rm -f /usr/local/bin/vpn_core.py 2>/dev/null
    rm -rf /usr/local/bin/__pycache__ 2>/dev/null
    echo "✓ Removed /usr/local/bin/ssh-vpn-pro and vpn_core.py"
fi

# Remove desktop entries (all possible locations)
if [ "$SUDO" = true ]; then
    rm -f /usr/share/applications/ssh-vpn-pro.desktop 2>/dev/null
    rm -f /usr/share/applications/SSH\ VPN\ Pro.desktop 2>/dev/null
    rm -f /usr/share/applications/ssh_vpn_pro.desktop 2>/dev/null
    echo "✓ Removed system desktop entries"
fi

# Get real user home directory (in case running with sudo)
if [ -n "$SUDO_USER" ]; then
    REAL_HOME=$(eval echo ~$SUDO_USER)
else
    REAL_HOME="$HOME"
fi

# Remove user desktop entries
rm -f "$REAL_HOME/.local/share/applications/ssh-vpn-pro.desktop" 2>/dev/null
rm -f "$REAL_HOME/.local/share/applications/SSH VPN Pro.desktop" 2>/dev/null
rm -f "$REAL_HOME/.local/share/applications/ssh_vpn_pro.desktop" 2>/dev/null
echo "✓ Removed user desktop entries from $REAL_HOME"

# Clean mimeinfo.cache
if [ -f "$REAL_HOME/.local/share/applications/mimeinfo.cache" ]; then
    sed -i '/ssh-vpn-pro/d' "$REAL_HOME/.local/share/applications/mimeinfo.cache" 2>/dev/null || true
    echo "✓ Cleaned desktop cache"
fi

# Remove icon
if [ "$SUDO" = true ]; then
    rm -f /usr/share/pixmaps/ssh-vpn-pro.png 2>/dev/null
    echo "✓ Removed system icon"
fi

# Update desktop database
if [ "$SUDO" = true ]; then
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database /usr/share/applications 2>/dev/null || true
        echo "✓ Updated system desktop database"
    fi
fi

if command -v update-desktop-database &> /dev/null; then
    if [ -n "$SUDO_USER" ]; then
        sudo -u "$SUDO_USER" update-desktop-database "$REAL_HOME/.local/share/applications" 2>/dev/null || true
    else
        update-desktop-database "$REAL_HOME/.local/share/applications" 2>/dev/null || true
    fi
    echo "✓ Updated user desktop database"
fi

# Clear icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    if [ "$SUDO" = true ]; then
        gtk-update-icon-cache -f -t /usr/share/pixmaps 2>/dev/null || true
    fi
    gtk-update-icon-cache -f -t ~/.local/share/icons 2>/dev/null || true
fi

# Kill any running instances
pkill -f "ssh_vpn.*\.py" 2>/dev/null || true
pkill -f "ssh-vpn-pro" 2>/dev/null || true

echo ""
echo "✅ Uninstall complete!"
echo ""
echo "📝 Note: Your saved profiles were kept at:"
echo "   ~/.ssh_vpn_profiles.json"
echo ""
echo "   To remove profiles too, run:"
echo "   rm ~/.ssh_vpn_profiles.json"
echo ""
echo "🔄 To reinstall:"
echo "   sudo ./install.sh"
echo ""
