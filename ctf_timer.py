#!/usr/bin/env python3
"""
Ouroboros: CTF Tracker
A minimalist, brutal timer for CTF players to enforce detachment.
Built with CustomTkinter. Audio via native Linux players (paplay/aplay).
"""

import customtkinter as ctk
import os
import sys
import tkinter as tk
import wave
import struct
import math
import tempfile
import random
import time
from datetime import datetime
from typing import List, Tuple, Optional

from PIL import Image

# ============== CONFIG / COLORS ==============
BG = "#121212"
TEXT_MUTED = "#888888"
TEXT_LIGHT = "#e5e5e5"
ACCENT_BLUE = "#2563eb"       # Flag Captured
ACCENT_AMBER = "#a78bfa"      # +5 Min (light purple)
ACCENT_CRIMSON = "#7c3aed"    # Timeout / harsh (purple)
ACCENT_GHOST = "#6b7280"      # Drop & Flag
SIDEBAR_BG = "#1a1a1a"
ENTRY_BG = "#1f1f1f"

EGO_LINES: List[str] = [
    "Sunk cost mathematically loses to breadth. Drop it.",
    "The server returned False. It is not personal. Move on.",
    "Your ego is burning the clock. Next category.",
    "You are evaluating a bad assumption. Leave it in the Ghosts list.",
]


def get_asset_path(filename: str) -> str:
    """Return absolute path to asset, works in script mode and PyInstaller onefile."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", filename)


class CTFTimerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Force Tk scaling as early as possible (helps on some Linux setups)
        try:
            import os
            scale = float(os.environ.get("CTF_TIMER_SCALE", "1.35"))
            self.tk.call("tk", "scaling", scale)
        except Exception:
            pass

        self.title("Ouroboros: CTF Tracker")
        self.geometry("1080x680")
        self.minsize(920, 580)
        self.configure(fg_color=BG)

        # Help some Linux environments / docks recognize the app name early
        try:
            self.tk.call("tk", "appname", "Ouroboros")
        except Exception:
            pass

        # Set window icon using bundled logo
        try:
            icon_path = get_asset_path("ouroboros_logo_128.png")
            if os.path.exists(icon_path):
                icon = tk.PhotoImage(file=icon_path)
                self.iconphoto(False, icon)
                self._icon_ref = icon  # keep reference
        except Exception:
            pass

        # Set WM_CLASS + icon name so Linux desktop environments, docks,
        # alt-tab and .desktop files recognize the app as "Ouroboros"
        # instead of the default "Tk".
        try:
            self.tk.call('wm', 'class', self._w, 'Ouroboros')
            self.wm_iconname("Ouroboros: CTF Tracker")
            # also set title explicitly
            self.tk.call('wm', 'title', self._w, 'Ouroboros: CTF Tracker')
        except Exception:
            pass

        # State
        self.default_seconds: int = 20 * 60
        self.remaining_seconds: int = 20 * 60
        self.initial_seconds: int = 20 * 60
        self.problem_start_time: Optional[float] = None
        self.is_running: bool = False
        self.extension_used: bool = False
        self.current_target: str = ""

        self.kills: List[Tuple[str, str]] = []   # (name, "MM:SS")
        self.ghosts: List[Tuple[str, str]] = []  # (name, "MM:SS")

        self.buzzer_path: Optional[str] = None
        self._tick_job: Optional[str] = None
        self.timed_out: bool = False
        self._blink_job: Optional[str] = None

        self._ensure_buzzer()
        self._ensure_success_sound()
        self._ensure_drop_sound()
        self._ensure_plus5_sound()

        # UI Setup
        self._setup_ui()

        # Close handler for persistence
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initial state
        self._update_timer_display()
        self._update_action_buttons()
        self._refresh_sidebar()

        # Dynamic timer font on resize
        self._resize_job = None
        self.bind("<Configure>", self._on_window_configure)
        self.after(150, self._resize_timer_font)

        # Force WM class after window is ready (helps some DEs show correct name instead of Tk)
        self.after(100, self._force_wm_class)

    def _force_wm_class(self):
        try:
            self.tk.call('wm', 'class', self._w, 'Ouroboros')
        except Exception:
            pass

    def _on_window_configure(self, event):
        if event.widget == self:
            if self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(120, self._resize_timer_font)

    def _resize_timer_font(self):
        """Scale the big timer font based on the actual timer container size for perfect fit and centering."""
        if not hasattr(self, 'timer_frame') or not self.timer_frame.winfo_exists():
            return
        if getattr(self, 'timed_out', False) and self.remaining_seconds <= 0:
            return  # keep quote font during timeout
        try:
            tw = self.timer_frame.winfo_width()
            th = self.timer_frame.winfo_height()
            if tw < 20 or th < 20:
                return
            # "20:00" ~5 chars. Conservative to ensure it always fits inside the box with margin.
            # Use ~70% width / 6 for chars, 60% height.
            font_size = max(20, min(200, int((tw * 0.70) / 6.0), int(th * 0.60)))
            self.timer_label.configure(
                font=ctk.CTkFont(family="monospace", size=font_size, weight="bold")
            )
        except Exception:
            pass

    # ------------------- UI BUILD -------------------
    def _setup_ui(self):
        # Main grid: left controls + center timer | right sidebar
        self.grid_columnconfigure(0, weight=3, minsize=520)
        self.grid_columnconfigure(1, weight=2, minsize=320)
        self.grid_rowconfigure(0, weight=1)

        # ===== LEFT / MAIN CONTENT =====
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        main.grid_columnconfigure(0, weight=1)
        # Give the timer (row 6) the majority of vertical space
        main.grid_rowconfigure(5, weight=1)

        # Top branding: logo + title side by side
        top_branding = ctk.CTkFrame(main, fg_color="transparent")
        top_branding.grid(row=0, column=0, sticky="w", pady=(0, 2))

        try:
            logo_path = get_asset_path("ouroboros_logo_128.png")
            if os.path.exists(logo_path):
                pil = Image.open(logo_path)
                ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(42, 42))
                logo_lbl = ctk.CTkLabel(top_branding, image=ctk_img, text="")
                logo_lbl.grid(row=0, column=0, padx=(0, 8))
                self._logo_ref = ctk_img  # prevent GC
        except Exception:
            pass

        header = ctk.CTkLabel(
            top_branding,
            text="OUROBOROS  —  CTF TRACKER",
            font=ctk.CTkFont(family="monospace", size=16, weight="bold"),
            text_color=TEXT_LIGHT
        )
        header.grid(row=0, column=1, sticky="w")

        # Mode selector
        mode_frame = ctk.CTkFrame(main, fg_color="transparent")
        mode_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        mode_frame.grid_columnconfigure((0, 1), weight=1)

        self.mode_var = ctk.StringVar(value="20:00")
        self.mode_btn_20 = ctk.CTkButton(
            mode_frame,
            text="STANDARD\n20:00",
            font=ctk.CTkFont(family="monospace", size=13, weight="bold"),
            fg_color="#1f2937",
            hover_color="#374151",
            text_color=TEXT_LIGHT,
            corner_radius=6,
            height=52,
            command=lambda: self._set_mode(20)
        )
        self.mode_btn_20.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.mode_btn_10 = ctk.CTkButton(
            mode_frame,
            text="BLITZ\n10:00",
            font=ctk.CTkFont(family="monospace", size=13, weight="bold"),
            fg_color="#1f2937",
            hover_color="#374151",
            text_color=TEXT_LIGHT,
            corner_radius=6,
            height=52,
            command=lambda: self._set_mode(10)
        )
        self.mode_btn_10.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        self._highlight_mode()

        # Target input
        target_label = ctk.CTkLabel(
            main,
            text="CURRENT TARGET",
            font=ctk.CTkFont(family="monospace", size=11),
            text_color=TEXT_MUTED
        )
        target_label.grid(row=2, column=0, sticky="w", pady=(8, 2))

        entry_row = ctk.CTkFrame(main, fg_color="transparent")
        entry_row.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        entry_row.grid_columnconfigure(0, weight=1)

        self.target_entry = ctk.CTkEntry(
            entry_row,
            placeholder_text="Enter target name or category",
            font=ctk.CTkFont(family="monospace", size=13),
            fg_color=ENTRY_BG,
            border_color="#333333",
            text_color=TEXT_LIGHT,
            height=38
        )
        self.target_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.target_entry.bind("<Return>", lambda e: self.start_timer())

        clear_btn = ctk.CTkButton(
            entry_row,
            text="✕",
            width=38,
            height=38,
            font=ctk.CTkFont(size=14),
            fg_color="#222222",
            hover_color="#3f3f3f",
            text_color=TEXT_MUTED,
            command=lambda: (self.target_entry.delete(0, "end"), self.target_entry.focus())
        )
        clear_btn.grid(row=0, column=1, sticky="e")

        # Start button
        self.start_btn = ctk.CTkButton(
            main,
            text="START TIMER",
            font=ctk.CTkFont(family="monospace", size=15, weight="bold"),
            fg_color="#111111",
            hover_color="#1f2937",
            text_color="#22c55e",
            border_width=2,
            border_color="#22c55e",
            height=44,
            command=self.start_timer
        )
        self.start_btn.grid(row=4, column=0, sticky="ew", pady=(0, 16))

        # Timer display
        timer_frame = ctk.CTkFrame(main, fg_color=SIDEBAR_BG, corner_radius=8)
        timer_frame.grid(row=5, column=0, sticky="nsew", pady=(4, 12))
        timer_frame.grid_columnconfigure(0, weight=1)
        timer_frame.grid_rowconfigure(0, weight=1)
        timer_frame.grid_rowconfigure(1, weight=0)  # active label small

        # Temporary font; will be resized dynamically
        self.timer_label = ctk.CTkLabel(
            timer_frame,
            text="20:00",
            font=ctk.CTkFont(family="monospace", size=60, weight="bold"),
            text_color=TEXT_MUTED,
            justify="center",
            anchor="center"
        )
        self.timer_label.grid(row=0, column=0, sticky="nsew")
        self.timer_frame = timer_frame  # for resize calculations
        self.timer_frame.bind("<Configure>", lambda e: self.after(80, self._resize_timer_font))

        # Active problem display
        self.active_label = ctk.CTkLabel(
            timer_frame,
            text="",
            font=ctk.CTkFont(family="monospace", size=13),
            text_color=ACCENT_BLUE
        )
        self.active_label.grid(row=1, column=0, pady=(0, 10))

        # Action buttons
        actions = ctk.CTkFrame(main, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        self.flag_btn = ctk.CTkButton(
            actions,
            text="FLAG CAPTURED",
            font=ctk.CTkFont(family="monospace", size=13, weight="bold"),
            fg_color=ACCENT_BLUE,
            hover_color="#1d4ed8",
            text_color="white",
            height=46,
            command=self.flag_captured
        )
        self.flag_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.plus5_btn = ctk.CTkButton(
            actions,
            text="+5 MIN",
            font=ctk.CTkFont(family="monospace", size=13, weight="bold"),
            fg_color=ACCENT_AMBER,
            hover_color="#b45309",
            text_color="white",
            height=46,
            command=self.add_five_minutes
        )
        self.plus5_btn.grid(row=0, column=1, padx=6, sticky="ew")

        self.drop_btn = ctk.CTkButton(
            actions,
            text="DROP & FLAG",
            font=ctk.CTkFont(family="monospace", size=13, weight="bold"),
            fg_color=ACCENT_GHOST,
            hover_color="#4b5563",
            text_color="white",
            height=46,
            command=self.drop_and_flag
        )
        self.drop_btn.grid(row=0, column=2, padx=(6, 0), sticky="ew")

        # Bottom bar: always on top + status
        bottom = ctk.CTkFrame(main, fg_color="transparent")
        bottom.grid(row=7, column=0, sticky="ew", pady=(14, 0))

        self.topmost_var = ctk.BooleanVar(value=False)
        self.topmost_btn = ctk.CTkButton(
            bottom,
            text="",
            width=30,
            height=18,
            fg_color="#4b5563",  # off
            hover_color="#6b7280",
            command=self._toggle_topmost
        )
        self.topmost_btn.grid(row=0, column=0, sticky="w", padx=(0, 5))

        if self.topmost_var.get():
            self.topmost_btn.configure(fg_color=ACCENT_AMBER)

        self.status_label = ctk.CTkLabel(
            bottom,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED
        )
        self.status_label.grid(row=0, column=1, sticky="e")

        # ===== RIGHT SIDEBAR =====
        sidebar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=8)
        sidebar.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        sidebar.grid_rowconfigure(1, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        # Kills header
        kills_header = ctk.CTkLabel(
            sidebar,
            text="KILLS",
            font=ctk.CTkFont(family="monospace", size=12, weight="bold"),
            text_color=ACCENT_BLUE
        )
        kills_header.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self.kills_box = ctk.CTkTextbox(
            sidebar,
            font=ctk.CTkFont(family="monospace", size=12),
            fg_color="#111111",
            text_color=TEXT_LIGHT,
            border_color="#222222",
            wrap="none"
        )
        self.kills_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self.kills_box.configure(state="disabled")
        # Strikethrough tag
        self.kills_box._textbox.tag_config(
            "strike",
            overstrike=True,
            foreground="#666666"
        )

        # Ghosts header
        ghosts_header = ctk.CTkLabel(
            sidebar,
            text="GHOSTS",
            font=ctk.CTkFont(family="monospace", size=12, weight="bold"),
            text_color=ACCENT_GHOST
        )
        ghosts_header.grid(row=2, column=0, sticky="w", padx=12, pady=(6, 4))

        self.ghosts_box = ctk.CTkTextbox(
            sidebar,
            font=ctk.CTkFont(family="monospace", size=12),
            fg_color="#111111",
            text_color=TEXT_LIGHT,
            border_color="#222222",
            wrap="none"
        )
        self.ghosts_box.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.ghosts_box.configure(state="disabled")

        # Sidebar footer actions
        side_footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        side_footer.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        side_footer.grid_columnconfigure(0, weight=1)

        export_btn = ctk.CTkButton(
            side_footer,
            text="EXPORT SESSION",
            font=ctk.CTkFont(family="monospace", size=11),
            fg_color="#222222",
            hover_color="#333333",
            text_color=TEXT_MUTED,
            height=30,
            command=self.export_session
        )
        export_btn.grid(row=0, column=0, sticky="ew")

    def _highlight_mode(self):
        if self.default_seconds == 20 * 60:
            self.mode_btn_20.configure(fg_color=ACCENT_BLUE, text_color="white")
            self.mode_btn_10.configure(fg_color="#1f2937", text_color=TEXT_LIGHT)
        else:
            self.mode_btn_10.configure(fg_color=ACCENT_AMBER, text_color="white")
            self.mode_btn_20.configure(fg_color="#1f2937", text_color=TEXT_LIGHT)

    def _set_mode(self, minutes: int):
        if self.is_running:
            return
        self.default_seconds = minutes * 60
        self.remaining_seconds = self.default_seconds
        self._update_timer_display()
        self._highlight_mode()

    def _toggle_topmost(self):
        val = not self.topmost_var.get()
        self.topmost_var.set(val)
        self.attributes("-topmost", val)
        if val:
            self.topmost_btn.configure(fg_color=ACCENT_AMBER)  # light purple on
        else:
            self.topmost_btn.configure(fg_color="#4b5563")  # off gray

    # ------------------- TIMER CORE -------------------
    def _update_timer_display(self, force_color: Optional[str] = None):
        if getattr(self, 'timed_out', False) and self.remaining_seconds <= 0:
            return  # quote is shown in timer area during timeout
        text = self._format_time(self.remaining_seconds)
        color = force_color or (ACCENT_CRIMSON if self.remaining_seconds <= 0 and not self.is_running else TEXT_MUTED)
        self.timer_label.configure(text=text, text_color=color)

    def _format_time(self, secs: int) -> str:
        m = max(0, secs) // 60
        s = max(0, secs) % 60
        return f"{m:02d}:{s:02d}"

    def _start_blink(self):
        """Start blinking the 00:00 after timeout."""
        if getattr(self, 'timed_out', False):
            self._blink_state = True
            if self._blink_job:
                self.after_cancel(self._blink_job)
            self._do_blink()

    def _do_blink(self):
        if not getattr(self, 'timed_out', False) or self.remaining_seconds != 0:
            return
        color = ACCENT_CRIMSON if getattr(self, '_blink_state', True) else "#555555"
        self.timer_label.configure(text_color=color)
        self._blink_state = not getattr(self, '_blink_state', True)
        self._blink_job = self.after(500, self._do_blink)

    def _get_monospace_font(self, size: int):
        """Try common programming fonts that exist on most Linux systems."""
        candidates = [
            "JetBrains Mono",
            "Fira Code",
            "DejaVu Sans Mono",
            "Liberation Mono",
            "Source Code Pro",
            "monospace",
            "Courier New",
            "Courier",
        ]
        for fam in candidates:
            try:
                f = ctk.CTkFont(family=fam, size=size, weight="bold")
                return f
            except Exception:
                continue
        return ctk.CTkFont(size=size, weight="bold")

    def _update_action_buttons(self):
        running = self.is_running
        post_timeout = getattr(self, 'timed_out', False) and bool(self.current_target)
        can_act = running or post_timeout

        # Start button
        if running:
            self.start_btn.configure(state="disabled", text="RUNNING")
        else:
            self.start_btn.configure(state="normal", text="START TIMER")

        # Action buttons: allow after timeout too (user can still flag/drop/+5)
        state = "normal" if can_act else "disabled"
        self.flag_btn.configure(state=state)
        self.drop_btn.configure(state=state)

        # +5 if can act and not used (even post-timeout)
        if can_act and not self.extension_used:
            self.plus5_btn.configure(state="normal")
        else:
            self.plus5_btn.configure(state="disabled")

        # Mode buttons disabled while running or post-timeout (active problem)
        mstate = "disabled" if can_act else "normal"
        self.mode_btn_20.configure(state=mstate)
        self.mode_btn_10.configure(state=mstate)

        # Target entry: only lock while actively running; allow edit post-timeout to start fresh if desired
        if running:
            self.target_entry.configure(state="disabled")
        else:
            self.target_entry.configure(state="normal")

    def _set_active_display(self, text: str = ""):
        self.active_label.configure(text=text)

    def start_timer(self):
        if self.is_running:
            return

        target = self.target_entry.get().strip()
        if not target:
            self.status_label.configure(text="Enter a target name to start", text_color=ACCENT_AMBER)
            self.after(1800, lambda: self.status_label.configure(text=""))
            return

        # If abandoning a timed-out problem by starting new, auto-ghost it
        if getattr(self, 'timed_out', False) and self.current_target:
            elapsed = self._get_elapsed_seconds()
            time_str = self._format_time(elapsed)
            self.ghosts.append((self.current_target, f"{time_str} timeout"))
            self._refresh_sidebar()

        # Capture
        self.current_target = target
        self.initial_seconds = self.default_seconds
        self.remaining_seconds = self.default_seconds
        self.problem_start_time = time.time()
        self.extension_used = False
        self.is_running = True
        self.timed_out = False
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None

        self._set_active_display(f"▶ {self.current_target}")
        self._update_timer_display()
        self._update_action_buttons()
        self.status_label.configure(text="")

        # Start ticking
        self._schedule_tick()

    def _schedule_tick(self):
        if self._tick_job:
            self.after_cancel(self._tick_job)
        self._tick_job = self.after(1000, self._tick)

    def _tick(self):
        if not self.is_running:
            return

        self.remaining_seconds -= 1
        self._update_timer_display()

        if self.remaining_seconds <= 0:
            self._handle_timeout()
            return

        self._schedule_tick()

    def stop_timer(self, clear_current: bool = True):
        self.is_running = False
        if self._tick_job:
            self.after_cancel(self._tick_job)
            self._tick_job = None
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None
        self.timed_out = False

        # Reset visual timer to current mode default for next run
        self.remaining_seconds = self.default_seconds
        self._update_timer_display()

        self._update_action_buttons()
        if clear_current:
            self._clear_current_problem()

    def _clear_current_problem(self):
        self.current_target = ""
        self.target_entry.delete(0, "end")
        self._set_active_display("")
        self.extension_used = False
        self.problem_start_time = None
        self.timed_out = False
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None

    # ------------------- ACTIONS -------------------
    def add_five_minutes(self):
        if not (self.is_running or getattr(self, 'timed_out', False)) or self.extension_used:
            return
        was_post_timeout = not self.is_running and getattr(self, 'timed_out', False)
        self.remaining_seconds += 5 * 60
        self.extension_used = True
        self.timed_out = False
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None
        if was_post_timeout:
            self.is_running = True
            self._schedule_tick()
        self._update_timer_display()
        self._update_action_buttons()
        self._play_plus5_sound()
        self.status_label.configure(text="+5 added (locked for this problem)", text_color=ACCENT_AMBER)
        self.after(1600, lambda: self.status_label.configure(text="") if not (self.is_running or self.timed_out) else None)

    def flag_captured(self):
        if not (self.is_running or getattr(self, 'timed_out', False)):
            return

        name = self.current_target
        elapsed = self._get_elapsed_seconds()
        time_str = self._format_time(elapsed)

        self.kills.append((name, time_str))
        self._refresh_sidebar()

        # Play positive success sound (Mario-style)
        self._play_success_sound()

        self.timed_out = False
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None
        self.stop_timer(clear_current=True)
        self._update_timer_display()  # reset color

    def drop_and_flag(self):
        if not (self.is_running or getattr(self, 'timed_out', False)):
            return

        name = self.current_target
        elapsed = self._get_elapsed_seconds()
        time_str = self._format_time(elapsed)

        self.ghosts.append((name, time_str))
        self._refresh_sidebar()

        # Play drop sound
        self._play_drop_sound()

        self.timed_out = False
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None
        self.stop_timer(clear_current=True)
        self._update_timer_display()

    def _get_elapsed_seconds(self) -> int:
        if self.problem_start_time:
            return max(0, int(time.time() - self.problem_start_time))
        # Fallback to initial - remaining (less accurate if +5 used)
        return max(0, self.initial_seconds - self.remaining_seconds)

    # ------------------- TIMEOUT / EGO DROP -------------------
    def _handle_timeout(self):
        self.is_running = False
        if self._tick_job:
            self.after_cancel(self._tick_job)
            self._tick_job = None

        # Visual: show quote in the timer area (where timer is displayed)
        self.remaining_seconds = 0
        self.timed_out = True
        quote = random.choice(EGO_LINES)
        # Use a readable size for the quote in the box
        self.timer_label.configure(
            text=quote,
            text_color=ACCENT_CRIMSON,
            font=ctk.CTkFont(family="monospace", size=16, weight="bold")
        )
        self._update_action_buttons()

        # Play sound
        self._play_buzzer()

        # Lock UI + modal overlay 
        self._show_ego_overlay()

    def _show_ego_overlay(self):
        # Disable everything hard
        self._set_all_controls_disabled(True)

        overlay = ctk.CTkToplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.configure(fg_color=BG)

        # Larger size, scaled for HiDPI, centered on screen for prominent "windowed fullscreen" feel
        scale = float(os.environ.get("CTF_TIMER_SCALE", "1.35"))
        popup_width = int(800 * scale)
        popup_height = int(340 * scale)
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - popup_width) // 2
        y = (screen_h - popup_height) // 2
        overlay.geometry(f"{popup_width}x{popup_height}+{x}+{y}")

        # Use inner frame for better alignment/padding
        inner = ctk.CTkFrame(overlay, fg_color=BG)
        inner.pack(expand=True, fill="both", padx=30, pady=25)

        # Content - larger, minimal, no quote here (quote shown in main timer area)
        title = ctk.CTkLabel(
            inner,
            text="⏱  TIME'S UP",
            font=ctk.CTkFont(family="monospace", size=28, weight="bold"),
            text_color=ACCENT_CRIMSON
        )
        title.pack(pady=(10, 5))

        sub = ctk.CTkLabel(
            inner,
            text="4 seconds to detach.",
            font=ctk.CTkFont(family="monospace", size=16),
            text_color=TEXT_LIGHT
        )
        sub.pack(pady=(5, 10))

        # Auto close + re-enable (keep timer at 00:00 blinking, allow user to act)
        def finish():
            try:
                overlay.destroy()
            except Exception:
                pass
            self._set_all_controls_disabled(False)
            # set back to 00:00 in timer area
            self.timer_label.configure(
                text="00:00",
                text_color=ACCENT_CRIMSON,
                font=ctk.CTkFont(family="monospace", size=60, weight="bold")  # will be resized
            )
            self._start_blink()
            # restore correct per-state button enables (post-timeout allows actions)
            self._update_action_buttons()
            # Do NOT reset or clear target.
            # Timer stays at 00:00 (blinking), user can still Drop/Flag/+5 the current one.

        overlay.after(4000, finish)
        overlay.grab_set()

    def _set_all_controls_disabled(self, disabled: bool):
        state = "disabled" if disabled else "normal"
        for btn in (self.start_btn, self.flag_btn, self.plus5_btn, self.drop_btn,
                    self.mode_btn_20, self.mode_btn_10):
            btn.configure(state=state)
        self.target_entry.configure(state=state)
        self.topmost_btn.configure(state=state)

    # ------------------- SIDEBAR -------------------
    def _refresh_sidebar(self):
        # Kills
        self.kills_box.configure(state="normal")
        self.kills_box.delete("1.0", "end")
        for name, t in self.kills:
            # Show both the markdown-style strikethrough text + real overstrike tag
            line = f"~~{name} ({t})~~\n"
            self.kills_box.insert("end", line)
            last_line_start = self.kills_box.index("end-2l")
            last_line_end = self.kills_box.index("end-1l")
            try:
                self.kills_box._textbox.tag_add("strike", last_line_start, last_line_end)
            except Exception:
                pass  # fallback to the ~~ visual only
        self.kills_box.configure(state="disabled")

        # Ghosts
        self.ghosts_box.configure(state="normal")
        self.ghosts_box.delete("1.0", "end")
        for name, t in self.ghosts:
            self.ghosts_box.insert("end", f"{name}  ({t})\n")
        self.ghosts_box.configure(state="disabled")

    # ------------------- PERSISTENCE -------------------
    def export_session(self):
        if not self.kills and not self.ghosts:
            self.status_label.configure(text="Nothing to export yet", text_color=TEXT_MUTED)
            self.after(1400, lambda: self.status_label.configure(text=""))
            return

        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"ctf_session_{date_str}.md"

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# CTF Session — {date_str}\n\n")
                f.write("**Ouroboros: CTF Tracker Log**\n\n")

                f.write("## KILLS (Solved)\n\n")
                if self.kills:
                    for name, t in self.kills:
                        f.write(f"- ~~{name} ({t})~~\n")
                else:
                    f.write("_None_\n")

                f.write("\n## GHOSTS (Flagged / Unsolved)\n\n")
                if self.ghosts:
                    for name, t in self.ghosts:
                        f.write(f"- {name} ({t})\n")
                else:
                    f.write("_None_\n")

                f.write("\n---\n")
                f.write(f"Generated by Ouroboros CTF Tracker on {datetime.now().isoformat(timespec='seconds')}\n")

            self.status_label.configure(text=f"Exported → {filename}", text_color=ACCENT_BLUE)
            self.after(2200, lambda: self.status_label.configure(text=""))
        except Exception as e:
            self.status_label.configure(text=f"Export failed: {e}", text_color=ACCENT_CRIMSON)

    def on_closing(self):
        try:
            self.export_session()
        except Exception:
            pass
        self.destroy()

    # ------------------- AUDIO -------------------
    def _ensure_buzzer(self):
        self.buzzer_path = os.path.join(tempfile.gettempdir(), "ouroboros_ctf_buzzer.wav")
        if not os.path.exists(self.buzzer_path):
            self._generate_buzzer(self.buzzer_path)

    def _generate_buzzer(self, path: str):
        """Generate a harsh, jarring multi-beep buzzer (stdlib only). ~4.5s"""
        framerate = 44100
        # ~4.5s total: many short harsh bursts
        with wave.open(path, "w") as wf:
            wf.setparams((1, 2, framerate, 0, "NONE", "not compressed"))
            samples = []
            freqs = [980, 1240, 920, 1350]  # harsh alternating
            beep_len = int(0.12 * framerate)
            gap_len = int(0.08 * framerate)

            for i in range(18):
                f = freqs[i % len(freqs)]
                # Basic sine + light distortion for harshness
                for n in range(beep_len):
                    t = n / framerate
                    val = 0.85 * math.sin(2 * math.pi * f * t)
                    val += 0.35 * math.sin(2 * math.pi * (f * 1.97) * t)  # harmonic
                    val = max(min(val, 1.0), -1.0)
                    samples.append(int(val * 32767))
                samples.extend([0] * gap_len)

            for s in samples:
                wf.writeframes(struct.pack("<h", s))

    def _play_buzzer(self):
        if not self.buzzer_path or not os.path.exists(self.buzzer_path):
            # fallback terminal bell (usually works in terminals)
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            return

        # Linux-first playback via installed audio utils (paplay / pw-play / aplay)
        # These are present on virtually all modern desktop Linux installs.
        played = False
        cmds = [
            f'paplay "{self.buzzer_path}"',
            f'pw-play "{self.buzzer_path}"',
            f'aplay -q "{self.buzzer_path}"',
            f'play -q "{self.buzzer_path}" 2>/dev/null',  # sox
        ]
        for cmd in cmds:
            try:
                rc = os.system(cmd + " 2>/dev/null")
                if rc == 0:
                    played = True
                    break
            except Exception:
                continue

        if not played:
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass

    # ------------------- SUCCESS SOUND FOR FLAG CAPTURED (Mario-like) -------------------
    def _ensure_success_sound(self):
        self.success_path = os.path.join(tempfile.gettempdir(), "ouroboros_success.wav")
        if not os.path.exists(self.success_path):
            self._generate_success_sound(self.success_path)

    def _generate_success_sound(self, path: str):
        """Short positive Mario-style success chime (~0.6s ascending tones)."""
        framerate = 44100
        with wave.open(path, "w") as wf:
            wf.setparams((1, 2, framerate, 0, "NONE", "not compressed"))
            samples = []
            # Ascending bright tones for coin / success feel
            tones = [
                (700, 0.07),
                (900, 0.07),
                (1100, 0.09),
                (1300, 0.12),
            ]
            for freq, dur in tones:
                for n in range(int(dur * framerate)):
                    t = n / framerate
                    # main tone + slight higher harmonic for "ding"
                    val = 0.65 * math.sin(2 * math.pi * freq * t)
                    val += 0.25 * math.sin(2 * math.pi * (freq * 1.5) * t)
                    # quick attack/decay envelope
                    env = min(1.0, n / (0.01 * framerate)) * (1.0 - (n / (dur * framerate)))
                    val *= env
                    val = max(min(val, 0.9), -0.9)
                    samples.append(int(val * 32767))
                # tiny separation
                samples.extend([0] * int(0.02 * framerate))
            for s in samples:
                wf.writeframes(struct.pack("<h", s))

    def _play_success_sound(self):
        if not hasattr(self, "success_path") or not os.path.exists(self.success_path):
            self._ensure_success_sound()
        if not self.success_path or not os.path.exists(self.success_path):
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            return
        played = False
        cmds = [
            f'paplay "{self.success_path}"',
            f'pw-play "{self.success_path}"',
            f'aplay -q "{self.success_path}"',
        ]
        for cmd in cmds:
            try:
                rc = os.system(cmd + " 2>/dev/null")
                if rc == 0:
                    played = True
                    break
            except Exception:
                continue
        if not played:
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass

    # Drop sound (short low "thud" for Drop & Flag)
    def _ensure_drop_sound(self):
        self.drop_path = os.path.join(tempfile.gettempdir(), "ouroboros_drop.wav")
        if not os.path.exists(self.drop_path):
            self._generate_drop_sound(self.drop_path)

    def _generate_drop_sound(self, path: str):
        """Short low descending tone for drop action."""
        framerate = 44100
        with wave.open(path, "w") as wf:
            wf.setparams((1, 2, framerate, 0, "NONE", "not compressed"))
            samples = []
            # Low descending for "drop"
            tones = [
                (350, 0.1),
                (280, 0.12),
                (220, 0.15),
            ]
            for freq, dur in tones:
                for n in range(int(dur * framerate)):
                    t = n / framerate
                    val = 0.6 * math.sin(2 * math.pi * freq * t)
                    val += 0.15 * math.sin(2 * math.pi * freq * 0.5 * t)
                    env = (1.0 - (n / (dur * framerate))) * 0.9
                    val *= env
                    val = max(min(val, 0.7), -0.7)
                    samples.append(int(val * 32767))
                samples.extend([0] * int(0.03 * framerate))
            for s in samples:
                wf.writeframes(struct.pack("<h", s))

    def _play_drop_sound(self):
        if not hasattr(self, "drop_path") or not os.path.exists(self.drop_path):
            self._ensure_drop_sound()
        if not self.drop_path or not os.path.exists(self.drop_path):
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            return
        played = False
        cmds = [
            f'paplay "{self.drop_path}"',
            f'pw-play "{self.drop_path}"',
            f'aplay -q "{self.drop_path}"',
        ]
        for cmd in cmds:
            try:
                rc = os.system(cmd + " 2>/dev/null")
                if rc == 0:
                    played = True
                    break
            except Exception:
                continue
        if not played:
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass

    # +5 Min sound (short positive "up" tone)
    def _ensure_plus5_sound(self):
        self.plus5_path = os.path.join(tempfile.gettempdir(), "ouroboros_plus5.wav")
        if not os.path.exists(self.plus5_path):
            self._generate_plus5_sound(self.plus5_path)

    def _generate_plus5_sound(self, path: str):
        """Short positive up tone for +5 Min (like power-up)."""
        framerate = 44100
        with wave.open(path, "w") as wf:
            wf.setparams((1, 2, framerate, 0, "NONE", "not compressed"))
            samples = []
            tones = [
                (600, 0.06),
                (850, 0.08),
            ]
            for freq, dur in tones:
                for n in range(int(dur * framerate)):
                    t = n / framerate
                    val = 0.65 * math.sin(2 * math.pi * freq * t)
                    val += 0.2 * math.sin(2 * math.pi * (freq * 1.6) * t)
                    env = min(1.0, n / (0.01 * framerate)) * (1.0 - n / (dur * framerate) * 0.7)
                    val *= env
                    val = max(min(val, 0.8), -0.8)
                    samples.append(int(val * 32767))
                samples.extend([0] * int(0.02 * framerate))
            for s in samples:
                wf.writeframes(struct.pack("<h", s))

    def _play_plus5_sound(self):
        if not hasattr(self, "plus5_path") or not os.path.exists(self.plus5_path):
            self._ensure_plus5_sound()
        if not self.plus5_path or not os.path.exists(self.plus5_path):
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            return
        played = False
        cmds = [
            f'paplay "{self.plus5_path}"',
            f'pw-play "{self.plus5_path}"',
            f'aplay -q "{self.plus5_path}"',
        ]
        for cmd in cmds:
            try:
                rc = os.system(cmd + " 2>/dev/null")
                if rc == 0:
                    played = True
                    break
            except Exception:
                continue
        if not played:
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass


def main():
    ctk.set_appearance_mode("dark")

    # === HIGH-DPI / SCALING FIX ===
    # On modern Linux (GNOME, KDE, Wayland, HiDPI screens) tkinter/CustomTkinter
    # often renders fonts and widgets too small. These two calls are the most
    # effective fix. Tune the number (1.2 - 1.8) to taste for your display.
    # You can also override with: CTF_TIMER_SCALE=1.5 python3 ctf_timer.py
    import os
    scale = float(os.environ.get("CTF_TIMER_SCALE", "1.35"))
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(1.0)

    app = CTFTimerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
