"Core VPN functionality for SSH VPN Pro
- Centralized network setup and cleanup
- systemd-resolved support for modern DNS handling on Linux
- IPv6 leak protection
- Fallback to legacy resolv.conf modification
"

import subprocess
import paramiko
import time
import os
import signal
import atexit

RESOLV_BACKUP = '/tmp/resolv.conf.ssh_vpn_pro.bak' # Use /tmp for better compatibility

# --- Helper for running commands with root ---
def _run_sudo(cmd_list, log_callback):
    """Tries to run a command with pkexec, falling back to sudo."""
    try:
        # pkexec is often preferred for GUI apps
        subprocess.run(['pkexec'] + cmd_list, check=True, timeout=15, capture_output=True)
        log_callback(f"Successfully ran with pkexec: {' '.join(cmd_list)}")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log_callback(f"pkexec failed: {e}. Falling back to sudo.")
        try:
            # Fallback for systems without pkexec or if it fails
            subprocess.run(['sudo'] + cmd_list, check=True, timeout=15, capture_output=True)
            log_callback(f"Successfully ran with sudo: {' '.join(cmd_list)}")
            return True
        except Exception as e_sudo:
            log_callback(f"sudo also failed: {e_sudo}. Command failed: {' '.join(cmd_list)}")
            return False

# --- DNS Management ---
def _uses_systemd_resolved():
    """Check if systemd-resolved is active."""
    return os.path.exists('/usr/bin/resolvectl') and subprocess.run(['pidof', 'systemd-resolved'], capture_output=True).stdout.strip()

def _get_default_interface():
    """Get the default network interface device name."""
    try:
        # ip route get 1.1.1.1 | grep -oP 'dev \K\w+'
        result = subprocess.run(
            "ip route get 1.1.1.1 | grep -oP 'dev \\K\\w+'",
            shell=True, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except Exception:
        return None

def _configure_dns(dns_servers, log_callback):
    """
    Configures system DNS. Prefers systemd-resolved if available.
    Returns the interface name if systemd-resolved was used, otherwise True/False.
    """
    log = log_callback or print
    dns_list = [dns.strip() for dns in dns_servers.split(',') if dns.strip()]
    if not dns_list:
        log("No DNS servers provided.")
        return False

    if _uses_systemd_resolved():
        interface = _get_default_interface()
        if not interface:
            log("Could not determine default interface for resolvectl.")
            return False
        log(f"Using systemd-resolved on interface '{interface}'")
        # Set DNS
        _run_sudo(['resolvectl', 'dns', interface] + dns_list, log)
        # Set domain to '~.' to route all queries through the VPN DNS
        _run_sudo(['resolvectl', 'domain', interface, '~.'], log)
        return interface  # Return interface for later use
    else:
        # Fallback to legacy method
        log("Using legacy /etc/resolv.conf method for DNS")
        try:
            # Backup
            if os.path.exists('/etc/resolv.conf'):
                _run_sudo(['cp', '/etc/resolv.conf', RESOLV_BACKUP], log)
                log(f"Backed up /etc/resolv.conf to {RESOLV_BACKUP}")
            # Write new config
            dns_text = '\\n'.join(f'nameserver {d}' for d in dns_list) + '\\n'
            return _run_sudo(['bash', '-c', f"echo -e '{dns_text}' > /etc/resolv.conf"], log)
        except Exception as e:
            log(f"Error modifying /etc/resolv.conf: {e}")
            return False

def _revert_dns(systemd_interface, log_callback):
    """
    Reverts system DNS changes.
    systemd_interface: The interface name if systemd-resolved was used, otherwise None.
    """
    log = log_callback or print
    if systemd_interface and _uses_systemd_resolved():
        log(f"Reverting DNS on interface '{systemd_interface}' using resolvectl")
        _run_sudo(['resolvectl', 'revert', systemd_interface], log)
    else:
        log("Reverting DNS using legacy /etc/resolv.conf method")
        if os.path.exists(RESOLV_BACKUP):
            _run_sudo(['cp', RESOLV_BACKUP, '/etc/resolv.conf'], log)
            _run_sudo(['rm', '-f', RESOLV_BACKUP], log)
            log("Restored /etc/resolv.conf from backup.")

# --- IPv6 Management ---
def _disable_ipv6(log_callback):
    log = log_callback or print
    log("Disabling IPv6 to prevent leaks...")
    _run_sudo(['sysctl', '-w', 'net.ipv6.conf.all.disable_ipv6=1'], log)
    _run_sudo(['sysctl', '-w', 'net.ipv6.conf.default.disable_ipv6=1'], log)

def _enable_ipv6(log_callback):
    log = log_callback or print
    log("Re-enabling IPv6...")
    _run_sudo(['sysctl', '-w', 'net.ipv6.conf.all.disable_ipv6=0'], log)
    _run_sudo(['sysctl', '-w', 'net.ipv6.conf.default.disable_ipv6=0'], log)

# --- Main Public Functions ---

def create_tun_vpn(host, port, username, auth_method, password, ssh_key_path, udpgw_port=7300, dns_servers='8.8.8.8, 8.8.4.4', log_callback=None):
    """
    Creates the full VPN tunnel: sets up network, starts proxies, and returns process info.
    """
    log = log_callback or print
    try:
        log(f"Creating tun2socks VPN (UDP Gateway: {udpgw_port})...")

        # 1. Disable IPv6
        _disable_ipv6(log)

        # 2. Configure DNS
        systemd_interface = _configure_dns(dns_servers, log)
        if not systemd_interface:
            log("Warning: Could not update system DNS. DNS leaks may occur.")

        # 3. Start SOCKS proxy (your existing logic)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ssh_script = os.path.join(script_dir, 'ssh_socks_simple.py')
        if not os.path.exists(ssh_script):
            # Adjust for installed location
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

        # Wait for SOCKS proxy to be ready
        time.sleep(3) # Initial wait
        if ssh_process.poll() is not None:
             raise RuntimeError("SSH SOCKS proxy failed to start.")

        # 4. Setup TUN device and badvpn-tun2socks
        tun_cmd = [
            'badvpn-tun2socks',
            '--tundev', 'tun0',
            '--netif-ipaddr', '10.0.0.2',
            '--netif-netmask', '255.255.255.0',
            '--socks-server-addr', '127.0.0.1:1080',
            '--udpgw-server-addr', f'127.0.0.1:{udpgw_port}'
        ]
        udpgw_cmd = ['badvpn-udpgw', '--listen-addr', f'127.0.0.1:{udpgw_port}']

        # These require root
        setup_cmds = [
            ['ip', 'tuntap', 'add', 'dev', 'tun0', 'mode', 'tun'],
            ['ip', 'addr', 'add', '10.0.0.1/24', 'dev', 'tun0'],
            ['ip', 'link', 'set', 'dev', 'tun0', 'up'],
            ['ip', 'route', 'add', '0.0.0.0/1', 'dev', 'tun0'],
            ['ip', 'route', 'add', '128.0.0.0/1', 'dev', 'tun0']
        ]
        for cmd_item in setup_cmds:
            if not _run_sudo(cmd_item, log):
                raise RuntimeError(f"Failed to run network setup command: {cmd_item}")

        # Start tun2socks and udpgw as the current user
        tunnel_proc = subprocess.Popen(tun_cmd, preexec_fn=os.setsid)
        udpgw_proc = subprocess.Popen(udpgw_cmd, preexec_fn=os.setsid)

        log("✅ VPN tunnel established successfully.")
        # Return all necessary info for cleanup
        return True, {
            "ssh_proc": ssh_process,
            "tunnel_proc": tunnel_proc,
            "udpgw_proc": udpgw_proc,
            "systemd_interface": systemd_interface # can be str or bool
        }
    except Exception as e:
        log(f"❌ create_tun_vpn failed: {e}")
        # Cleanup any partial setup
        cleanup_network({"systemd_interface": locals().get("systemd_interface")}, log)
        return False, None


def cleanup_network(vpn_info, log_callback=None):
    """
    Cleans up all network changes and kills VPN processes.
    vpn_info: The dictionary returned by create_tun_vpn.
    """
    log = log_callback or print
    log("🧹 Cleaning up network connection...")

    # Kill processes
    for proc_name in ["ssh_proc", "tunnel_proc", "udpgw_proc"]:
        if vpn_info and proc_name in vpn_info and vpn_info[proc_name]:
            try:
                # Kill the whole process group
                os.killpg(os.getpgid(vpn_info[proc_name].pid), signal.SIGTERM)
                log(f"Terminated {proc_name} (PID: {vpn_info[proc_name].pid})")
            except Exception as e:
                log(f"Could not terminate {proc_name}: {e}")

    # Fallback pkill
    _run_sudo(['pkill', '-f', 'badvpn-tun2socks'], log)
    _run_sudo(['pkill', '-f', 'badvpn-udpgw'], log)
    _run_sudo(['pkill', '-f', 'ssh_socks_simple.py'], log)

    # Remove TUN device and routes
    _run_sudo(['ip', 'link', 'set', 'tun0', 'down'], log)
    _run_sudo(['ip', 'tuntap', 'del', 'dev', 'tun0', 'mode', 'tun'], log)

    # Revert DNS
    systemd_interface = vpn_info.get("systemd_interface") if vpn_info else None
    _revert_dns(systemd_interface, log)

    # Re-enable IPv6
    _enable_ipv6(log)

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
    # stunnel will print the local port to stdout
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

        # Check if process is still alive
        if proc.poll() is not None:
            err = proc.stderr.read()
            log(f"stunnel failed to start. Error: {err}")
            return None, None

        # stunnel doesn't print the port anymore, we have to find it.
        # We can find the ephemeral port stunnel is using to connect to the server
        # but what we need is the local port it is listening on. 'accept = 127.0.0.1:0'
        # makes it listen on a random free port.
        # We can find this port using `ss` or `netstat`.
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
                        if f'{proc.pid}/stunnel' in line and '127.0.0.1' in line:
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

# Atexit handler to ensure cleanup on unexpected exit
def _emergency_cleanup():
    print("Emergency cleanup on exit...")
    log = print
    _run_sudo(['pkill', '-f', 'badvpn-tun2socks'], log)
    _run_sudo(['pkill', '-f', 'badvpn-udpgw'], log)
    _revert_dns(None, log) # Attempt legacy revert
    _enable_ipv6(log)

atexit.register(_emergency_cleanup)
signal.signal(signal.SIGTERM, lambda signum, frame: _emergency_cleanup() or os._exit(1))
signal.signal(signal.SIGINT, lambda signum, frame: _emergency_cleanup() or os._exit(1))