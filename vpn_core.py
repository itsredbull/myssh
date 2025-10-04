"""
Core VPN functionality for SSH VPN Pro
Fixed version - runs SSH tunnel as user, only TUN setup needs root
"""

import subprocess
import paramiko
import time
import os
import signal


def test_ssh_connection(host, port, username, auth_method, password, ssh_key_path, log_callback=None):
    """Test SSH connection with password or SSH key"""
    def log(message):
        if log_callback:
            log_callback(message)

    try:
        log(f"🔌 Attempting SSH: {username}@{host}:{port}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if auth_method == "SSH Key":
            # Expand ~ to home directory
            key_path = os.path.expanduser(ssh_key_path)

            # Check if key file exists
            if not os.path.exists(key_path):
                log(f"❌ SSH key file not found: {key_path}")
                return False

            # Try loading different key types
            key = None
            key_errors = []

            # Try RSA
            try:
                key = paramiko.RSAKey.from_private_key_file(key_path)
                log(f"🔑 Using RSA key: {key_path}")
            except Exception as e:
                key_errors.append(f"RSA: {e}")

            # Try Ed25519
            if not key:
                try:
                    key = paramiko.Ed25519Key.from_private_key_file(key_path)
                    log(f"🔑 Using Ed25519 key: {key_path}")
                except Exception as e:
                    key_errors.append(f"Ed25519: {e}")

            # Try DSS
            if not key:
                try:
                    key = paramiko.DSSKey.from_private_key_file(key_path)
                    log(f"🔑 Using DSS key: {key_path}")
                except Exception as e:
                    key_errors.append(f"DSS: {e}")

            # Try ECDSA
            if not key:
                try:
                    key = paramiko.ECDSAKey.from_private_key_file(key_path)
                    log(f"🔑 Using ECDSA key: {key_path}")
                except Exception as e:
                    key_errors.append(f"ECDSA: {e}")

            if not key:
                log(f"❌ Could not load SSH key. Tried: {', '.join(key_errors)}")
                return False

            # Connect with key
            ssh.connect(host, port=port, username=username, pkey=key, timeout=10)
        else:
            # Connect with password
            ssh.connect(host, port=port, username=username, password=password, timeout=10)

        ssh.close()
        log(f"✅ SSH connection successful")
        return True
    except Exception as e:
        log(f"❌ SSH connection failed: {type(e).__name__}: {str(e)}")
        return False


def check_udpgw_status(udpgw_port=7300):
    """Check if UDP gateway is running"""
    try:
        result = subprocess.run(['ss', '-tuln'], capture_output=True, text=True, timeout=2)
        return f'127.0.0.1:{udpgw_port}' in result.stdout
    except:
        return False


def create_stunnel_config(host, tls_port, sni_domain, local_port=None):
    """
    Create stunnel client configuration for SSH-over-TLS

    Args:
        host: Remote server IP/domain
        tls_port: TLS port on server (usually 443)
        sni_domain: SNI domain to mimic (e.g., www.google.com)
        local_port: Local port for unwrapped SSH (default: random 22000-22999)

    Returns:
        (config_path, local_port)
    """
    import random

    # Use random port to avoid conflicts
    if local_port is None:
        local_port = random.randint(22000, 22999)

    rand_suffix = random.randint(10000, 99999)
    config_path = f'/tmp/stunnel_ssh_{rand_suffix}.conf'

    # Log file for debugging
    log_file = f'/tmp/stunnel_ssh_{rand_suffix}.log'

    # Resolve hostname to IP if needed
    import socket
    try:
        server_ip = socket.gethostbyname(host)
    except:
        server_ip = host

    config_content = f"""foreground = no
debug = 7
pid = /tmp/stunnel_ssh_{rand_suffix}.pid
output = {log_file}

[ssh-tls]
client = yes
accept = 127.0.0.1:{local_port}
connect = {server_ip}:{tls_port}
sni = {sni_domain}
verifyChain = no
TIMEOUTclose = 0
delay = yes
"""

    with open(config_path, 'w') as f:
        f.write(config_content)

    return config_path, local_port


def start_stunnel(config_path, log_callback=None):
    """
    Start stunnel client process

    Args:
        config_path: Path to stunnel config file
        log_callback: Optional logging function

    Returns:
        (stunnel_process, local_port) or (None, None)
    """
    def log(message):
        if log_callback:
            log_callback(message)

    try:
        # Kill any existing stunnel processes to free up ports
        try:
            subprocess.run(['pkill', '-f', 'stunnel.*ssh'], check=False, timeout=2)
            time.sleep(0.5)
        except:
            pass

        # Check if stunnel is installed
        result = subprocess.run(['which', 'stunnel4'], capture_output=True, text=True)
        if result.returncode != 0:
            result = subprocess.run(['which', 'stunnel'], capture_output=True, text=True)
            if result.returncode != 0:
                log("❌ stunnel not installed! Install: sudo ./REINSTALL.sh")
                return None
            stunnel_cmd = 'stunnel'
        else:
            stunnel_cmd = 'stunnel4'

        # Extract local port from config
        local_port = None
        with open(config_path, 'r') as f:
            for line in f:
                if 'accept' in line and '127.0.0.1:' in line:
                    local_port = int(line.split(':')[-1].strip())
                    break

        if not local_port:
            log("❌ Could not determine local port from config")
            return None

        log(f"📝 Using {stunnel_cmd}, local port {local_port}")

        # Start stunnel in daemon mode with log file
        log_file = config_path.replace('.conf', '.log')
        pid_file = config_path.replace('.conf', '.pid')

        result = subprocess.run(
            [stunnel_cmd, config_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            log(f"❌ stunnel failed to start: {result.stderr}")
            return (None, None)

        # Read PID from file
        time.sleep(1)
        try:
            with open(pid_file, 'r') as f:
                stunnel_pid = int(f.read().strip())
            stunnel_process = type('obj', (object,), {'pid': stunnel_pid, 'poll': lambda: None})()
        except:
            log(f"❌ Could not read stunnel PID file")
            return (None, None)

        # Wait for stunnel to initialize
        log("⏳ Waiting for stunnel to initialize...")
        for i in range(10):
            time.sleep(1)

            # Check if local port is listening
            result = subprocess.run(['ss', '-tln'], capture_output=True, text=True)
            if f':{local_port}' in result.stdout:
                log(f"✅ stunnel running (PID: {stunnel_process.pid}), local port {local_port} ready")
                log(f"📄 Log file: {log_file}")
                return (stunnel_process, local_port)

        # Timeout - stunnel didn't start listening
        log(f"❌ stunnel timeout - port {local_port} not listening after 10s")
        stunnel_process.kill()
        return (None, None)

    except Exception as e:
        log(f"❌ stunnel error: {e}")
        return (None, None)


def create_tun_vpn(host, port, username, auth_method, password, ssh_key_path, udpgw_port=7300, dns_servers='8.8.8.8, 8.8.4.4', log_callback=None):
    """
    Create SSH VPN using tun2socks + udpgw method

    NEW APPROACH:
    1. Start SSH SOCKS proxy as regular user (avoids OpenSSL issues)
    2. Use pkexec only for TUN interface creation (needs root)

    Args:
        auth_method: "Password" or "SSH Key"
        password: Password for auth (used if auth_method == "Password")
        ssh_key_path: Path to SSH private key (used if auth_method == "SSH Key")
    """
    def log(message):
        if log_callback:
            log_callback(message)

    try:
        log(f"Creating tun2socks VPN (UDP Gateway: {udpgw_port})...")

        # Parse DNS servers
        dns_list = [dns.strip() for dns in dns_servers.split(',') if dns.strip()]
        primary_dns = dns_list[0] if len(dns_list) > 0 else '8.8.8.8'
        secondary_dns = dns_list[1] if len(dns_list) > 1 else '8.8.4.4'

        # STEP 1: Start SSH SOCKS proxy using Python (system SSH has OpenSSL issues)
        log("Starting SSH SOCKS proxy...")

        import random
        rand_suffix = random.randint(10000, 99999)

        # Find Python SSH SOCKS script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ssh_script = os.path.join(script_dir, 'ssh_socks_simple.py')
        if not os.path.exists(ssh_script):
            ssh_script = '/usr/local/bin/ssh_socks_simple.py'

        # Start Python SSH SOCKS proxy
        if auth_method == "SSH Key":
            # Use SSH key authentication
            ssh_cmd = [
                'python3', '-u',
                ssh_script,
                host,
                str(port),
                username,
                ssh_key_path,
                '1080',
                'key'  # auth method parameter
            ]
        else:
            # Use password authentication
            ssh_cmd = [
                'python3', '-u',
                ssh_script,
                host,
                str(port),
                username,
                password,
                '1080',
                'password'  # auth method parameter
            ]

        # Redirect output to log file to prevent buffer blocking
        socks_log = f'/tmp/vpn_socks_{rand_suffix}.log'
        with open(socks_log, 'w') as log_file:
            ssh_process = subprocess.Popen(
                ssh_cmd,
                stdout=log_file,
                stderr=log_file
            )

        password_file = None  # Not used with Python implementation

        log(f"SSH SOCKS proxy started (PID: {ssh_process.pid})")
        time.sleep(3)

        # Check if SSH process is still alive
        if ssh_process.poll() is not None:
            with open(socks_log, 'r') as f:
                output = f.read()
            log(f"❌ SSH process died: {output}")
            return (False, None)

        # Wait for SOCKS proxy to be ready
        log("Waiting for SOCKS proxy...")
        socks_ready = False
        for i in range(10):
            time.sleep(1)

            # Check if process died
            if ssh_process.poll() is not None:
                with open(socks_log, 'r') as f:
                    output = f.read()
                log(f"❌ SSH process died: {output}")
                return (False, None)

            result = subprocess.run(['ss', '-tln'], capture_output=True, text=True)
            if ':1080' in result.stdout:
                log("✅ SOCKS proxy active on 127.0.0.1:1080")
                socks_ready = True
                break

        if not socks_ready:
            log("❌ SOCKS proxy failed to start")
            if ssh_process.poll() is None:
                ssh_process.kill()
            return (False, None)

        # STEP 2: Create TUN interface script (runs as root via pkexec)
        log("Starting tun2socks VPN script...")

        tun_script_path = f'/tmp/vpn_tun_setup_{rand_suffix}.sh'

        tun_script_lines = [
            "#!/bin/bash",
            'echo "Setting up TUN interface for VPN..."',
            "",
            "# Cleanup any existing VPN processes first",
            'echo "Cleaning up any old VPN processes..."',
            "pkill -f badvpn-udpgw 2>/dev/null || true",
            "pkill -f badvpn-tun2socks 2>/dev/null || true",
            "ip link set tun0 down 2>/dev/null || true",
            "ip tuntap del dev tun0 mode tun 2>/dev/null || true",
            "sleep 1",
            "",
            "# Backup network configuration",
            "cp /etc/resolv.conf /tmp/resolv.conf.backup 2>/dev/null || true",
            f"ORIGINAL_GW=$(ip route | grep default | head -1 | awk '{{print $3}}')",
            f"ORIGINAL_DEV=$(ip route | grep default | head -1 | awk '{{print $5}}')",
            f'echo "Original gateway: $ORIGINAL_GW via $ORIGINAL_DEV"',
            "",
            "# Preserve route to SSH server",
            f"ip route add {host}/32 via $ORIGINAL_GW dev $ORIGINAL_DEV 2>/dev/null || true",
            "",
            "# Start UDP gateway",
            f'echo "Starting UDP gateway on port {udpgw_port}..."',
            f"badvpn-udpgw --listen-addr 127.0.0.1:{udpgw_port} --loglevel error &",
            "UDPGW_PID=$!",
            "sleep 2",
            "# Check if UDP gateway is running",
            'if kill -0 $UDPGW_PID 2>/dev/null; then',
            f'    echo "✓ UDP gateway running on 127.0.0.1:{udpgw_port} (PID: $UDPGW_PID)"',
            'else',
            f'    echo "✗ UDP gateway failed to start"',
            '    echo "Error: Maybe port {udpgw_port} is already in use?"',
            '    lsof -i :{udpgw_port} 2>/dev/null || true',
            '    exit 1',
            'fi',
            "",
            "# Create TUN interface",
            'echo "Creating TUN interface..."',
            "ip tuntap add dev tun0 mode tun",
            "ip addr add 10.0.0.1/24 dev tun0",
            "ip link set tun0 up",
            'echo "TUN interface created (10.0.0.1/24)"',
            "",
            "# Start tun2socks",
            'echo "Starting tun2socks..."',
            f"badvpn-tun2socks --tundev tun0 --netif-ipaddr 10.0.0.2 --netif-netmask 255.255.255.0 --socks-server-addr 127.0.0.1:1080 --udpgw-remote-server-addr 127.0.0.1:{udpgw_port} --loglevel error &",
            "TUN2SOCKS_PID=$!",
            'echo "tun2socks PID: $TUN2SOCKS_PID"',
            "sleep 5",
            "# Check if tun2socks is still running",
            'if kill -0 $TUN2SOCKS_PID 2>/dev/null; then',
            '    echo "✓ tun2socks is running"',
            'else',
            '    echo "✗ tun2socks died!"',
            '    echo "Error: Check if SOCKS proxy is working on 127.0.0.1:1080"',
            '    netstat -tlnp | grep 1080 || true',
            '    exit 1',
            'fi',
            "",
            "# Verify TUN interface",
            "if ip addr show tun0 >/dev/null 2>&1; then",
            '    echo "✓ TUN interface ready"',
            "else",
            '    echo "✗ TUN interface failed"',
            "    exit 1",
            "fi",
            "",
            "# Route all traffic through VPN using split routing",
            'echo "Configuring split routing..."',
            "# Delete any conflicting routes",
            "ip route del 0.0.0.0/1 2>/dev/null || true",
            "ip route del 128.0.0.0/1 2>/dev/null || true",
            "# Split routing covers all IPs without replacing default",
            "ip route add 0.0.0.0/1 dev tun0 metric 0",
            "ip route add 128.0.0.0/1 dev tun0 metric 0",
            'echo "✓ Routes added with highest priority (metric 0)"',
            "sleep 3",
            "",
            "# Block IPv6 to prevent leaking",
            'echo "Blocking IPv6..."',
            "sysctl -w net.ipv6.conf.all.disable_ipv6=1 2>/dev/null || true",
            "sysctl -w net.ipv6.conf.default.disable_ipv6=1 2>/dev/null || true",
            "sysctl -w net.ipv6.conf.lo.disable_ipv6=1 2>/dev/null || true",
            "# Block IPv6 with iptables",
            "if command -v ip6tables >/dev/null 2>&1; then",
            "    ip6tables -P INPUT DROP 2>/dev/null || true",
            "    ip6tables -P FORWARD DROP 2>/dev/null || true",
            "    ip6tables -P OUTPUT DROP 2>/dev/null || true",
            '    echo "✓ IPv6 blocked with ip6tables"',
            "else",
            '    echo "✓ IPv6 disabled (ip6tables not available)"',
            "fi",
            "",
            "# Update DNS",
            'echo "Updating DNS..."',
            "echo 'nameserver {primary_dns}' > /etc/resolv.conf",
            "echo 'nameserver {secondary_dns}' >> /etc/resolv.conf",
            'echo "✓ DNS updated"',
            "",
            'echo "✅ VPN setup complete!"',
            "",
            "# Keep script running",
            "tail -f /dev/null",
        ]

        with open(tun_script_path, 'w') as f:
            f.write('\n'.join(tun_script_lines))
        os.chmod(tun_script_path, 0o755)

        log("Waiting for root authentication dialog...")
        log("⚠️  Please enter your system password when prompted (you have 60 seconds)")

        # Run TUN setup script with pkexec
        tunnel_process = subprocess.Popen(
            ['pkexec', 'bash', tun_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Monitor script output with longer timeout
        success_found = False
        for i in range(60):  # Increased from 30 to 60 seconds
            time.sleep(1)
            log(f"Monitoring tun2socks setup... ({i+1}/60)")

            # Check if process ended
            if tunnel_process.poll() is not None:
                returncode = tunnel_process.returncode
                if returncode == 126:
                    log("❌ Authentication cancelled or timed out")
                elif returncode == 127:
                    log("❌ pkexec not found - install policykit")
                elif returncode != 0:
                    log(f"❌ Setup script failed with code {returncode}")
                break

            # Read output
            try:
                line = tunnel_process.stdout.readline()
                if line:
                    log(f"Script: {line.strip()}")
                    if "VPN setup complete" in line:
                        success_found = True
                        break
            except:
                pass

        if success_found:
            log("✅ Connected!")
            # Return BOTH processes so they stay alive!
            return (True, (tunnel_process, ssh_process))
        else:
            log("🧹 Cleaning up failed connection...")

            # Kill tunnel process
            try:
                tunnel_process.kill()
                tunnel_process.wait(timeout=3)
            except:
                pass

            # Kill SSH process
            try:
                ssh_process.kill()
                ssh_process.wait(timeout=3)
            except:
                pass

            # Kill any leftover processes
            try:
                subprocess.run(['pkill', '-f', f'ssh.*{socks_port}'], check=False, timeout=5)
                subprocess.run(['pkill', '-f', 'badvpn-tun2socks'], check=False, timeout=5)
                subprocess.run(['pkill', '-f', f'badvpn-udpgw.*{udpgw_port}'], check=False, timeout=5)
            except:
                pass

            # Remove script
            try:
                os.remove(tun_script_path)
            except:
                pass

            return (False, None)

    except Exception as e:
        log(f"❌ Error: {e}")

        # Clean up on exception
        log("🧹 Cleaning up after error...")
        try:
            if 'ssh_process' in locals() and ssh_process:
                ssh_process.kill()
        except:
            pass

        try:
            if 'tunnel_process' in locals() and tunnel_process:
                tunnel_process.kill()
        except:
            pass

        # Kill any leftover processes
        try:
            subprocess.run(['pkill', '-f', 'badvpn-tun2socks'], check=False, timeout=5)
            subprocess.run(['pkill', '-f', 'badvpn-udpgw'], check=False, timeout=5)
        except:
            pass

        return (False, None)
