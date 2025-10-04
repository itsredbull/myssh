#!/usr/bin/env python3
"""
Simple SSH Dynamic Port Forward using paramiko
Uses paramiko's built-in forward functionality
"""

import sys
import paramiko
import socket
import select
import threading


def forward_tunnel(local_port, remote_host, remote_port, transport):
    """Forward a local port to remote host via SSH transport"""

    class ForwardServer(threading.Thread):
        def __init__(self, local_port, transport):
            threading.Thread.__init__(self)
            self.daemon = False
            self.local_port = local_port
            self.transport = transport

        def run(self):
            # Create server socket
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', self.local_port))
            server.listen(100)

            print(f"SOCKS proxy active on 127.0.0.1:{self.local_port}", flush=True)

            while True:
                try:
                    client_sock, addr = server.accept()
                    # Handle in separate thread
                    t = threading.Thread(target=self.handle_socks, args=(client_sock,))
                    t.daemon = False
                    t.start()
                except Exception as e:
                    print(f"Accept error: {e}", flush=True)
                    break

        def handle_socks(self, client_sock):
            """Handle SOCKS5 connection"""
            try:
                # SOCKS5 handshake
                data = client_sock.recv(262)
                if len(data) < 2 or data[0] != 0x05:
                    client_sock.close()
                    return

                # No auth required
                client_sock.send(b'\x05\x00')

                # Get connection request
                data = client_sock.recv(4)
                if len(data) < 4:
                    client_sock.close()
                    return

                if data[1] != 0x01:  # Only CONNECT supported
                    client_sock.close()
                    return

                atyp = data[3]

                # Get destination
                if atyp == 0x01:  # IPv4
                    addr_bytes = client_sock.recv(4)
                    addr = socket.inet_ntoa(addr_bytes)
                elif atyp == 0x03:  # Domain
                    addr_len = client_sock.recv(1)[0]
                    addr = client_sock.recv(addr_len).decode('utf-8')
                else:
                    client_sock.close()
                    return

                # Get port
                port_bytes = client_sock.recv(2)
                port = int.from_bytes(port_bytes, 'big')

                # Open SSH channel
                try:
                    channel = self.transport.open_channel(
                        'direct-tcpip',
                        (addr, port),
                        ('127.0.0.1', 0)
                    )
                except Exception as e:
                    # Connection refused
                    client_sock.send(b'\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00')
                    client_sock.close()
                    return

                # Success
                client_sock.send(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')

                # Relay data bidirectionally
                while True:
                    r, w, x = select.select([client_sock, channel], [], [], 1.0)

                    if client_sock in r:
                        data = client_sock.recv(8192)
                        if len(data) == 0:
                            break
                        channel.send(data)

                    if channel in r:
                        data = channel.recv(8192)
                        if len(data) == 0:
                            break
                        client_sock.send(data)

                    # Check if transport is still active
                    if not self.transport.is_active():
                        break

            except Exception as e:
                pass
            finally:
                try:
                    client_sock.close()
                except:
                    pass
                try:
                    channel.close()
                except:
                    pass

    return ForwardServer(local_port, transport)


if __name__ == "__main__":
    if len(sys.argv) < 6 or len(sys.argv) > 7:
        print("Usage: ssh_socks_simple.py <host> <port> <user> <password|key_path> <local_port> [auth_method]")
        print("  auth_method: 'password' (default) or 'key'")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    user = sys.argv[3]
    auth_credential = sys.argv[4]
    local_port = int(sys.argv[5])
    auth_method = sys.argv[6] if len(sys.argv) == 7 else 'password'

    try:
        print(f"Connecting to {host}:{port}...", flush=True)

        # Connect SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if auth_method == 'key':
            # SSH key authentication
            import os
            key_path = os.path.expanduser(auth_credential)

            if not os.path.exists(key_path):
                print(f"SSH key not found: {key_path}", flush=True)
                sys.exit(1)

            # Try loading different key types
            key = None
            key_errors = []

            # Try RSA
            try:
                key = paramiko.RSAKey.from_private_key_file(key_path)
                print(f"Using RSA key: {key_path}", flush=True)
            except Exception as e:
                key_errors.append(f"RSA: {e}")

            # Try Ed25519
            if not key:
                try:
                    key = paramiko.Ed25519Key.from_private_key_file(key_path)
                    print(f"Using Ed25519 key: {key_path}", flush=True)
                except Exception as e:
                    key_errors.append(f"Ed25519: {e}")

            # Try DSS
            if not key:
                try:
                    key = paramiko.DSSKey.from_private_key_file(key_path)
                    print(f"Using DSS key: {key_path}", flush=True)
                except Exception as e:
                    key_errors.append(f"DSS: {e}")

            # Try ECDSA
            if not key:
                try:
                    key = paramiko.ECDSAKey.from_private_key_file(key_path)
                    print(f"Using ECDSA key: {key_path}", flush=True)
                except Exception as e:
                    key_errors.append(f"ECDSA: {e}")

            if not key:
                print(f"Could not load SSH key. Tried: {', '.join(key_errors)}", flush=True)
                sys.exit(1)

            ssh.connect(
                hostname=host,
                port=port,
                username=user,
                pkey=key,
                timeout=10
            )
        else:
            # Password authentication
            ssh.connect(
                hostname=host,
                port=port,
                username=user,
                password=auth_credential,
                timeout=10
            )

        transport = ssh.get_transport()
        transport.set_keepalive(10)

        print(f"SSH connected", flush=True)

        # Start forward server
        server = forward_tunnel(local_port, host, port, transport)
        server.start()

        # Keep main thread alive
        server.join()

    except Exception as e:
        print(f"Error: {e}", flush=True)
        sys.exit(1)
