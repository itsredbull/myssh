#!/bin/bash
# SSH VPN Pro - Complete Uninstaller

echo "╔════════════════════════════════════════════════╗"
echo "║      SSH VPN Pro - Uninstall Script           ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo "This uninstaller needs root. Re-run with sudo."
    echo "Example: sudo $0"
    exit 1
fi

echo "🗑️  Removing SSH VPN Pro..."
echo ""

# Kill any running instances
pkill -f "ssh_vpn_pro.py" 2>/dev/null || true
pkill -f "ssh-vpn-pro" 2>/dev/null || true
echo "✓ Terminated any running instances."

# Remove main application directory
if [ -d "/usr/local/lib/ssh-vpn-pro" ]; then
    rm -rf "/usr/local/lib/ssh-vpn-pro"
    echo "✓ Removed application library: /usr/local/lib/ssh-vpn-pro"
fi

# Remove the binary wrapper
if [ -f "/usr/local/bin/ssh-vpn-pro" ]; then
    rm -f "/usr/local/bin/ssh-vpn-pro"
    echo "✓ Removed command-line launcher: /usr/local/bin/ssh-vpn-pro"
fi

# Remove desktop entry and icon
if [ -f "/usr/share/applications/ssh-vpn-pro.desktop" ]; then
    rm -f "/usr/share/applications/ssh-vpn-pro.desktop"
    echo "✓ Removed system desktop entry."
fi
if [ -f "/usr/share/pixmaps/ssh-vpn-pro.png" ]; then
    rm -f "/usr/share/pixmaps/ssh-vpn-pro.png"
    echo "✓ Removed system icon."
fi

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q /usr/share/applications
    echo "✓ Updated system desktop database."
fi

# Clean up temporary files
rm -f /tmp/vpn_cleanup.sh 2>/dev/null
rm -f /tmp/resolv.conf.ssh_vpn_pro.bak 2>/dev/null
rm -f /tmp/vpn_socks_*.log 2>/dev/null
rm -f /tmp/stunnel_config_*.conf 2>/dev/null
echo "✓ Cleaned up temporary files."


echo ""
echo "✅ Uninstall complete!"
echo ""
echo "📝 Note: Your saved profiles were NOT removed. They are located at:"
echo "   ~/.ssh_vpn_profiles.json"
echo ""
echo "   To remove your profiles as well, run this command:"
echo "   rm ~/.ssh_vpn_profiles.json"
echo ""