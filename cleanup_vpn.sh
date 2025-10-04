#!/bin/bash
# SSH VPN Pro - Emergency Network Cleanup
# Run this if your internet doesn't work after VPN disconnect

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SSH VPN Pro - Network Cleanup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This will:"
echo "  • Kill all VPN processes"
echo "  • Remove VPN network interface"
echo "  • Restore your normal internet"
echo ""
echo "🔐 You may be asked for your password..."
echo ""

# Kill processes
echo "🧹 Killing VPN processes..."
sudo pkill -f badvpn-udpgw 2>/dev/null
sudo pkill -f badvpn-tun2socks 2>/dev/null
sudo pkill -f stunnel 2>/dev/null
sleep 1

# Remove TUN interface
echo "🌐 Removing VPN interface..."
sudo ip link set tun0 down 2>/dev/null
sudo ip tuntap del dev tun0 mode tun 2>/dev/null

# Restore DNS
echo "📡 Restoring DNS..."
sudo cp /tmp/resolv.conf.backup /etc/resolv.conf 2>/dev/null || true

# Re-enable IPv6
echo "🔓 Re-enabling IPv6..."
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=0 >/dev/null 2>&1
sudo sysctl -w net.ipv6.conf.default.disable_ipv6=0 >/dev/null 2>&1

echo ""
echo "✅ Cleanup complete!"
echo "Your internet should work now."
echo ""
