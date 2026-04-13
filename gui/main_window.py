"""
gui/main_window.py
──────────────────
J.A.R.V.I.S. holographic-style GUI built with CustomTkinter.

Panels:
  ┌───────────────────────────────┐
  │  HEADER – title + status bar  │
  ├─────────────┬─────────────────┤
  │  LEFT       │  RIGHT          │
  │  Camera     │  Chat / Log     │
  │  panel      │  panel          │
  ├─────────────┴─────────────────┤
  │  BOTTOM – input + controls    │
  └───────────────────────────────┘

Design: dark background + cyan/blue neon accents (JARVIS palette).
"""

from __future__ import annotations
import sys
import time
import math
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Callable, Any

import customtkinter as ctk
import psutil
from PIL import Image, ImageTk
import numpy as np
import cv2
from loguru import logger


# ── Palette ──────────────────────────────────────
BG_DARK   = "#050d1a"
BG_PANEL  = "#0a1628"
BG_INPUT  = "#0d1e38"
ACCENT1   = "#00d4ff"   # cyan
ACCENT2   = "#0077ff"   # blue
ACCENT3   = "#00ff88"   # green status
WARN_COL  = "#ffaa00"
ERR_COL   = "#ff3344"
TXT_MAIN  = "#c8e8ff"
TXT_DIM   = "#4a7fa0"
FONT_MAIN = ("Courier New", 13)
FONT_HED  = ("Courier New", 18, "bold")
FONT_SML  = ("Courier New", 11)


class JarvisWindow:

    def __init__(self,
                 on_command: Callable[[str], None],
                 on_listen_toggle: Callable[[bool], None],
                 on_camera_toggle: Callable[[bool], None],
                 on_register_face: Callable[[str], None]) -> None:

        self._on_command        = on_command
        self._on_listen_toggle  = on_listen_toggle
        self._on_camera_toggle  = on_camera_toggle
        self._on_register_face  = on_register_face

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title("J.A.R.V.I.S.")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)
        self.root.configure(fg_color=BG_DARK)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._listening   = False
        self._camera_on   = False
        self._cpu_var     = tk.StringVar(value="CPU  0%")
        self._ram_var     = tk.StringVar(value="RAM  0%")
        self._status_var  = tk.StringVar(value="STANDBY")
        self._log_lines: list[str] = []

        self._build_ui()
        self._start_sys_monitor()
        self._animate_pulse()

    # ────── Build UI ──────

    def _build_ui(self) -> None:
        self._build_header()
        self._build_main()
        self._build_footer()

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self.root, fg_color=BG_PANEL,
                           corner_radius=0, height=56)
        hdr.pack(fill="x", padx=0, pady=0)
        hdr.pack_propagate(False)

        # Logo
        logo = ctk.CTkLabel(hdr, text="◈ J.A.R.V.I.S.",
                            font=FONT_HED, text_color=ACCENT1)
        logo.pack(side="left", padx=20)

        # Status badge
        self._status_badge = ctk.CTkLabel(
            hdr, textvariable=self._status_var,
            font=FONT_SML, text_color=BG_DARK,
            fg_color=ACCENT3, corner_radius=6,
            padx=10, pady=3,
        )
        self._status_badge.pack(side="left", padx=12)

        # Sys stats
        ctk.CTkLabel(hdr, textvariable=self._cpu_var,
                     font=FONT_SML, text_color=TXT_DIM).pack(side="right", padx=8)
        ctk.CTkLabel(hdr, textvariable=self._ram_var,
                     font=FONT_SML, text_color=TXT_DIM).pack(side="right", padx=8)

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self.root, fg_color=BG_DARK)
        main.pack(fill="both", expand=True, padx=8, pady=4)
        main.columnconfigure(0, weight=4)
        main.columnconfigure(1, weight=6)
        main.rowconfigure(0, weight=1)

        # Left – camera + pulse canvas
        left = ctk.CTkFrame(main, fg_color=BG_PANEL, corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        self._build_camera_panel(left)

        # Right – log
        right = ctk.CTkFrame(main, fg_color=BG_PANEL, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)
        self._build_log_panel(right)

    def _build_camera_panel(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(parent, text="◉ VISUAL FEED",
                     font=FONT_SML, text_color=ACCENT1).pack(anchor="w", padx=12, pady=(10,2))

        # Canvas for camera / pulse animation
        self._cam_canvas = tk.Canvas(parent, bg=BG_DARK, bd=0,
                                     highlightthickness=0, width=340, height=260)
        self._cam_canvas.pack(padx=8, pady=4)

        # Buttons
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=4)

        self._cam_btn = ctk.CTkButton(
            btn_row, text="▶ Camera ON", width=100,
            fg_color=ACCENT2, text_color="white",
            font=FONT_SML, command=self._toggle_camera,
        )
        self._cam_btn.pack(side="left", padx=4)

        ctk.CTkButton(
            btn_row, text="⊕ Register Face", width=110,
            fg_color=BG_INPUT, text_color=ACCENT1,
            border_color=ACCENT1, border_width=1,
            font=FONT_SML, command=self._register_face,
        ).pack(side="left", padx=4)

    def _build_log_panel(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(parent, text="◈ ACTIVITY LOG",
                     font=FONT_SML, text_color=ACCENT1).pack(anchor="w", padx=12, pady=(10,2))

        self._log_box = ctk.CTkTextbox(
            parent, fg_color=BG_DARK, text_color=TXT_MAIN,
            font=FONT_SML, border_color=ACCENT2,
            border_width=1, corner_radius=6,
            state="disabled",
        )
        self._log_box.pack(fill="both", expand=True, padx=8, pady=(2, 8))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self.root, fg_color=BG_PANEL,
                              corner_radius=0, height=80)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # Input row
        row = ctk.CTkFrame(footer, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=12)

        self._input_entry = ctk.CTkEntry(
            row, placeholder_text="Enter command or speak…",
            fg_color=BG_INPUT, text_color=TXT_MAIN,
            border_color=ACCENT2, border_width=1,
            font=FONT_MAIN, height=40,
        )
        self._input_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._input_entry.bind("<Return>", lambda e: self._send_text())

        ctk.CTkButton(
            row, text="SEND", width=70, height=40,
            fg_color=ACCENT2, text_color="white",
            font=FONT_MAIN, command=self._send_text,
        ).pack(side="left", padx=4)

        self._listen_btn = ctk.CTkButton(
            row, text="🎤 LISTEN", width=90, height=40,
            fg_color=BG_INPUT, text_color=ACCENT3,
            border_color=ACCENT3, border_width=1,
            font=FONT_MAIN, command=self._toggle_listen,
        )
        self._listen_btn.pack(side="left", padx=4)

    # ────── Actions ──────

    def _send_text(self) -> None:
        text = self._input_entry.get().strip()
        if not text:
            return
        self._input_entry.delete(0, "end")
        self.append_log(f"YOU: {text}", color=ACCENT3)
        self._on_command(text)

    def _toggle_listen(self) -> None:
        self._listening = not self._listening
        if self._listening:
            self._listen_btn.configure(
                text="■ STOP", fg_color=WARN_COL, text_color=BG_DARK)
        else:
            self._listen_btn.configure(
                text="🎤 LISTEN", fg_color=BG_INPUT, text_color=ACCENT3)
        self._on_listen_toggle(self._listening)

    def _toggle_camera(self) -> None:
        self._camera_on = not self._camera_on
        if self._camera_on:
            self._cam_btn.configure(text="■ Camera OFF", fg_color=ERR_COL)
        else:
            self._cam_btn.configure(text="▶ Camera ON", fg_color=ACCENT2)
            # Clear canvas
            self._cam_canvas.delete("all")
        self._on_camera_toggle(self._camera_on)

    def _register_face(self) -> None:
        name = simpledialog.askstring(
            "Register Face", "Enter your name:", parent=self.root
        )
        if name and name.strip():
            self._on_register_face(name.strip())

    def _on_close(self) -> None:
        if messagebox.askyesno("Exit", "Shut down J.A.R.V.I.S.?"):
            self.root.destroy()
            import sys; sys.exit(0)

    # ────── External update methods ──────

    def set_status(self, msg: str) -> None:
        def _upd():
            self._status_var.set(msg.upper()[:24])
            if "think" in msg.lower() or "execut" in msg.lower():
                self._status_badge.configure(fg_color=WARN_COL)
            elif "error" in msg.lower():
                self._status_badge.configure(fg_color=ERR_COL)
            else:
                self._status_badge.configure(fg_color=ACCENT3)
        try:
            self.root.after(0, _upd)
        except Exception:
            pass

    def append_log(self, line: str, color: str = TXT_MAIN) -> None:
        ts = time.strftime("%H:%M:%S")
        full = f"[{ts}] {line}\n"
        self._log_lines.append(full)
        if len(self._log_lines) > 500:
            self._log_lines = self._log_lines[-300:]

        def _upd():
            try:
                self._log_box.configure(state="normal")
                self._log_box.insert("end", full)
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
            except Exception:
                pass
        try:
            self.root.after(0, _upd)
        except Exception:
            pass

    def update_camera_frame(self, bgr_frame) -> None:
        """Called from VisionModule with each OpenCV frame."""
        try:
            rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb).resize((340, 256), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(pil)
            self._cam_canvas._last_img = tk_img  # prevent GC

            def _upd():
                self._cam_canvas.delete("all")
                self._cam_canvas.create_image(0, 0, anchor="nw", image=tk_img)
            self.root.after(0, _upd)
        except Exception:
            pass

    def confirm_dialog(self, message: str) -> bool:
        result = {"v": False}

        def _ask():
            result["v"] = messagebox.askyesno(
                "J.A.R.V.I.S. Confirmation Required",
                message, icon="warning", parent=self.root
            )

        self.root.after(0, _ask)
        # Busy-wait (short timeout)
        deadline = time.time() + 30
        while time.time() < deadline:
            if result["v"] is not False or not self.root.winfo_exists():
                break
            time.sleep(0.05)
        return result["v"]

    # ────── Animations ──────

    def _animate_pulse(self) -> None:
        """Draws a slow radar/pulse ring when camera is off."""
        self._pulse_phase = 0.0

        def _tick():
            if not self._camera_on:
                self._cam_canvas.delete("all")
                cx, cy, r = 170, 128, 80
                # Background circle
                self._cam_canvas.create_oval(
                    cx-r, cy-r, cx+r, cy+r,
                    outline=ACCENT2, width=1,
                )
                # Rotating arc
                start = int(self._pulse_phase) % 360
                self._cam_canvas.create_arc(
                    cx-r, cy-r, cx+r, cy+r,
                    start=start, extent=120,
                    outline=ACCENT1, width=2, style="arc",
                )
                # Inner cross
                self._cam_canvas.create_line(
                    cx-r-20, cy, cx+r+20, cy, fill=TXT_DIM, width=1, dash=(3,4))
                self._cam_canvas.create_line(
                    cx, cy-r-20, cx, cy+r+20, fill=TXT_DIM, width=1, dash=(3,4))
                # Label
                self._cam_canvas.create_text(
                    cx, cy+r+22, text="OPTICAL SENSOR OFFLINE",
                    fill=TXT_DIM, font=("Courier New", 9))
                self._pulse_phase += 3
            try:
                self.root.after(50, _tick)
            except Exception:
                pass

        _tick()

    # ────── System monitor ──────

    def _start_sys_monitor(self) -> None:
        def _update():
            try:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                self._cpu_var.set(f"CPU {cpu:4.1f}%")
                self._ram_var.set(f"RAM {ram:4.1f}%")
            except Exception:
                pass
            try:
                self.root.after(2000, _update)
            except Exception:
                pass
        self.root.after(1000, _update)

    # ────── Run ──────

    def run(self) -> None:
        logger.info("GUI mainloop starting")
        self.root.mainloop()
