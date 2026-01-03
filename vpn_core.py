"""Core VPN functionality for SSH VPN Pro
- Centralized network setup and cleanup via single sudo prompt
- systemd-resolved support for modern DNS handling on Linux
- IPv6 leak protection
- Prevents connection loop by adding explicit route for the SSH host
"""

import subprocess
import paramiko
import time
import os
import signal
import atexit
import socket

RESOLV_BACKUP = '/tmp/resolv.conf.ssh_vpn_pro.bak' # Use /tmp for better compatibility

# --- Helper for running scripts with root ---
def _run_sudo_script(script_content, log_callback):
    """Tries to run a script with pkexec, falling back to sudo."""
    log = log_callback or print
    cmd = ['bash', '-c', script_content]
    
    try:
        # pkexec is often preferred for GUI apps
        log("Attempting to run network script with pkexec...")
        subprocess.run(['pkexec'] + cmd, check=True, timeout=30, capture_output=True, text=True)
        log("✅ pkexec script execution successful.")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log(f"pkexec failed: {e.stderr if hasattr(e, 'stderr') else e}. Falling back to sudo.")
        try:
            # Fallback for systems without pkexec or if it fails
            log("Attempting to run network script with sudo...")
            subprocess.run(['sudo', 'bash'], input=script_content, check=True, timeout=30, capture_output=True, text=True)
            log("✅ sudo script execution successful.")
            return True
        except Exception as e_sudo:
            stderr = e_sudo.stderr if hasattr(e_sudo, 'stderr') else "(no stderr)"
            log(f"❌ sudo script also failed: {e_sudo}. Stderr: {stderr}")
            return False

# --- DNS Management Helpers ---
def _uses_systemd_resolved():
    """Check if systemd-resolved is active."""
    return os.path.exists('/usr/bin/resolvectl') and subprocess.run(['pidof', 'systemd-resolved'], capture_output=True).stdout.strip()

def _get_default_interface():
    """Get the default network interface device name."""
    try:
        # First, try the specific route method, which is often more accurate
        # for complex routing tables (e.g., multiple default routes).
        result = subprocess.run(
            ['ip', 'route', 'get', '1.1.1.1'],
            check=True, capture_output=True, text=True
        )
        # Example output: "1.1.1.1 via 192.168.1.1 dev eth0 src 192.168.1.100 uid 1000"
        parts = result.stdout.strip().split()
        if 'dev' in parts:
            return parts[parts.index('dev') + 1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If the first method fails, fall back to parsing the main routing table.
        try:
            result = subprocess.run(
                ['ip', 'route'],
                check=True, capture_output=True, text=True
            )
            # Find the line starting with 'default'
            for line in result.stdout.splitlines():
                if line.startswith('default'):
                    parts = line.split()
                    if 'dev' in parts:
                        return parts[parts.index('dev') + 1]
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None # Both methods failed
    return None

# --- Main Public Functions ---

def create_tun_vpn(host, port, username, auth_method, password, ssh_key_path, udpgw_port=7300, dns_servers='8.8.8.8, 8.8.4.4', log_callback=None):
    """
    Creates the full VPN tunnel: sets up network, starts proxies, and returns process info.
    This version bundles all privileged operations into a single script.
    """
    log = log_callback or print
    systemd_interface = None # Define here for cleanup scope

    try:
        log(f"Creating tun2socks VPN (UDP Gateway: {udpgw_port})...")
        
        # 1. Resolve host and determine route BEFORE building script
        try:
            host_ip = socket.gethostbyname(host)
            log(f"Resolved SSH host '{host}' to IP '{host_ip}'")
        except socket.gaierror:
            raise RuntimeError(f"Could not resolve host: {host}")

        route_cmd_output = subprocess.check_output(['ip', 'route', 'get', host_ip], text=True).strip()
        parts = route_cmd_output.split()
        try:
            src_index = parts.index('src')
            route_to_add = ' '.join(parts[:src_index])
        except ValueError:
            route_to_add = route_cmd_output
        log(f"Found route to host: '{route_to_add}'")

        # 2. Build the network setup script
        setup_script = "#!/bin/bash\nset -e\n\n"
        log("Building network setup script...")

        # Disable IPv6
        setup_script += "# Disable IPv6 to prevent leaks\n"
        setup_script += "sysctl -w net.ipv6.conf.all.disable_ipv6=1\n"
        setup_script += "sysctl -w net.ipv6.conf.default.disable_ipv6=1\n\n"

        # Configure DNS
        dns_list = [dns.strip() for dns in dns_servers.split(',') if dns.strip()]
        if dns_list:
            setup_script += "# Configure DNS\n"
            if _uses_systemd_resolved():
                interface = _get_default_interface()
                if interface:
                    systemd_interface = interface
                    dns_str = ' '.join(dns_list)
                    setup_script += f"resolvectl dns {interface} {dns_str}\n"
                    setup_script += f"resolvectl domain {interface} '~.'\n\n"
                    log(f"Script will use systemd-resolved on interface '{interface}'")
                else:
                    log("Warning: Could not determine default interface for resolvectl. DNS may not be set.")
            else:
                log("Script will use legacy /etc/resolv.conf method for DNS")
                if os.path.exists('/etc/resolv.conf'):
                    setup_script += f"cp /etc/resolv.conf {RESOLV_BACKUP}\n"
                dns_text = '\n'.join(f'nameserver {d}' for d in dns_list)
                setup_script += f"echo -e '{dns_text}' > /etc/resolv.conf\n\n"

        # Setup TUN device and routing
        setup_script += "# Setup TUN device and routing\n"
        setup_script += "ip tuntap add dev tun0 mode tun\n"
        setup_script += "ip addr add 10.0.0.1/24 dev tun0\n"
        setup_script += "ip link set dev tun0 up\n"
        
        # CRITICAL: Add explicit route to SSH host to avoid connection loop
        setup_script += f"# Add explicit route for SSH host to prevent loop\n"
        setup_script += f"ip route add {route_to_add}\n\n"
        
        # Route all other traffic through the tunnel
        setup_script += "# Route all other traffic through the tunnel\n"
        setup_script += "ip route add 0.0.0.0/1 dev tun0\n"
        setup_script += "ip route add 128.0.0.0/1 dev tun0\n"
        
        # 3. Execute the setup script with root privileges
        log("Requesting root permissions for all network setup tasks...")
        if not _run_sudo_script(setup_script, log):
            raise RuntimeError("Failed to execute network setup script. Check logs for details.")
        
        # 4. Start SOCKS proxy (as current user)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ssh_script = os.path.join(script_dir, 'ssh_socks_simple.py')
        if not os.path.exists(ssh_script):
            ssh_script = '/usr/local/lib/ssh-vpn-pro/ssh_socks_simple.py'

        cmd = ['python3', '-u', ssh_script, host, str(port), username]
        if auth_method == "SSH Key":
            cmd.extend([os.path.expanduser(ssh_key_path), '1080', 'key'])
        else:
            cmd.extend([password, '1080', 'password'])

        socks_log = f'/tmp/vpn_socks_{os.getpid()}.log'
        with open(socks_log, 'w') as log_file:
            ssh_process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
        log(f"SSH SOCKS proxy started (PID: {ssh_process.pid})")

        time.sleep(3) # Wait for SOCKS proxy to be ready
        if ssh_process.poll() is not None:
             raise RuntimeError("SSH SOCKS proxy failed to start. Check credentials and connectivity.")

        # 5. Start tun2socks and udpgw (as current user)
        tun_cmd = [
            'badvpn-tun2socks', '--tundev', 'tun0', '--netif-ipaddr', '10.0.0.2',
            '--netif-netmask', '255.255.255.0', '--socks-server-addr', '127.0.0.1:1080',
            '--udpgw-server-addr', f'127.0.0.1:{udpgw_port}'
        ]
        udpgw_cmd = ['badvpn-udpgw', '--listen-addr', f'127.0.0.1:{udpgw_port}']

        tunnel_proc = subprocess.Popen(tun_cmd, preexec_fn=os.setsid)
        udpgw_proc = subprocess.Popen(udpgw_cmd, preexec_fn=os.setsid)

        log("✅ VPN tunnel established successfully.")
        return True, {
            "ssh_proc": ssh_process,
            "tunnel_proc": tunnel_proc,
            "udpgw_proc": udpgw_proc,
            "systemd_interface": systemd_interface
        }
    except Exception as e:
        log(f"❌ create_tun_vpn failed: {e}")
        cleanup_network({"systemd_interface": systemd_interface}, log) # Attempt cleanup
        return False, None

def cleanup_network(vpn_info, log_callback=None):
    """Cleans up all network changes and kills VPN processes using a single sudo script."""
    log = log_callback or print
    log("🧹 Cleaning up network connection...")

    # 1. Kill user-space processes
    for proc_name in ["ssh_proc", "tunnel_proc", "udpgw_proc"]:
        if vpn_info and proc_name in vpn_info and vpn_info[proc_name]:
            try:
                os.killpg(os.getpgid(vpn_info[proc_name].pid), signal.SIGTERM)
                log(f"Terminated {proc_name} (PID: {vpn_info[proc_name].pid})")
            except Exception as e:
                log(f"Could not terminate {proc_name}: {e}")
    
    # 2. Build and run cleanup script
    cleanup_script = "#!/bin/bash\n" # Don't use set -e, we want to try every command
    
    cleanup_script += "# Kill any leftover processes\n"
    cleanup_script += "pkill -f 'badvpn-tun2socks' || true\n"
    cleanup_script += "pkill -f 'badvpn-udpgw' || true\n"
    cleanup_script += "pkill -f 'ssh_socks_simple.py' || true\n\n"
    
    cleanup_script += "# Remove TUN device and routes\n"
    cleanup_script += "ip link set tun0 down || true\n"
    cleanup_script += "ip tuntap del dev tun0 mode tun || true\n\n"
    
    cleanup_script += "# Revert DNS changes\n"
    systemd_interface = vpn_info.get("systemd_interface") if vpn_info else None
    if systemd_interface and _uses_systemd_resolved():
        log(f"Script will revert DNS on interface '{systemd_interface}'")
        cleanup_script += f"resolvectl revert {systemd_interface} || true\n"
    else:
        log("Script will attempt to restore /etc/resolv.conf from backup")
        if os.path.exists(RESOLV_BACKUP):
            cleanup_script += f"cp {RESOLV_BACKUP} /etc/resolv.conf || true\n"
            cleanup_script += f"rm -f {RESOLV_BACKUP} || true\n"
    
    cleanup_script += "\n# Re-enable IPv6\n"
    cleanup_script += "sysctl -w net.ipv6.conf.all.disable_ipv6=0 || true\n"
    cleanup_script += "sysctl -w net.ipv6.conf.default.disable_ipv6=0 || true\n"

    log("Requesting root permissions for all network cleanup tasks...")
    if not _run_sudo_script(cleanup_script, log):
        log("❌ Network cleanup script failed. Manual cleanup may be required.")
    else:
        log("✅ Network cleanup complete.")

def test_ssh_connection(host, port, username, auth_method, password, ssh_key_path, log_callback=None):
    log = log_callback or print
    try:
        log(f"🔌 Attempting SSH: {username}@{host}:{port}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        key_path = os.path.expanduser(ssh_key_path)

        if auth_method == "SSH Key":
            if not os.path.exists(key_path):
                log(f"❌ SSH key file not found: {key_path}")
                return False
            ssh.connect(host, port=port, username=username, key_filename=key_path, timeout=10)
        else:
            ssh.connect(host, port=port, username=username, password=password, timeout=10)
        
        ssh.close()
        log("✅ SSH connection successful")
        return True
    except Exception as e:
        log(f"❌ SSH connection failed: {type(e).__name__}: {str(e)}")
        return False

def check_udpgw_status(udpgw_port=7300):
    """Checks if the UDP gateway is listening on its port."""
    try:
        result = subprocess.run(['ss', '-tuln'], capture_output=True, text=True, timeout=2)
        return f'127.0.0.1:{udpgw_port}' in result.stdout
    except FileNotFoundError:
        # Fallback for systems without 'ss'
        try:
            result = subprocess.run(['netstat', '-tuln'], capture_output=True, text=True, timeout=2)
            return f'127.0.0.1:{udpgw_port}' in result.stdout
        except Exception:
            return False # Cannot determine status
    except Exception:
        return False

def create_stunnel_config(host, tls_port, sni_domain):
    """Creates a temporary stunnel config file."""
    config_content = f"""
foreground = yes
pid = 
client = yes
[ssh]
accept = 127.0.0.1:0
connect = {host}:{tls_port}
sni = {sni_domain}
"""
    config_path = f'/tmp/stunnel_config_{os.getpid()}.conf'
    with open(config_path, 'w') as f:
        f.write(config_content)
    return config_path, None 

def start_stunnel(config_path, log_callback):
    """Starts stunnel and captures the local port it uses."""
    log = log_callback or print
    try:
        proc = subprocess.Popen(
            ['stunnel', config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(2) # Give stunnel a moment to start and bind

        if proc.poll() is not None:
            err = proc.stderr.read()
            log(f"stunnel failed to start. Error: {err}")
            return None, None

        # Find the ephemeral port stunnel is listening on
        for i in range(5):
            try:
                res = subprocess.run(['ss', '-tlpn'], capture_output=True, text=True, check=True)
                for line in res.stdout.splitlines():
                    if f'pid={proc.pid}' in line and '127.0.0.1' in line:
                        local_port = int(line.split()[3].split(':')[-1])
                        log(f"stunnel is listening on local port: {local_port}")
                        return proc, local_port
                time.sleep(1)
            except Exception as e:
                log(f"Could not get stunnel port with 'ss': {e}. Trying 'netstat'.")
                try:
                    res = subprocess.run(['netstat', '-tlpn'], capture_output=True, text=True, check=True)
                    for line in res.stdout.splitlines():
                        if f'{{proc.pid}}/stunnel' in line and '127.0.0.1' in line:
                            local_port = int(line.split()[3].split(':')[-1])
                            log(f"stunnel is listening on local port: {local_port}")
                            return proc, local_port
                    time.sleep(1)
                except Exception as e2:
                    log(f"Could not get stunnel port with 'netstat' either: {e2}")
        
        log("Could not determine stunnel's local listening port.")
        proc.kill()
        return None, None
        
    except Exception as e:
        log(f"Failed to start stunnel: {e}")
        return None, None

# Atexit handler for emergency cleanup
@atexit.register
def _emergency_cleanup():
    print("Emergency cleanup on exit...")
    cleanup_info = {"systemd_interface": None} # Assume we don't know the interface
    cleanup_network(cleanup_info, print)
