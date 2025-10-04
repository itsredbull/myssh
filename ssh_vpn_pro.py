#!/usr/bin/env python3
"""
SSH VPN Pro - Mobile-Style UI
Tabs at bottom, compact layout, HUGE animations!
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
import threading
import subprocess
import time
import os
import json
import math
import socket
from pathlib import Path
from datetime import datetime

try:
    from vpn_core import test_ssh_connection, create_tun_vpn, check_udpgw_status, create_stunnel_config, start_stunnel
    VPN_CORE_AVAILABLE = True
except ImportError:
    VPN_CORE_AVAILABLE = False
    print("Warning: vpn_core.py not found")

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("Warning: pystray not installed (system tray disabled)")

# ===== COLORS =====
COLORS = {
    'bg_dark': '#1a1d29',
    'bg_card': '#252936',
    'bg_lighter': '#2f3443',
    'bg_input': '#353a4a',
    'accent_green': '#00e096',
    'accent_blue': '#4f7cff',
    'accent_orange': '#ff9f43',
    'accent_red': '#ff6b6b',
    'text_white': '#ffffff',
    'text_gray': '#9ca3af',
    'text_dark': '#6b7280',
}


# ===== HUGE ANIMATED BUTTON =====
class HugeConnectButton(tk.Canvas):
    """Massive animated connect button"""

    def __init__(self, parent, command=None, **kwargs):
        super().__init__(parent, width=180, height=180,
                        bg=COLORS['bg_card'], highlightthickness=0, **kwargs)

        self.command = command
        self.is_connected = False
        self.is_connecting = False

        self.radius = 70
        self.center_x = 90
        self.center_y = 90

        # Glow circle
        self.glow_circle = self.create_oval(
            self.center_x - self.radius - 8,
            self.center_y - self.radius - 8,
            self.center_x + self.radius + 8,
            self.center_y + self.radius + 8,
            fill='', outline=COLORS['accent_blue'], width=0
        )

        # Button circle
        self.button_circle = self.create_oval(
            self.center_x - self.radius,
            self.center_y - self.radius,
            self.center_x + self.radius,
            self.center_y + self.radius,
            fill=COLORS['accent_blue'], outline='', width=0
        )

        # Icon
        self.power_icon = self.create_text(
            self.center_x, self.center_y,
            text="⚡", font=('Segoe UI', 42),
            fill=COLORS['text_white']
        )

        # Bindings
        self.tag_bind(self.button_circle, '<Button-1>', self._on_click)
        self.tag_bind(self.power_icon, '<Button-1>', self._on_click)

        self.pulse_angle = 0
        self.glow_size = 0
        self.animation_id = None

    def _on_click(self, event=None):
        if self.command:
            self.command()

    def set_connecting(self):
        self.is_connecting = True
        self.is_connected = False
        self.itemconfig(self.button_circle, fill=COLORS['accent_orange'])
        self.itemconfig(self.power_icon, text="●")
        self._start_pulse()

    def set_connected(self):
        self.is_connecting = False
        self.is_connected = True
        self._stop_pulse()
        self.itemconfig(self.button_circle, fill=COLORS['accent_green'])
        self.itemconfig(self.power_icon, text="✓")
        self._start_glow()

    def set_disconnected(self):
        self.is_connecting = False
        self.is_connected = False
        self._stop_pulse()
        self._stop_glow()
        self.itemconfig(self.button_circle, fill=COLORS['accent_blue'])
        self.itemconfig(self.power_icon, text="⚡")

    def _start_pulse(self):
        self._animate_pulse()

    def _stop_pulse(self):
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None
        self.coords(
            self.button_circle,
            self.center_x - self.radius,
            self.center_y - self.radius,
            self.center_x + self.radius,
            self.center_y + self.radius
        )

    def _start_glow(self):
        self._animate_glow()

    def _stop_glow(self):
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None
        self.itemconfig(self.glow_circle, width=0)

    def _animate_pulse(self):
        if not self.is_connecting:
            return

        self.pulse_angle += 0.15
        scale = 1.0 + 0.15 * math.sin(self.pulse_angle)

        r = self.radius * scale
        self.coords(
            self.button_circle,
            self.center_x - r,
            self.center_y - r,
            self.center_x + r,
            self.center_y + r
        )

        rotation_frames = ['●', '◐', '◑', '◒', '◓']
        frame_index = int(self.pulse_angle * 2) % len(rotation_frames)
        self.itemconfig(self.power_icon, text=rotation_frames[frame_index])

        self.animation_id = self.after(30, self._animate_pulse)

    def _animate_glow(self):
        if not self.is_connected:
            return

        self.glow_size += 0.1
        width = 4 + 3 * math.sin(self.glow_size)
        self.itemconfig(self.glow_circle, width=int(width), outline=COLORS['accent_green'])
        self.animation_id = self.after(50, self._animate_glow)


# ===== SINGLE INSTANCE LOCK =====
class SingleInstance:
    """Ensure only one instance of the app runs"""

    def __init__(self, port=47285):
        self.port = port
        self.socket = None

    def acquire(self):
        """Try to acquire lock. Returns True if successful."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('127.0.0.1', self.port))
            self.socket.listen(1)  # Must call listen() to actually hold the port
            return True
        except OSError:
            # Port already in use - another instance is running
            return False

    def release(self):
        """Release the lock"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass


# ===== MAIN APP =====
class SSHVPNPro:
    """SSH VPN Pro - Mobile-style layout"""

    def __init__(self):
        # Single instance check (BEFORE creating Tk window)
        self.instance_lock = SingleInstance()
        if not self.instance_lock.acquire():
            # Create temporary root just for the messagebox
            temp_root = tk.Tk()
            temp_root.withdraw()
            messagebox.showerror(
                "Already Running",
                "SSH VPN Pro is already running!\n\nCheck your system tray or taskbar."
            )
            temp_root.quit()
            temp_root.destroy()
            import sys
            sys.exit(1)

        self.root = tk.Tk()
        self.root.title("SSH VPN Pro")

        # Mobile-friendly size (similar to phone screen ratio)
        self.root.geometry("400x700")
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS['bg_dark'])

        # State
        self.connected = False
        self.tunnel_process = None
        self.stunnel_process = None
        self.profiles = {}
        self.current_profile = None
        self.profiles_file = Path.home() / '.ssh_vpn_profiles.json'

        # Security: Ensure profile file has secure permissions on load
        if self.profiles_file.exists():
            os.chmod(self.profiles_file, 0o600)
        self.connection_start_time = None
        self.uptime_timer = None
        self.current_tab = 'home'
        self.tray_icon = None
        self.initial_rx_bytes = 0
        self.initial_tx_bytes = 0

        self.load_profiles()
        self.setup_ui()
        self.setup_tray_icon()
        self.center_window()

    def setup_ui(self):
        """Setup mobile-style UI with bottom tabs"""

        # Main container
        main_container = tk.Frame(self.root, bg=COLORS['bg_dark'])
        main_container.pack(fill=tk.BOTH, expand=True)

        # Content area (fills most of screen)
        self.content_area = tk.Frame(main_container, bg=COLORS['bg_dark'])
        self.content_area.pack(fill=tk.BOTH, expand=True)

        # Bottom tab bar
        tab_bar = tk.Frame(main_container, bg=COLORS['bg_card'], height=70)
        tab_bar.pack(fill=tk.X, side=tk.BOTTOM)
        tab_bar.pack_propagate(False)

        # Tab buttons (4 tabs at bottom)
        self.tab_buttons = {}

        tabs = [
            ('home', '🏠', 'Home'),
            ('config', '📁', 'Profiles'),
            ('logs', '📋', 'Logs'),
            ('about', '👤', 'About')
        ]

        for i, (key, icon, label) in enumerate(tabs):
            btn_frame = tk.Frame(tab_bar, bg=COLORS['bg_card'])
            btn_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            btn = tk.Button(
                btn_frame,
                text=f"{icon}\n{label}",
                font=('Segoe UI', 10),
                bg=COLORS['bg_card'],
                fg=COLORS['text_gray'],
                activebackground=COLORS['accent_blue'],
                activeforeground=COLORS['text_white'],
                relief='flat',
                bd=0,
                cursor='hand2',
                padx=5,
                pady=8,
                command=lambda k=key: self.switch_tab(k)
            )
            btn.pack(fill=tk.BOTH, expand=True)
            self.tab_buttons[key] = btn

        # Create tab contents
        self.create_home_tab()
        self.create_config_tab()
        self.create_logs_tab()
        self.create_about_tab()

        # Show home
        self.switch_tab('home')

    def create_home_tab(self):
        """Home/Dashboard tab"""
        self.home_frame = tk.Frame(self.content_area, bg=COLORS['bg_dark'])

        # Header
        header = tk.Frame(self.home_frame, bg=COLORS['bg_dark'])
        header.pack(fill=tk.X, padx=20, pady=(20, 10))

        tk.Label(header, text="SSH VPN Pro",
                font=('Segoe UI', 20, 'bold'),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_white']).pack()

        # Status
        self.status_label = tk.Label(self.home_frame,
                                     text="Not Connected",
                                     font=('Segoe UI', 16, 'bold'),
                                     bg=COLORS['bg_dark'],
                                     fg=COLORS['text_gray'])
        self.status_label.pack(pady=5)

        self.status_subtitle = tk.Label(self.home_frame,
                                        text="Tap to connect",
                                        font=('Segoe UI', 11),
                                        bg=COLORS['bg_dark'],
                                        fg=COLORS['text_dark'])
        self.status_subtitle.pack(pady=(0, 5))

        # Current profile name
        self.profile_label = tk.Label(self.home_frame,
                                      text="No profile selected",
                                      font=('Segoe UI', 10),
                                      bg=COLORS['bg_dark'],
                                      fg=COLORS['accent_blue'])
        self.profile_label.pack(pady=(0, 10))

        # HUGE button
        self.connect_button = HugeConnectButton(self.home_frame, command=self.toggle_connection)
        self.connect_button.pack(pady=10)

        # Stats
        stats_container = tk.Frame(self.home_frame, bg=COLORS['bg_dark'])
        stats_container.pack(fill=tk.X, padx=20, pady=15)

        self.create_stat_row(stats_container, "⏱", "Time", "00:00:00", 'time')
        self.create_stat_row(stats_container, "📊", "Data", "0 MB", 'data')
        self.create_stat_row(stats_container, "🌐", "Server", "None", 'server')
        self.create_stat_row(stats_container, "📡", "UDP", "Inactive", 'udp')

        # Actions
        actions = tk.Frame(self.home_frame, bg=COLORS['bg_dark'])
        actions.pack(fill=tk.X, padx=20, pady=10)

        tk.Button(actions, text="📡 Ping Server",
                 font=('Segoe UI', 10),
                 bg=COLORS['bg_lighter'],
                 fg=COLORS['text_white'],
                 relief='flat',
                 cursor='hand2',
                 command=self.ping_server).pack(fill=tk.X, ipady=8)

    def create_stat_row(self, parent, icon, label, value, key):
        """Compact stat row"""
        row = tk.Frame(parent, bg=COLORS['bg_lighter'])
        row.pack(fill=tk.X, pady=3)

        tk.Label(row, text=icon, font=('Segoe UI', 14),
                bg=COLORS['bg_lighter'], fg=COLORS['text_gray']).pack(side=tk.LEFT, padx=(10, 5))

        tk.Label(row, text=label, font=('Segoe UI', 10),
                bg=COLORS['bg_lighter'], fg=COLORS['text_dark']).pack(side=tk.LEFT)

        value_label = tk.Label(row, text=value, font=('Segoe UI', 10, 'bold'),
                              bg=COLORS['bg_lighter'], fg=COLORS['text_white'])
        value_label.pack(side=tk.RIGHT, padx=10)

        setattr(self, f'{key}_value', value_label)

    def create_config_tab(self):
        """Modern Config tab - Profile cards only (editor in pop-up)"""
        self.config_frame = tk.Frame(self.content_area, bg=COLORS['bg_dark'])

        # Header with + New button
        header = tk.Frame(self.config_frame, bg=COLORS['bg_dark'])
        header.pack(fill=tk.X, padx=15, pady=15)

        tk.Label(header, text="Profiles",
                font=('Segoe UI', 20, 'bold'),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_white']).pack(side=tk.LEFT)

        tk.Button(header, text="+ New",
                 font=('Segoe UI', 11, 'bold'),
                 bg=COLORS['accent_blue'],
                 fg=COLORS['text_white'],
                 relief='flat',
                 cursor='hand2',
                 padx=15,
                 pady=5,
                 command=self.new_profile).pack(side=tk.RIGHT)

        # Profile cards list - scrollable
        cards_frame = tk.Frame(self.config_frame, bg=COLORS['bg_dark'])
        cards_frame.pack(fill=tk.BOTH, expand=True, padx=15)

        tk.Label(cards_frame, text="Your Profiles",
                font=('Segoe UI', 11, 'bold'),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_gray']).pack(anchor='w', pady=(0, 10))

        # Scrollable profile cards canvas
        cards_canvas_frame = tk.Frame(cards_frame, bg=COLORS['bg_dark'])
        cards_canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.profile_canvas = tk.Canvas(cards_canvas_frame, bg=COLORS['bg_dark'], highlightthickness=0)
        self.profile_scrollbar = tk.Scrollbar(cards_canvas_frame, orient="vertical", command=self.profile_canvas.yview)
        self.profile_cards_container = tk.Frame(self.profile_canvas, bg=COLORS['bg_dark'])

        self.profile_cards_container.bind(
            "<Configure>",
            lambda e: self.profile_canvas.configure(scrollregion=self.profile_canvas.bbox("all"))
        )

        self.profile_canvas.create_window((0, 0), window=self.profile_cards_container, anchor="nw")
        self.profile_canvas.configure(yscrollcommand=self.profile_scrollbar.set)

        self.profile_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.profile_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind canvas width to update window width
        def _on_canvas_configure(event):
            self.profile_canvas.itemconfig(self.profile_canvas.find_all()[0], width=event.width)
        self.profile_canvas.bind('<Configure>', _on_canvas_configure)

        # Mouse wheel for profile cards
        def _on_profile_mousewheel(event):
            self.profile_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.profile_canvas.bind("<MouseWheel>", _on_profile_mousewheel)
        self.profile_canvas.bind("<Button-4>", lambda e: self.profile_canvas.yview_scroll(-1, "units"))
        self.profile_canvas.bind("<Button-5>", lambda e: self.profile_canvas.yview_scroll(1, "units"))

        self.update_profile_cards()

    def open_profile_editor(self, profile_name=None):
        """Open pop-up dialog to create/edit profile"""
        self.log(f"Opening editor for: {profile_name if profile_name else 'New Profile'}")

        # Create modal dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("New Profile" if not profile_name else f"Edit: {profile_name}")
        dialog.geometry("500x650")
        dialog.configure(bg=COLORS['bg_dark'])
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (250)
        y = (dialog.winfo_screenheight() // 2) - (325)
        dialog.geometry(f'500x650+{x}+{y}')

        # Main container
        main_container = tk.Frame(dialog, bg=COLORS['bg_dark'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Scrollable content
        canvas = tk.Canvas(main_container, bg=COLORS['bg_dark'], highlightthickness=0)
        scrollbar = tk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['bg_dark'])

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Update canvas window width when canvas resizes
        def _configure_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', _configure_canvas)

        # Mouse wheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Form fields
        fields = {}

        def create_field(label, key, default="", show=None):
            tk.Label(scrollable_frame, text=label, font=('Segoe UI', 10, 'bold'),
                    bg=COLORS['bg_dark'], fg=COLORS['text_white']).pack(anchor='w', pady=(10, 3))
            entry = tk.Entry(scrollable_frame, font=('Segoe UI', 11),
                           bg=COLORS['bg_input'], fg=COLORS['text_white'],
                           relief='flat', bd=0)
            entry.pack(fill=tk.X, ipady=6)
            entry.insert(0, default)
            if show:
                entry.config(show=show)
            fields[key] = entry

        def create_dropdown(label, key, options, default):
            tk.Label(scrollable_frame, text=label, font=('Segoe UI', 10, 'bold'),
                    bg=COLORS['bg_dark'], fg=COLORS['text_white']).pack(anchor='w', pady=(10, 3))
            var = tk.StringVar(value=default)
            dropdown = ttk.Combobox(scrollable_frame, textvariable=var, values=options,
                                   font=('Segoe UI', 11), state='readonly')
            dropdown.pack(fill=tk.X, ipady=4)
            fields[key] = var

            # Toggle TLS fields for protocol
            def on_protocol_change(e):
                protocol = var.get()
                if protocol == "SSH-TLS":
                    fields['sni_container'].pack(fill=tk.X, pady=(10, 0), before=fields['advanced_label'])
                    fields['tls_port_container'].pack(fill=tk.X, pady=(10, 0), before=fields['advanced_label'])
                else:
                    fields['sni_container'].pack_forget()
                    fields['tls_port_container'].pack_forget()

            # Only bind protocol dropdown (auth_method handled separately now)
            if key == 'protocol':
                dropdown.bind('<<ComboboxSelected>>', on_protocol_change)

            return var

        # Load existing profile data
        data = self.profiles.get(profile_name, {}) if profile_name else {}

        # Protocol
        protocol_var = create_dropdown("🔐 Protocol", 'protocol', ["SSH", "SSH-TLS"], data.get('protocol', 'SSH'))

        # Basic fields
        create_field("🌐 Host", 'host', data.get('host', ''))
        create_field("🔌 Port", 'port', data.get('port', '22'))
        create_field("👤 Username", 'username', data.get('username', ''))

        # Password field (create before auth dropdown for reference)
        password_container = tk.Frame(scrollable_frame, bg=COLORS['bg_dark'])
        tk.Label(password_container, text="🔑 Password", font=('Segoe UI', 10, 'bold'),
                bg=COLORS['bg_dark'], fg=COLORS['text_white']).pack(anchor='w', pady=(0, 3))
        password_entry = tk.Entry(password_container, font=('Segoe UI', 11),
                                 bg=COLORS['bg_input'], fg=COLORS['text_white'],
                                 relief='flat', bd=0, show='●')
        password_entry.pack(fill=tk.X, ipady=6)
        password_entry.insert(0, data.get('password', ''))
        fields['password'] = password_entry
        fields['password_container'] = password_container

        # SSH Key field (create before auth dropdown for reference)
        ssh_key_container = tk.Frame(scrollable_frame, bg=COLORS['bg_dark'])
        tk.Label(ssh_key_container, text="🔑 SSH Key File", font=('Segoe UI', 10, 'bold'),
                bg=COLORS['bg_dark'], fg=COLORS['text_white']).pack(anchor='w', pady=(0, 3))

        ssh_key_frame = tk.Frame(ssh_key_container, bg=COLORS['bg_dark'])
        ssh_key_frame.pack(fill=tk.X)

        ssh_key_entry = tk.Entry(ssh_key_frame, font=('Segoe UI', 11),
                                bg=COLORS['bg_input'], fg=COLORS['text_white'],
                                relief='flat', bd=0)
        ssh_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        ssh_key_entry.insert(0, data.get('ssh_key_path', '~/.ssh/id_rsa'))

        def browse_key_file():
            from tkinter import filedialog
            file_path = filedialog.askopenfilename(
                title="Select SSH Private Key",
                initialdir=str(Path.home() / '.ssh'),
                filetypes=[("SSH Keys", "id_*"), ("All files", "*")]
            )
            if file_path:
                ssh_key_entry.delete(0, tk.END)
                ssh_key_entry.insert(0, file_path)

        tk.Button(ssh_key_frame, text="📁",
                 font=('Segoe UI', 11),
                 bg=COLORS['bg_lighter'],
                 fg=COLORS['text_white'],
                 relief='flat',
                 cursor='hand2',
                 padx=10,
                 command=browse_key_file).pack(side=tk.LEFT, padx=(5, 0))

        fields['ssh_key'] = ssh_key_entry
        fields['ssh_key_container'] = ssh_key_container

        # Authentication method dropdown (must be AFTER creating containers)
        # Create label and dropdown manually to get reference to the dropdown widget
        tk.Label(scrollable_frame, text="🔐 Auth Method", font=('Segoe UI', 10, 'bold'),
                bg=COLORS['bg_dark'], fg=COLORS['text_white']).pack(anchor='w', pady=(10, 3))
        auth_var = tk.StringVar(value=data.get('auth_method', 'Password'))
        auth_dropdown = ttk.Combobox(scrollable_frame, textvariable=auth_var, values=["Password", "SSH Key"],
                                    font=('Segoe UI', 11), state='readonly')
        auth_dropdown.pack(fill=tk.X, ipady=4)
        fields['auth_method'] = auth_var
        fields['auth_dropdown'] = auth_dropdown  # Save reference

        # Show/hide password/key fields based on auth method - pack right after dropdown
        if data.get('auth_method', 'Password') == "Password":
            password_container.pack(fill=tk.X, pady=(10, 0))
        else:
            ssh_key_container.pack(fill=tk.X, pady=(10, 0))

        # Bind auth method change AFTER initial packing
        def on_auth_method_change(e):
            auth = auth_var.get()
            # Unpack both first
            fields['password_container'].pack_forget()
            fields['ssh_key_container'].pack_forget()

            # Pack the selected one right after the auth dropdown
            # Get the position in the pack order
            if auth == "Password":
                # Pack password field right after auth dropdown, before TLS fields
                fields['password_container'].pack(fill=tk.X, pady=(10, 0), after=fields['auth_dropdown'])
            else:
                # Pack SSH key field right after auth dropdown, before TLS fields
                fields['ssh_key_container'].pack(fill=tk.X, pady=(10, 0), after=fields['auth_dropdown'])

        auth_dropdown.bind('<<ComboboxSelected>>', on_auth_method_change)

        # TLS fields (hideable)
        sni_container = tk.Frame(scrollable_frame, bg=COLORS['bg_dark'])
        tk.Label(sni_container, text="🌐 SNI Domain", font=('Segoe UI', 10, 'bold'),
                bg=COLORS['bg_dark'], fg=COLORS['text_white']).pack(anchor='w', pady=(0, 3))
        sni_entry = tk.Entry(sni_container, font=('Segoe UI', 11),
                            bg=COLORS['bg_input'], fg=COLORS['text_white'], relief='flat', bd=0)
        sni_entry.pack(fill=tk.X, ipady=6)
        sni_entry.insert(0, data.get('sni_domain', 'www.google.com'))
        fields['sni'] = sni_entry
        fields['sni_container'] = sni_container

        tls_port_container = tk.Frame(scrollable_frame, bg=COLORS['bg_dark'])
        tk.Label(tls_port_container, text="📍 TLS Port", font=('Segoe UI', 10, 'bold'),
                bg=COLORS['bg_dark'], fg=COLORS['text_white']).pack(anchor='w', pady=(0, 3))
        tls_port_entry = tk.Entry(tls_port_container, font=('Segoe UI', 11),
                                 bg=COLORS['bg_input'], fg=COLORS['text_white'], relief='flat', bd=0)
        tls_port_entry.pack(fill=tk.X, ipady=6)
        tls_port_entry.insert(0, data.get('tls_port', '443'))
        fields['tls_port'] = tls_port_entry
        fields['tls_port_container'] = tls_port_container

        # Advanced section
        adv_label = tk.Label(scrollable_frame, text="Advanced", font=('Segoe UI', 11, 'bold'),
                           bg=COLORS['bg_dark'], fg=COLORS['text_gray'])
        adv_label.pack(anchor='w', pady=(20, 3))
        fields['advanced_label'] = adv_label

        create_field("📡 UDP Port", 'udpgw', data.get('udpgw_port', '7300'))
        create_field("🌍 DNS Servers", 'dns', data.get('dns_servers', '8.8.8.8, 8.8.4.4'))

        # Show/hide TLS fields based on initial protocol
        if protocol_var.get() == "SSH-TLS":
            sni_container.pack(fill=tk.X, pady=(10, 0), before=adv_label)
            tls_port_container.pack(fill=tk.X, pady=(10, 0), before=adv_label)

        # Buttons
        btn_frame = tk.Frame(scrollable_frame, bg=COLORS['bg_dark'])
        btn_frame.pack(fill=tk.X, pady=20)

        def save_and_close():
            name = profile_name
            if not name:
                name = simpledialog.askstring("Profile Name", "Enter profile name:", parent=dialog)
                if not name:
                    return

            self.profiles[name] = {
                'protocol': fields['protocol'].get(),
                'host': fields['host'].get().strip(),
                'port': fields['port'].get().strip(),
                'username': fields['username'].get().strip(),
                'auth_method': fields['auth_method'].get(),
                'password': fields['password'].get().strip(),
                'ssh_key_path': fields['ssh_key'].get().strip(),
                'sni_domain': fields['sni'].get().strip(),
                'tls_port': fields['tls_port'].get().strip(),
                'udpgw_port': fields['udpgw'].get().strip(),
                'dns_servers': fields['dns'].get().strip(),
            }

            self.save_profiles()
            self.update_profile_cards()
            self.current_profile = name
            self.profile_label.config(text=f"📁 {name}")
            self.log(f"💾 Saved '{name}'")
            dialog.destroy()

        tk.Button(btn_frame, text="💾 Save Profile", font=('Segoe UI', 12, 'bold'),
                 bg=COLORS['accent_green'], fg=COLORS['text_white'],
                 relief='flat', cursor='hand2', padx=25, pady=10,
                 command=save_and_close).pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="✖ Cancel", font=('Segoe UI', 12),
                 bg=COLORS['bg_lighter'], fg=COLORS['text_white'],
                 relief='flat', cursor='hand2', padx=25, pady=10,
                 command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def create_logs_tab(self):
        """Logs tab"""
        self.logs_frame = tk.Frame(self.content_area, bg=COLORS['bg_dark'])

        # Header
        header = tk.Frame(self.logs_frame, bg=COLORS['bg_dark'])
        header.pack(fill=tk.X, padx=15, pady=15)

        tk.Label(header, text="Activity Logs",
                font=('Segoe UI', 18, 'bold'),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_white']).pack(side=tk.LEFT)

        tk.Button(header, text="✖ Clear",
                 font=('Segoe UI', 11, 'bold'),
                 bg=COLORS['bg_lighter'],
                 fg=COLORS['text_white'],
                 relief='flat',
                 cursor='hand2',
                 padx=15,
                 pady=5,
                 command=self.clear_logs).pack(side=tk.RIGHT)

        # Logs
        self.log_text = scrolledtext.ScrolledText(
            self.logs_frame,
            bg=COLORS['bg_input'],
            fg=COLORS['text_white'],
            font=('Consolas', 9),
            relief='flat',
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        self.log("✨ SSH VPN Pro initialized")

    def create_about_tab(self):
        """About tab"""
        self.about_frame = tk.Frame(self.content_area, bg=COLORS['bg_dark'])

        tk.Label(self.about_frame, text="SSH VPN Pro",
                font=('Segoe UI', 24, 'bold'),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_white']).pack(pady=(50, 10))

        tk.Label(self.about_frame, text="v4.0.0",
                font=('Segoe UI', 14),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_gray']).pack(pady=5)

        tk.Label(self.about_frame, text="Secure SSH Tunnel VPN",
                font=('Segoe UI', 12),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_dark']).pack(pady=20)

        info_text = """
Features:
• SSH & SSH-TLS protocols
• Password & SSH Key authentication
• SNI domain spoofing (SSH-TLS)
• UDP traffic support
• Profile management
• Real-time bandwidth monitoring
• Activity logging
• Modern animated UI

Built with Python & Tkinter
        """

        tk.Label(self.about_frame, text=info_text,
                font=('Segoe UI', 10),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_gray'],
                justify=tk.LEFT).pack(pady=20)

        # Developer credits
        tk.Label(self.about_frame, text="Developed by",
                font=('Segoe UI', 10),
                bg=COLORS['bg_dark'],
                fg=COLORS['text_dark']).pack()

        tk.Label(self.about_frame, text="Mohammad Safarzadeh",
                font=('Segoe UI', 12, 'bold'),
                bg=COLORS['bg_dark'],
                fg=COLORS['accent_green']).pack(pady=5)

        github_link = tk.Label(self.about_frame, text="github.com/itsredbull",
                font=('Segoe UI', 10),
                bg=COLORS['bg_dark'],
                fg=COLORS['accent_blue'],
                cursor='hand2')
        github_link.pack()
        github_link.bind('<Button-1>', lambda e: self.open_github())

    def switch_tab(self, tab_name):
        """Switch tabs"""
        # Hide all
        for frame in [self.home_frame, self.config_frame, self.logs_frame, self.about_frame]:
            frame.pack_forget()

        # Update buttons
        for key, btn in self.tab_buttons.items():
            if key == tab_name:
                btn.config(bg=COLORS['accent_blue'], fg=COLORS['text_white'])
            else:
                btn.config(bg=COLORS['bg_card'], fg=COLORS['text_gray'])

        # Show selected
        if tab_name == 'home':
            self.home_frame.pack(fill=tk.BOTH, expand=True)
        elif tab_name == 'config':
            self.config_frame.pack(fill=tk.BOTH, expand=True)
        elif tab_name == 'logs':
            self.logs_frame.pack(fill=tk.BOTH, expand=True)
        elif tab_name == 'about':
            self.about_frame.pack(fill=tk.BOTH, expand=True)

        self.current_tab = tab_name

    # ===== CONNECTION LOGIC =====
    def toggle_connection(self):
        if self.connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        if self.connected:
            return

        # Get current profile data
        if not self.current_profile or self.current_profile not in self.profiles:
            messagebox.showerror("Error", "Please select a profile from Config tab")
            return

        profile = self.profiles[self.current_profile]

        protocol = profile.get('protocol', 'SSH')
        host = profile.get('host', '').strip()
        port = profile.get('port', '22').strip()
        username = profile.get('username', '').strip()
        auth_method = profile.get('auth_method', 'Password')
        password = profile.get('password', '').strip()
        ssh_key_path = profile.get('ssh_key_path', '').strip()
        udpgw_port = profile.get('udpgw_port', '7300').strip()
        sni_domain = profile.get('sni_domain', 'www.google.com').strip()
        tls_port = profile.get('tls_port', '443').strip()

        # Validate required fields
        if not all([host, port, username]):
            messagebox.showerror("Error", "Please fill host, port, and username")
            return

        # Validate authentication
        if auth_method == "Password" and not password:
            messagebox.showerror("Error", "Password is required")
            return
        elif auth_method == "SSH Key" and not ssh_key_path:
            messagebox.showerror("Error", "SSH key path is required")
            return

        if protocol == "SSH-TLS" and not all([sni_domain, tls_port]):
            messagebox.showerror("Error", "Please fill SNI Domain and TLS Port for SSH-TLS")
            return

        self.status_label.config(text="Connecting...", fg=COLORS['accent_orange'])
        self.status_subtitle.config(text="Please wait...")
        self.connect_button.set_connecting()
        self.update_tray_icon('connecting')

        if protocol == "SSH-TLS":
            self.log(f"🔄 Connecting via SSH-TLS to {host}:{tls_port} (SNI: {sni_domain})...")
        else:
            self.log(f"🔄 Connecting to {host}:{port}...")

        dns = profile.get('dns_servers', '8.8.8.8, 8.8.4.4').strip()

        threading.Thread(target=self._connect_thread,
                        args=(protocol, host, port, username, auth_method, password, ssh_key_path, udpgw_port, sni_domain, tls_port, dns),
                        daemon=True).start()

    def _connect_thread(self, protocol, host, port, username, auth_method, password, ssh_key_path, udpgw_port, sni_domain, tls_port, dns):
        try:
            if not VPN_CORE_AVAILABLE:
                self.log("⚠️ Simulation mode (vpn_core not found)")
                time.sleep(2)
                self.root.after(0, self._connection_success, host)
                return

            # SSH-TLS: Start stunnel first
            if protocol == "SSH-TLS":
                self.log("🔐 Starting stunnel (SSH-over-TLS)...")
                config_path, _ = create_stunnel_config(host, int(tls_port), sni_domain)
                result = start_stunnel(config_path, self.log)

                if not result or result[0] is None:
                    self.log("❌ stunnel failed to start")
                    self.root.after(0, self._connection_failed)
                    return

                self.stunnel_process, local_ssh_port = result
                self.log(f"✅ stunnel running, local port {local_ssh_port} → {host}:{tls_port}")

                # Wait for stunnel to fully establish TLS connection
                self.log("⏳ Waiting for TLS handshake...")
                time.sleep(5)

                # Test SSH connection through stunnel
                self.log(f"🔍 Testing SSH through stunnel to {host}...")
                if not test_ssh_connection('127.0.0.1', local_ssh_port, username, auth_method, password, ssh_key_path, self.log):
                    self.log("❌ SSH through stunnel failed")
                    self.log(f"💡 Check: Server stunnel on {host}:{tls_port}, correct port, SSH forwarding")
                    if self.stunnel_process:
                        try:
                            import os
                            os.kill(self.stunnel_process.pid, 9)
                        except:
                            pass
                    self.root.after(0, self._connection_failed)
                    return

                # Use localhost:local_ssh_port for VPN connection
                ssh_host = '127.0.0.1'
                ssh_port = local_ssh_port
                self.log(f"✅ SSH through stunnel OK (localhost:{local_ssh_port} → {host}:22)")

            else:
                # Regular SSH mode
                self.log("🔍 Testing SSH...")
                if not test_ssh_connection(host, int(port), username, auth_method, password, ssh_key_path, self.log):
                    self.log("❌ SSH failed")
                    self.root.after(0, self._connection_failed)
                    return

                ssh_host = host
                ssh_port = port
                self.log("✅ SSH OK")

            success, tunnel = create_tun_vpn(ssh_host, ssh_port, username, auth_method, password, ssh_key_path,
                                             int(udpgw_port), dns, self.log)

            if success:
                # tunnel is now a tuple: (tunnel_process, ssh_process)
                self.tunnel_process = tunnel
                self.root.after(0, self._connection_success, host)
            else:
                self.log("❌ Tunnel failed")
                # Kill stunnel if it was started
                if protocol == "SSH-TLS" and self.stunnel_process:
                    self.stunnel_process.kill()
                self.root.after(0, self._connection_failed)

        except Exception as e:
            self.log(f"❌ Error: {e}")
            # Kill stunnel if it was started
            if protocol == "SSH-TLS" and self.stunnel_process:
                try:
                    self.stunnel_process.kill()
                except:
                    pass
            self.root.after(0, self._connection_failed)

    def _connection_success(self, host):
        self.connected = True
        self.connection_start_time = time.time()

        # Capture initial network stats
        self.initial_rx_bytes, self.initial_tx_bytes = self.get_network_stats()

        self.status_label.config(text="Connected", fg=COLORS['accent_green'])
        self.status_subtitle.config(text="Secure tunnel active")
        self.connect_button.set_connected()
        self.update_tray_icon('connected')

        self.server_value.config(text=host[:20])

        # Update UDP status from current profile
        if self.current_profile and self.current_profile in self.profiles:
            profile = self.profiles[self.current_profile]
            udpgw_port = profile.get('udpgw_port', '7300')
            self.udp_value.config(text=f"Active:{udpgw_port}", fg=COLORS['accent_green'])
        else:
            self.udp_value.config(text="Active", fg=COLORS['accent_green'])

        self.log(f"✅ Connected to {host}")
        self.start_uptime_timer()

        try:
            subprocess.run(['notify-send', 'SSH VPN Pro', f'Connected to {host}'],
                          check=False, timeout=2)
        except:
            pass

    def _connection_failed(self):
        # Clean up any running processes
        self.log("🧹 Cleaning up failed connection...")

        # Kill stunnel if running
        if self.stunnel_process:
            try:
                self.stunnel_process.terminate()
                self.stunnel_process.wait(timeout=3)
            except:
                try:
                    self.stunnel_process.kill()
                except:
                    pass
            self.stunnel_process = None

        # Kill any leftover processes
        try:
            subprocess.run(['pkill', '-f', 'stunnel'], check=False, timeout=5)
            subprocess.run(['pkill', '-f', 'badvpn-tun2socks'], check=False, timeout=5)
            subprocess.run(['pkill', '-f', 'badvpn-udpgw'], check=False, timeout=5)
        except:
            pass

        self.status_label.config(text="Failed", fg=COLORS['accent_red'])
        self.status_subtitle.config(text="Check credentials")
        self.connect_button.set_disconnected()
        self.update_tray_icon('disconnected')

    def disconnect(self):
        self.log("🔄 Disconnecting...")
        self.stop_uptime_timer()

        # Kill stunnel if running
        if self.stunnel_process:
            try:
                self.log("🔐 Stopping stunnel...")
                self.stunnel_process.terminate()
                self.stunnel_process.wait(timeout=3)
            except:
                try:
                    self.stunnel_process.kill()
                except:
                    pass
            self.stunnel_process = None

        # Kill tunnel processes (now a tuple of (tunnel_process, ssh_process))
        if self.tunnel_process:
            try:
                if isinstance(self.tunnel_process, tuple):
                    tunnel_proc, ssh_proc = self.tunnel_process
                    tunnel_proc.terminate()
                    ssh_proc.terminate()
                    tunnel_proc.wait(timeout=5)
                    ssh_proc.wait(timeout=5)
                else:
                    self.tunnel_process.terminate()
                    self.tunnel_process.wait(timeout=5)
            except:
                try:
                    if isinstance(self.tunnel_process, tuple):
                        self.tunnel_process[0].kill()
                        self.tunnel_process[1].kill()
                    else:
                        self.tunnel_process.kill()
                except:
                    pass

        # Kill all VPN processes
        try:
            subprocess.run(['pkill', '-f', 'ssh_socks_simple.py'], check=False, timeout=5)
            subprocess.run(['pkill', '-f', 'badvpn-tun2socks'], check=False, timeout=5)
            subprocess.run(['pkill', '-f', 'badvpn-udpgw'], check=False, timeout=5)
            subprocess.run(['pkill', '-f', 'stunnel'], check=False, timeout=5)
        except:
            pass

        # Cleanup TUN interface (needs root) - with short timeout
        self.log("🧹 Cleaning up network (enter password within 15 seconds)...")
        cleanup_success = False

        try:
            cleanup_script = '''#!/bin/bash
pkill -f badvpn-tun2socks 2>/dev/null
pkill -f badvpn-udpgw 2>/dev/null
ip link set tun0 down 2>/dev/null
ip tuntap del dev tun0 mode tun 2>/dev/null
cp /tmp/resolv.conf.backup /etc/resolv.conf 2>/dev/null || true
sysctl -w net.ipv6.conf.all.disable_ipv6=0 >/dev/null 2>&1
sysctl -w net.ipv6.conf.default.disable_ipv6=0 >/dev/null 2>&1
exit 0
'''
            with open('/tmp/vpn_cleanup.sh', 'w') as f:
                f.write(cleanup_script)
            os.chmod('/tmp/vpn_cleanup.sh', 0o755)

            # Try cleanup with short timeout
            result = subprocess.run(['pkexec', 'bash', '/tmp/vpn_cleanup.sh'],
                                   timeout=15, check=False, capture_output=True)

            if result.returncode == 0:
                cleanup_success = True
                self.log("✅ Network cleanup complete")
            else:
                self.log("⚠️  Cleanup authentication timed out or cancelled")

        except subprocess.TimeoutExpired:
            self.log("⚠️  Cleanup timed out")
        except Exception as e:
            self.log(f"⚠️  Cleanup error: {e}")

        # If cleanup failed, show recovery instructions
        if not cleanup_success:
            self.log("━" * 50)
            self.log("⚠️  INTERNET MAY NOT WORK!")
            self.log("To fix your internet, run this command in terminal:")
            self.log("   sudo bash /tmp/vpn_cleanup.sh")
            self.log("Or restart your computer to reset network")
            self.log("━" * 50)

            # Show popup warning
            messagebox.showwarning(
                "Network Cleanup Needed",
                "VPN disconnected but network cleanup was cancelled.\n\n"
                "Your internet may not work until you run:\n"
                "   sudo bash /tmp/vpn_cleanup.sh\n\n"
                "Or restart your computer."
            )

        self.connected = False
        self.connection_start_time = None

        self.status_label.config(text="Not Connected", fg=COLORS['text_gray'])
        self.status_subtitle.config(text="Tap to connect")
        self.connect_button.set_disconnected()
        self.update_tray_icon('disconnected')

        self.time_value.config(text="00:00:00")
        self.data_value.config(text="0 MB")
        self.server_value.config(text="None")
        self.udp_value.config(text="Inactive", fg=COLORS['text_white'])

        self.log("✅ Disconnected")

    def ping_server(self):
        # Get current profile
        if not self.current_profile or self.current_profile not in self.profiles:
            messagebox.showerror("Error", "Please select a profile from Config tab")
            return

        host = self.profiles[self.current_profile].get('host', '').strip()

        if not host:
            messagebox.showerror("Error", "No server configured in selected profile")
            return

        self.log(f"📡 Pinging {host}...")

        def do_ping():
            try:
                result = subprocess.run(
                    ['ping', '-c', '3', '-W', '2', host],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                # Parse ping output for average time
                import re
                match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', result.stdout)
                if match:
                    avg_ms = float(match.group(2))
                    self.log(f"✅ Ping: {avg_ms:.1f} ms")
                    self.root.after(0, lambda: messagebox.showinfo("Ping Result", f"{host}\n\nLatency: {avg_ms:.1f} ms"))
                elif '3 received' in result.stdout or '3 packets received' in result.stdout:
                    self.log(f"✅ Ping successful to {host}")
                    self.root.after(0, lambda: messagebox.showinfo("Ping Result", f"{host}\n\nReachable!"))
                else:
                    self.log(f"❌ Ping failed: Host unreachable")
                    self.root.after(0, lambda: messagebox.showerror("Ping Failed", f"{host}\n\nHost unreachable"))

            except subprocess.TimeoutExpired:
                self.log(f"❌ Ping timeout")
                self.root.after(0, lambda: messagebox.showerror("Ping Failed", f"{host}\n\nTimeout"))
            except Exception as e:
                self.log(f"❌ Ping error: {e}")
                self.root.after(0, lambda: messagebox.showerror("Ping Failed", str(e)))

        threading.Thread(target=do_ping, daemon=True).start()

    # ===== PROFILE MANAGEMENT =====
    def load_profiles(self):
        try:
            if self.profiles_file.exists():
                with open(self.profiles_file, 'r') as f:
                    self.profiles = json.load(f)
        except:
            self.profiles = {}

    def save_profiles(self):
        try:
            # Create file with secure permissions (owner read/write only)
            import os

            # Save profiles
            with open(self.profiles_file, 'w') as f:
                json.dump(self.profiles, f, indent=2)

            # Set file permissions to 600 (owner read/write only)
            # This prevents other users from reading your passwords
            os.chmod(self.profiles_file, 0o600)

            self.log("💾 Saved")
        except Exception as e:
            self.log(f"❌ Save error: {e}")

    def update_config_list(self):
        """Update profile cards in the new UI"""
        self.update_profile_cards()

    def update_profile_cards(self):
        """Create visual cards for each saved profile"""
        # Clear existing cards
        for widget in self.profile_cards_container.winfo_children():
            widget.destroy()

        if not self.profiles:
            # Show empty state
            tk.Label(self.profile_cards_container,
                    text="No profiles yet. Tap '+ New' to create one!",
                    font=('Segoe UI', 10),
                    bg=COLORS['bg_dark'],
                    fg=COLORS['text_gray']).pack(pady=30)
            return

        # Create card for each profile
        for name, data in self.profiles.items():
            self.create_profile_card(name, data)

    def create_profile_card(self, name, data):
        """Create a single profile card"""
        card = tk.Frame(self.profile_cards_container,
                       bg=COLORS['bg_card'],
                       relief='flat',
                       bd=0)
        card.pack(fill=tk.X, pady=5, padx=5)

        # Main content area (clickable)
        content = tk.Frame(card, bg=COLORS['bg_card'], cursor='hand2')
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Profile name
        name_label = tk.Label(content,
                             text=name,
                             font=('Segoe UI', 12, 'bold'),
                             bg=COLORS['bg_card'],
                             fg=COLORS['text_white'],
                             cursor='hand2')
        name_label.pack(anchor='w')

        # Host info
        host_info = f"{data.get('username', '')}@{data.get('host', '')}:{data.get('port', '22')}"
        info_label = tk.Label(content,
                             text=host_info,
                             font=('Segoe UI', 9),
                             bg=COLORS['bg_card'],
                             fg=COLORS['text_gray'],
                             cursor='hand2')
        info_label.pack(anchor='w')

        # Protocol badge
        protocol = data.get('protocol', 'SSH')
        badge_color = COLORS['accent_blue'] if protocol == 'SSH' else COLORS['accent_orange']
        badge = tk.Label(content,
                        text=f" {protocol} ",
                        font=('Segoe UI', 8, 'bold'),
                        bg=badge_color,
                        fg=COLORS['text_white'],
                        cursor='hand2')
        badge.pack(anchor='w', pady=(3, 0))

        # Click to select profile
        def select_this_profile(e=None):
            self.current_profile = name
            self.profile_label.config(text=f"📁 {name}")
            self.update_profile_cards()  # Refresh to show selection
            self.log(f"✅ Selected '{name}'")

        name_label.bind('<Button-1>', select_this_profile)
        info_label.bind('<Button-1>', select_this_profile)
        badge.bind('<Button-1>', select_this_profile)
        content.bind('<Button-1>', select_this_profile)

        # Highlight if selected
        if self.current_profile == name:
            card.config(bg=COLORS['accent_blue'], highlightthickness=2, highlightbackground=COLORS['accent_blue'])
            content.config(bg=COLORS['accent_blue'])
            name_label.config(bg=COLORS['accent_blue'])
            info_label.config(bg=COLORS['accent_blue'])
            badge.config(bg=COLORS['accent_green'])

        # Buttons on the right
        btn_frame = tk.Frame(card, bg=COLORS['bg_card'])
        btn_frame.pack(side=tk.RIGHT, padx=5)

        # Edit button
        edit_btn = tk.Button(btn_frame,
                            text="✎",
                            font=('Segoe UI', 14, 'bold'),
                            bg=COLORS['bg_lighter'],
                            fg=COLORS['text_white'],
                            relief='flat',
                            cursor='hand2',
                            padx=10,
                            pady=4,
                            command=lambda: self.load_profile_to_editor(name))
        edit_btn.pack(pady=2)

        # Delete button
        delete_btn = tk.Button(btn_frame,
                              text="✖",
                              font=('Segoe UI', 14, 'bold'),
                              bg=COLORS['bg_lighter'],
                              fg=COLORS['accent_red'],
                              relief='flat',
                              cursor='hand2',
                              padx=10,
                              pady=4,
                              command=lambda: self.delete_profile_card(name))
        delete_btn.pack(pady=2)

    def load_profile_to_editor(self, name):
        """Load a profile into the editor pop-up for editing"""
        if self.connected:
            messagebox.showwarning("Warning", "Disconnect first")
            return

        if name not in self.profiles:
            return

        self.open_profile_editor(name)

    def delete_profile_card(self, name):
        """Delete a profile from a card"""
        if messagebox.askyesno("Delete Profile", f"Delete '{name}'?"):
            if name in self.profiles:
                del self.profiles[name]
                self.save_profiles()
                self.update_profile_cards()

                # Clear current profile if deleted
                if self.current_profile == name:
                    self.current_profile = None
                    self.profile_label.config(text="No profile selected")

                self.log(f"🗑️ Deleted '{name}'")

    def new_profile(self):
        """Open editor pop-up for new profile"""
        if self.connected:
            messagebox.showwarning("Warning", "Disconnect first")
            return

        self.open_profile_editor()


    # ===== TIMER =====
    def get_network_stats(self):
        """Get tun0 interface statistics"""
        try:
            with open('/sys/class/net/tun0/statistics/rx_bytes', 'r') as f:
                rx_bytes = int(f.read().strip())
            with open('/sys/class/net/tun0/statistics/tx_bytes', 'r') as f:
                tx_bytes = int(f.read().strip())
            return rx_bytes, tx_bytes
        except:
            return 0, 0

    def start_uptime_timer(self):
        if self.connected and self.connection_start_time:
            elapsed = int(time.time() - self.connection_start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.time_value.config(text=f"{h:02d}:{m:02d}:{s:02d}")

            # Update data usage
            rx_bytes, tx_bytes = self.get_network_stats()
            total_bytes = (rx_bytes - self.initial_rx_bytes) + (tx_bytes - self.initial_tx_bytes)

            if total_bytes < 1024:
                data_str = f"{total_bytes} B"
            elif total_bytes < 1024 * 1024:
                data_str = f"{total_bytes / 1024:.1f} KB"
            elif total_bytes < 1024 * 1024 * 1024:
                data_str = f"{total_bytes / (1024 * 1024):.1f} MB"
            else:
                data_str = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"

            self.data_value.config(text=data_str)

            # Check UDP gateway status every 5 seconds
            if VPN_CORE_AVAILABLE and elapsed % 5 == 0 and self.current_profile:
                profile = self.profiles.get(self.current_profile, {})
                udpgw_port = int(profile.get('udpgw_port', '7300'))
                if check_udpgw_status(udpgw_port):
                    self.udp_value.config(text=f"Active:{udpgw_port}", fg=COLORS['accent_green'])
                else:
                    self.udp_value.config(text="Failed", fg=COLORS['accent_red'])

            self.uptime_timer = self.root.after(1000, self.start_uptime_timer)

    def stop_uptime_timer(self):
        if self.uptime_timer:
            self.root.after_cancel(self.uptime_timer)
            self.uptime_timer = None

    # ===== LOGGING =====
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)
        else:
            print(log_message.strip())

    def clear_logs(self):
        self.log_text.delete(1.0, tk.END)
        self.log("🗑️ Cleared")

    # ===== SYSTEM TRAY =====
    def setup_tray_icon(self):
        """Setup system tray icon"""
        if not TRAY_AVAILABLE:
            return

        def create_icon_image(color=(79, 124, 255)):
            """Create VPN shield icon"""
            img = Image.new('RGB', (64, 64), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)
            # Draw shield
            draw.polygon([(32, 10), (50, 18), (50, 40), (32, 54), (14, 40), (14, 18)],
                        fill=color, outline=(255, 255, 255))
            return img

        def on_tray_click(icon, item):
            """Show/hide window"""
            if self.root.state() == 'withdrawn':
                self.root.deiconify()
                self.root.lift()
            else:
                self.root.withdraw()

        def on_quit(icon, item):
            """Quit app"""
            icon.stop()
            self.on_closing()

        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem("Show/Hide", on_tray_click, default=True),
            pystray.MenuItem("Quit", on_quit)
        )

        # Create and run tray icon in background thread
        self.tray_icon = pystray.Icon(
            "ssh_vpn_pro",
            create_icon_image(),
            "SSH VPN Pro",
            menu
        )

        def run_tray():
            try:
                self.tray_icon.run()
            except:
                pass

        tray_thread = threading.Thread(target=run_tray, daemon=True)
        tray_thread.start()

    def update_tray_icon(self, status='disconnected'):
        """Update tray icon color based on connection status"""
        if not TRAY_AVAILABLE or not self.tray_icon:
            return

        colors = {
            'disconnected': (79, 124, 255),    # Blue
            'connecting': (255, 159, 67),      # Orange
            'connected': (0, 224, 150)          # Green
        }

        def create_icon_image(color):
            img = Image.new('RGB', (64, 64), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.polygon([(32, 10), (50, 18), (50, 40), (32, 54), (14, 40), (14, 18)],
                        fill=color, outline=(255, 255, 255))
            return img

        self.tray_icon.icon = create_icon_image(colors.get(status, colors['disconnected']))

    def open_github(self):
        """Open GitHub profile in browser"""
        import webbrowser
        webbrowser.open('https://github.com/itsredbull')
        self.log("🔗 Opened GitHub profile")

    # ===== WINDOW =====
    def center_window(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = (self.root.winfo_screenheight() // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f'+{x}+{y}')

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def on_closing(self):
        if self.connected:
            if messagebox.askyesno("Exit", "VPN is connected. Disconnect and exit?"):
                self.disconnect()
                if self.tray_icon:
                    self.tray_icon.stop()
                self.instance_lock.release()
                self.root.after(2000, self.root.destroy)
        else:
            if self.tray_icon:
                self.tray_icon.stop()
            self.instance_lock.release()
            self.root.destroy()


if __name__ == "__main__":
    app = SSHVPNPro()
    app.run()
