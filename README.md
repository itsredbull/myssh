# SSH VPN Pro

A modern, user-friendly SSH VPN client for Linux with a beautiful GUI. Create secure VPN tunnels through SSH connections with support for multiple protocols and authentication methods.

![SSH VPN Pro](vpn-icon.png)

## Features

- **Dual Protocol Support**: SSH and SSH-TLS modes for maximum flexibility
- **Flexible Authentication**: Password or SSH Key authentication (RSA, Ed25519, ECDSA, DSS)
- **Modern Animated GUI**: Clean, intuitive interface with smooth animations
- **System Tray Integration**: Minimize to tray for quick access
- **Profile Management**: Save and manage multiple server configurations
- **SNI Domain Spoofing**: SSH-TLS mode can mimic HTTPS traffic to bypass restrictions
- **Real-time Bandwidth Monitoring**: Track upload/download speeds
- **IPv6 Leak Protection**: Automatically blocks IPv6 to prevent leaks
- **UDP Traffic Support**: Full UDP forwarding capability
- **Custom DNS**: Configure your preferred DNS servers
- **Connection Statistics**: Real-time connection tracking

## Protocols

### SSH Mode
Direct SSH connection on any port (typically 22). Best for unrestricted networks with direct SSH access.

### SSH-TLS Mode
SSH connection wrapped in TLS/SSL (typically port 443). Traffic appears as HTTPS, making it harder to detect or block. Ideal for restrictive networks that filter SSH traffic.

## Installation

### Option 1: Automatic Installation (Recommended)

The installation script automatically detects your Linux distribution and installs all dependencies:

```bash
chmod +x install.sh
sudo ./install.sh
```

**Supported Distributions:**
- Debian/Ubuntu/Mint/Pop!_OS
- Arch/Manjaro/EndeavourOS
- Fedora/RHEL/AlmaLinux/Rocky Linux
- CentOS/Oracle Linux
- openSUSE/SLES
- Alpine Linux

After installation, launch from your application menu or run:
```bash
ssh-vpn-pro
```

### Option 2: Manual Installation

**Requirements:**
- Python 3.6 or higher
- Python packages: `paramiko`, `Pillow`, `pystray`
- System packages: `openssh-client`, `badvpn`, `stunnel4`, `policykit-1`, `iproute2`, `iptables`

**Install dependencies:**

**Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install python3 python3-tk python3-pip openssh-client badvpn stunnel4 policykit-1 iproute2 iptables
pip3 install paramiko Pillow pystray
```

**Arch Linux:**
```bash
sudo pacman -S python python-tk python-pip openssh badvpn stunnel
pip3 install paramiko Pillow pystray
```

**Fedora/RHEL:**
```bash
sudo dnf install python3 python3-tkinter python3-pip openssh-clients badvpn stunnel polkit iproute iptables
pip3 install paramiko Pillow pystray
```

**Run the application:**
```bash
chmod +x ssh_vpn_pro.py
./ssh_vpn_pro.py
```

## Usage

### Quick Start

1. Launch SSH VPN Pro
2. Go to **Profiles** tab
3. Click **+ New Profile**
4. Configure your connection:
   - **Protocol**: Choose SSH or SSH-TLS
   - **Host**: Your SSH server IP or hostname
   - **Port**: SSH port (default: 22)
   - **Username**: Your SSH username
   - **Auth Method**: Select Password or SSH Key
   - **Password/SSH Key**: Enter password or select key file
   - For SSH-TLS: Configure SNI Domain and TLS Port
5. Click **Save**
6. Return to **Home** tab
7. Click **CONNECT**
8. Enter your system password when prompted (required for network configuration)

### Authentication Methods

**Password Authentication:**
- Simple username/password login
- Credentials saved in encrypted profile (file permissions: 600)

**SSH Key Authentication:**
- More secure than passwords
- Supports RSA, Ed25519, ECDSA, DSS key types
- Default location: `~/.ssh/id_rsa`
- Browse to select your private key file

### Managing Profiles

- **Create**: Click + New Profile button
- **Edit**: Click ✎ on any saved profile
- **Delete**: Click ✖ on any saved profile
- **Select**: Click on profile card to make it active

Profiles are saved in `~/.ssh_vpn_profiles.json` with secure permissions.

## Server Recommendations

For optimal performance and reliability, we recommend using high-quality VPS providers:

**Recommended Provider: [MyHBD.net](https://myhbd.net)**
- Fast, reliable SSH servers
- Multiple global locations
- Optimized for VPN tunneling
- Excellent uptime and support

Choose servers geographically close to your location for best speeds.

## SSH-TLS Server Setup

To use SSH-TLS mode, configure stunnel on your SSH server:

### Server Configuration

**Install stunnel:**
```bash
sudo apt install stunnel4  # Debian/Ubuntu
sudo pacman -S stunnel     # Arch Linux
```

**Generate certificate:**
```bash
sudo openssl req -new -x509 -days 3650 -nodes \
  -out /etc/stunnel/stunnel.pem \
  -keyout /etc/stunnel/stunnel.pem
```

**Create config file (`/etc/stunnel/stunnel.conf`):**
```ini
[ssh]
accept = 443
connect = 127.0.0.1:22
cert = /etc/stunnel/stunnel.pem
```

**Enable and start:**
```bash
sudo systemctl enable stunnel4
sudo systemctl start stunnel4
```

**Allow firewall:**
```bash
sudo ufw allow 443/tcp
```

Now clients can connect using SSH-TLS mode on port 443!

## Troubleshooting

### Connection Issues

**SSH connection fails:**
```bash
# Test SSH access manually
ssh username@server -p port
```

**Authentication errors with SSH key:**
- Verify key file permissions: `chmod 600 ~/.ssh/id_rsa`
- Ensure public key is in server's `~/.ssh/authorized_keys`
- Check key file path is correct

**No internet after connecting:**
- Try disconnecting and reconnecting
- Check logs tab for error messages
- If disconnect fails, run cleanup script:
```bash
sudo bash cleanup_vpn.sh
```

**Multiple instance error:**
```bash
pkill -f ssh_vpn_pro.py
```

### Network Recovery

If your internet doesn't work after disconnecting, use the cleanup script:

```bash
sudo bash cleanup_vpn.sh
```

This will restore your network configuration.

## Uninstallation

```bash
sudo ./uninstall.sh
```

This removes application files but keeps your saved profiles in `~/.ssh_vpn_profiles.json`

## Security Notes

- Profile data stored in `~/.ssh_vpn_profiles.json` with 600 permissions (owner only)
- SSH key authentication recommended over passwords
- All traffic encrypted through SSH tunnel
- IPv6 automatically blocked to prevent leaks
- DNS queries routed through VPN

## Technical Details

**Files:**
- `ssh_vpn_pro.py` - Main application
- `vpn_core.py` - Core VPN functionality
- `ssh_socks_simple.py` - SSH tunnel handler
- `install.sh` - Automatic installer
- `uninstall.sh` - Uninstaller
- `cleanup_vpn.sh` - Network recovery tool

**Ports Used (localhost only):**
- 1080: SOCKS5 proxy
- 7300-7301: UDP gateway (configurable)

## Contributing

Issues and pull requests are welcome!

## License

MIT License - See LICENSE file for details

## Credits

Developed by **Mohammad Safarzadeh**

GitHub: [github.com/itsredbull](https://github.com/itsredbull)

---

**Note**: This tool is for legitimate use only. Ensure you have permission to use any SSH server you connect to. Respect all applicable laws and regulations.
