#!/bin/bash
# SSH VPN Pro - Emergency Network Cleanup
# Run this if your internet doesn't work after the VPN app crashes or fails to clean up.

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SSH VPN Pro - Emergency Network Cleanup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This script will attempt to restore your network configuration."
echo "🔐 You will be prompted for your password (sudo)."
echo ""

# --- Kill Processes ---
echo "🧹 Killing any lingering VPN processes..."
# Use pkill with the -f flag to match the full command line
sudo pkill -f badvpn-udpgw
sudo pkill -f badvpn-tun2socks
sudo pkill -f "python3.*ssh_socks_simple.py"
sudo pkill -f stunnel
echo "Processes terminated."
echo ""

# --- Remove TUN Interface ---
echo "🌐 Removing virtual network interface (tun0)..."
sudo ip link set tun0 down 2>/dev/null
sudo ip tuntap del dev tun0 mode tun 2>/dev/null
echo "Interface tun0 removed."
echo ""

# --- Restore DNS ---
RESOLV_BACKUP='/tmp/resolv.conf.ssh_vpn_pro.bak'
echo "📡 Restoring DNS configuration..."
if [ -f "$RESOLV_BACKUP" ]; then
    sudo cp "$RESOLV_BACKUP" /etc/resolv.conf
    sudo rm -f "$RESOLV_BACKUP"
    echo "Restored /etc/resolv.conf from backup."
else
    # As a fallback, try to revert using resolvectl if available
    if command -v resolvectl &> /dev/null; then
        echo "Attempting to revert DNS using resolvectl (requires interface name)..."
        # This is a best-effort attempt; we don't know the original interface name here.
        # We can try to find the most likely candidate.
        DEFAULT_IF=$(ip route get 1.1.1.1 | grep -oP 'dev \K\w+')
        if [ -n "$DEFAULT_IF" ]; then
            echo "Found default interface: $DEFAULT_IF. Reverting DNS..."
            sudo resolvectl revert "$DEFAULT_IF"
        else
            echo "Could not determine default interface to revert DNS."
        fi
    else
        echo "No DNS backup file found and resolvectl is not available."
    fi
fi
echo ""

# --- Re-enable IPv6 ---
echo "🔓 Re-enabling IPv6 to prevent connectivity issues..."
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=0 >/dev/null 2>&1
sudo sysctl -w net.ipv6.conf.default.disable_ipv6=0 >/dev/null 2>&1
echo "IPv6 has been re-enabled."
echo ""

echo "✅ Cleanup complete!"
echo "Your internet connection should now be restored."
echo ""