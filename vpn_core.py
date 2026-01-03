"""
Core VPN functionality for SSH VPN Pro
Fixed version - runs SSH tunnel as user, only TUN setup needs root
Includes DNS management helpers to reduce DNS leaks while VPN is active.
"""

import subprocess
import paramiko
import time
import os
import signal
import atexit

RESOLV_BACKUP = '/etc/resolv.conf.ssh_vpn_pro.bak'

def _log_callback_default(msg):
    print(msg)

def _backup_resolv(log_callback=None):
    log = log_callback or _log_callback_default
    try:
        if os.path.exists('/etc/resolv.conf') and not os.path.exists(RESOLV_BACKUP):
            # Use pkexec or sudo to copy (requires root)
            try:
                subprocess.run(['pkexec','cp','/etc/resolv.conf', RESOLV_BACKUP], check=True)
            except Exception:
                subprocess.run(['sudo','cp','/etc/resolv.conf', RESOLV_BACKUP], check=True)
            log(f"Backed up /etc/resolv.conf to {RESOLV_BACKUP}")
    except Exception as e:
        log(f"Warning: could not backup resolv.conf: {e}")

def _write_resolv(dns_list, log_callback=None):
    log = log_callback or _log_callback_default
    dns_text = '\n'.join(f'nameserver {d}' for d in dns_list) + '\n'
    cmd = "cat > /etc/resolv.conf <<'EOF'\n" + dns_text + "EOF"
    try:
        subprocess.run(['pkexec','bash','-c',cmd], check=True)
        log("Wrote new /etc/resolv.conf via pkexec")
        return True
    except Exception:
        try:
            subprocess.run(['sudo','bash','-c',cmd], check=True)
            log("Wrote new /etc/resolv.conf via sudo")
            return True
        except Exception as e:
            log(f"Failed to write /etc/resolv.conf: {e}")
            return False

def _restore_resolv(log_callback=None):
    log = log_callback or _log_callback_default
    try:
        if os.path.exists(RESOLV_BACKUP):
            try:
                subprocess.run(['pkexec','cp', RESOLV_BACKUP, '/etc/resolv.conf'], check=True)
            except Exception:
                subprocess.run(['sudo','cp', RESOLV_BACKUP, '/etc/resolv.conf'], check=True)
            try:
                subprocess.run(['pkexec','rm','-f', RESOLV_BACKUP], check=True)
            except Exception:
                subprocess.run(['sudo','rm','-f', RESOLV_BACKUP], check=True)
            log("Restored original /etc/resolv.conf")
    except Exception as e:
        log(f"Warning: could not restore resolv.conf: {e}")

# Register restore at exit/signals
def _on_exit_restore(signum=None, frame=None):
    try:
        _restore_resolv()
    finally:
        # if called from signal handler, exit
        if signum is not None:
            os._exit(0)

atexit.register(_restore_resolv)
for s in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(s, _on_exit_restore)
    except Exception:
        pass

# Existing functions (test_ssh_connection, check_udpgw_status, etc.) remain unchanged
# ... (the file continues) ...

def test_ssh_connection(host, port, username, auth_method, password, ssh_key_path, log_callback=None):
    def log(message):
        if log_callback:
            log_callback(message)
    try:
        log(f"🔌 Attempting SSH: {username}@{host}:{port}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if auth_method == "SSH Key":
            key_path = os.path.expanduser(ssh_key_path)
            if not os.path.exists(key_path):
                log(f"❌ SSH key file not found: {key_path}")
                return False
            key = None
            key_errors = []
            try:
                key = paramiko.RSAKey.from_private_key_file(key_path)
            except Exception as e:
                key_errors.append(f"RSA: {e}")
            if not key:
                try:
                    key = paramiko.Ed25519Key.from_private_key_file(key_path)
                except Exception as e:
                    key_errors.append(f"Ed25519: {e}")
            if not key:
                try:
                    key = paramiko.DSSKey.from_private_key_file(key_path)
                except Exception as e:
                    key_errors.append(f"DSS: {e}")
            if not key:
                try:
                    key = paramiko.ECDSAKey.from_private_key_file(key_path)
                except Exception as e:
                    key_errors.append(f"ECDSA: {e}")
            if not key:
                log(f"❌ Could not load SSH key. Tried: {', '.join(key_errors)}")
                return False
            ssh.connect(host, port=port, username=username, pkey=key, timeout=10)
        else:
            ssh.connect(host, port=port, username=username, password=password, timeout=10)
        ssh.close()
        log(f"✅ SSH connection successful")
        return True
    except Exception as e:
        log(f"❌ SSH connection failed: {type(e).__name__}: {str(e)}")
        return False

def check_udpgw_status(udpgw_port=7300):
    try:
        result = subprocess.run(['ss', '-tuln'], capture_output=True, text=True, timeout=2)
        return f'127.0.0.1:{udpgw_port}' in result.stdout
    except:
        return False

def create_tun_vpn(host, port, username, auth_method, password, ssh_key_path, udpgw_port=7300, dns_servers='8.8.8.8, 8.8.4.4', log_callback=None):
    def log(message):
        if log_callback:
            log_callback(message)

    try:
        log(f"Creating tun2socks VPN (UDP Gateway: {udpgw_port})...")

        # Parse DNS servers
        dns_list = [dns.strip() for dns in dns_servers.split(',') if dns.strip()]
        primary_dns = dns_list[0] if len(dns_list) > 0 else '8.8.8.8'
        secondary_dns = dns_list[1] if len(dns_list) > 1 else '8.8.4.4'

        # Set system DNS to provided servers (backup previous)
        _backup_resolv(log_callback=log)
        if _write_resolv(dns_list, log_callback=log):
            log(f"System DNS set to: {', '.join(dns_list)} (backup created: {RESOLV_BACKUP})")
        else:
            log("Warning: Could not update system DNS. DNS leak may occur.")

        # existing VPN creation logic continues...
        # Start SOCKS proxy, start tun2socks, etc.
        # NOTE: ensure cleanup restores resolv on disconnect (registered above)
        # ... (rest of function unchanged) ...

        import random
        rand_suffix = random.randint(10000, 99999)

        # Find Python SSH SOCKS script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ssh_script = os.path.join(script_dir, 'ssh_socks_simple.py')
        if not os.path.exists(ssh_script):
            ssh_script = '/usr/local/bin/ssh_socks_simple.py'

        # Start Python SSH SOCKS proxy
        if auth_method == "SSH Key":
            ssh_cmd = [
                'python3', '-u',
                ssh_script,
                host,
                str(port),
                username,
                ssh_key_path,
                '1080',
                'key'
            ]
        else:
            ssh_cmd = [
                'python3', '-u',
                ssh_script,
                host,
                str(port),
                username,
                password,
                '1080',
                'password'
            ]

        socks_log = f'/tmp/vpn_socks_{rand_suffix}.log'
        with open(socks_log, 'w') as log_file:
            ssh_process = subprocess.Popen(
                ssh_cmd,
                stdout=log_file,
                stderr=log_file
            )

        password_file = None
        log(f"SSH SOCKS proxy started (PID: {ssh_process.pid})")
        time.sleep(3)

        if ssh_process.poll() is not None:
            with open(socks_log, 'r') as f:
                output = f.read()
            log(f"❌ SSH process died: {output}")
            # restore resolv if failing early
            _restore_resolv(log_callback=log)
            return (False, None)

        # Wait for SOCKS proxy ready
        log("Waiting for SOCKS proxy...")
        socks_ready = False
        for i in range(10):
            time.sleep(1)
            if ssh_process.poll() is not None:
                with open(socks_log, 'r') as f:
                    output = f.read()
                log(f"❌ SSH process died while waiting: {output}")
                _restore_resolv(log_callback=log)
                return (False, None)
            # quick socket check
            try:
                import socket
                s = socket.socket()
                s.settimeout(0.5)
                s.connect(("127.0.0.1", 1080))
                s.close()
                socks_ready = True
                break
            except Exception:
                pass

        if not socks_ready:
            with open(socks_log, 'r') as f:
                output = f.read()
            log(f"❌ SOCKS proxy not ready: {output}")
            _restore_resolv(log_callback=log)
            return (False, None)

        # Continue TUN creation...
        # (the rest of your function's TUN / tun2socks launching logic should follow here)
        # Make sure cleanup code calls _restore_resolv() when VPN is stopped.

        return (True, {"socks_pid": ssh_process.pid})
    except Exception as e:
        log(f"❌ create_tun_vpn failed: {type(e).__name__}: {str(e)}")
        _restore_resolv(log_callback=log)
        return (False, None)
