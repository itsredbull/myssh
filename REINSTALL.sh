#!/bin/bash
# One-command reinstall script

echo "╔════════════════════════════════════════════════╗"
echo "║    SSH VPN Pro - Clean Reinstall               ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "This will:"
echo "  1. Remove old installation"
echo "  2. Install fresh copy"
echo "  3. Refresh desktop"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run with sudo:"
    echo "   sudo ./REINSTALL.sh"
    exit 1
fi

echo ""
echo "Step 1/2: Uninstalling old version..."
./uninstall.sh

echo ""
echo "Step 2/2: Installing fresh copy..."
./install.sh

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║          ✅ Reinstall Complete! ✅             ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "⚠️  IMPORTANT: You MUST logout/login now!"
echo ""
echo "After logout/login:"
echo "  • Press Super key"
echo "  • Type 'SSH VPN Pro'"
echo "  • Click to open!"
echo ""
