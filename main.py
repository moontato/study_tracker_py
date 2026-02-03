#!/usr/bin/env python3
"""Study Tracker GUI Application.

This script implements a simple study-tracking desktop application using
Tkinter. The user can start a stopwatch, pause, resume, and stop it. When
stopped, the session is saved together with any notes the user entered.
All sessions are persisted in a SQLite database so they survive across
restarts of the program and even system reboots.

Running the application
-----------------------
```
python3 main.py
```
To create a standalone executable that can be double‑clicked, run::

    pip install pyinstaller
    pyinstaller --onefile main.py

The resulting ``main`` binary (``main.exe`` on Windows or ``main`` on macOS
and Linux) will appear in the ``dist`` directory.

Author: moontato
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

DB_PATH = Path(__file__).with_name("study_sessions.db")


class SessionDatabase:
    """Simple SQLite wrapper for storing study sessions."""

    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._create_table()

    def _create_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration REAL,
                notes TEXT
            );
            """
        )
        self.conn.commit()

    def add_session(self, start: datetime, end: datetime, duration: float, notes: str) -> None:
        self.conn.execute(
            "INSERT INTO sessions (start_time, end_time, duration, notes) VALUES (?, ?, ?, ?)",
            (start.isoformat(), end.isoformat(), duration, notes),
        )
        self.conn.commit()

    def get_all_sessions(self) -> list[tuple]:
        cursor = self.conn.execute("SELECT id, start_time, duration FROM sessions ORDER BY start_time DESC")
        return cursor.fetchall()

    def get_session(self, session_id: int) -> tuple | None:
        cursor = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return cursor.fetchone()


class StudyTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        # Apply a modern ttk theme and color scheme
        style = ttk.Style(self)
        try:
            style.theme_use("clam")  # light‑mode theme
        except tk.TclError:
            # Fallback if theme not available
            pass
        # Configure widget styles for a cleaner look
        style.configure("TButton", padding=6, relief="flat")
        style.configure("TLabel", background="white")
        style.configure("TFrame", background="white")
        self.configure(background="white")
        self.title("Study Tracker")
        self.resizable(False, False)
        self.geometry("500x500")
        self.minsize(500, 500)
        self.resizable(True, True)

        self.db = SessionDatabase(DB_PATH)

        # State variables
        self._start_time: datetime | None = None
        self._elapsed: float = 0.0
        # New: mode selection: 'stopwatch' or 'timer'
        self._mode: str = "stopwatch"
        # For timer mode: target duration in seconds
        self._target_seconds: float = 0.0
        self._running: bool = False
        self._timer_job: int | None = None

        self._create_widgets()

    # ---------------------------------------------------------------------
    # UI Setup
    # ---------------------------------------------------------------------
    def _create_widgets(self) -> None:
        # Mode selector
        mode_frame = ttk.Frame(self)
        mode_frame.pack(pady=5)
        ttk.Label(mode_frame, text="Mode:").grid(row=0, column=0, padx=5)
        mode_var = tk.StringVar(value=self._mode)
        self._mode_var = mode_var
        ttk.Radiobutton(mode_frame, text="Stopwatch", variable=mode_var, value="stopwatch", command=self._on_mode_change).grid(row=0, column=1, padx=5)
        ttk.Radiobutton(mode_frame, text="Timer", variable=mode_var, value="timer", command=self._on_mode_change).grid(row=0, column=2, padx=5)

        # Timer display
        self.timer_label = ttk.Label(self, text="00:00:00", font=("Helvetica", 32, "bold"))
        self.timer_label.pack(pady=10)

        # Control buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=5, fill='x', expand=True)
        self.start_btn = ttk.Button(btn_frame, text="Start", command=self.start_session)
        self.start_btn.grid(row=0, column=0, padx=5)
        self.pause_btn = ttk.Button(btn_frame, text="Pause", command=self.pause_session, state="disabled")
        self.pause_btn.grid(row=0, column=1, padx=5)
        self.resume_btn = ttk.Button(btn_frame, text="Resume", command=self.resume_session, state="disabled")
        self.resume_btn.grid(row=0, column=2, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop_session, state="disabled")
        self.stop_btn.grid(row=0, column=3, padx=5)
        # Make button columns expand equally for centering
        for i in range(4):
            btn_frame.columnconfigure(i, weight=1)

        # Notes area
        notes_lbl = ttk.Label(self, text="Notes:")
        notes_lbl.pack(anchor="w", padx=10, pady=(10, 0))
        self.notes_text = tk.Text(self, height=8, width=45)
        self.notes_text.pack(padx=10, pady=5)
        self.notes_text.config(font=("Helvetica", 10))

        # View sessions button
        view_btn = ttk.Button(self, text="View Sessions", command=self.open_sessions_window)
        view_btn.pack(pady=5)

    def _on_mode_change(self) -> None:
        """Handle switching between stopwatch and timer modes.

        When the mode changes, reset any running session and update the UI.
        """
        self._mode = self._mode_var.get()
        # Reset session if running
        if self._running or self._elapsed > 0:
            # Stop current session and reset display
            self.stop_session()
        # Update timer label to zero
        self.timer_label.config(text="00:00:00")
        # Reset target seconds when leaving timer mode
        self._target_seconds = 0.0

    # ---------------------------------------------------------------------
    # Timer logic
    # ---------------------------------------------------------------------
    def _update_timer(self) -> None:
        if not self._running:
            return
        now = datetime.now()
        if self._mode == "stopwatch":
            elapsed = (now - self._start_time).total_seconds() + self._elapsed
            self.timer_label.config(text=self._format_seconds(elapsed))
        else:  # timer mode
            elapsed = (now - self._start_time).total_seconds() + self._elapsed
            remaining = max(self._target_seconds - elapsed, 0)
            self.timer_label.config(text=self._format_seconds(remaining))
            if remaining <= 0:
                # Timer finished automatically
                self.stop_session()
                return
        # schedule next update
        self._timer_job = self.after(200, self._update_timer)

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    # ---------------------------------------------------------------------
    # Control callbacks
    # ---------------------------------------------------------------------
    def start_session(self) -> None:
        if self._running:
            return
        # For timer mode, prompt for duration
        if self._mode == "timer":
            # Ask minutes; default 25
            minutes = simpledialog.askinteger(
                "Timer duration", "Enter minutes:", parent=self, minvalue=1, maxvalue=180
            )
            if minutes is None:
                return
            self._target_seconds = minutes * 60
            # Reset elapsed for new session
            self._elapsed = 0.0
        else:
            # Stopwatch mode
            self._target_seconds = 0.0
        self._start_time = datetime.now()
        self._running = True
        self._update_timer()
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        self.resume_btn.config(state="disabled")

    def pause_session(self) -> None:
        if not self._running:
            return
        self.after_cancel(self._timer_job)  # type: ignore[arg-type]
        now = datetime.now()
        self._elapsed += (now - self._start_time).total_seconds()
        self._running = False
        self.pause_btn.config(state="disabled")
        self.resume_btn.config(state="normal")

    def resume_session(self) -> None:
        if self._running:
            return
        self._start_time = datetime.now()
        self._running = True
        self._update_timer()
        self.pause_btn.config(state="normal")
        self.resume_btn.config(state="disabled")

    def stop_session(self) -> None:
        """End the current session and persist it.

        The original implementation failed to record the full duration for
        timer sessions that finished automatically (i.e. the timer reached
        zero without the user clicking Stop).  We now compute the elapsed
        time unconditionally and use ``_target_seconds`` for the duration
        when the timer mode is active and the elapsed time has reached the
        target.
        """
        if not (self._running or self._elapsed > 0):
            messagebox.showinfo("No session", "No active session to stop.")
            return

        # Compute elapsed time regardless of running state
        now = datetime.now()
        elapsed = (now - self._start_time).total_seconds() + self._elapsed
        start_time = self._start_time

        # If the timer finished automatically, record the target duration
        if self._mode == "timer" and elapsed >= self._target_seconds:
            duration = self._target_seconds
        else:
            duration = elapsed

        # Fetch notes and persist session
        notes = self.notes_text.get("1.0", tk.END).strip()
        self.db.add_session(start=start_time, end=now, duration=duration, notes=notes)
        messagebox.showinfo("Session Saved", f"Session of {self._format_seconds(duration)} saved.")

        # Reset state and UI
        self._running = False
        self._elapsed = 0.0
        self._start_time = None
        self._target_seconds = 0.0
        self.timer_label.config(text="00:00:00")
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled")
        self.resume_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")
        self.notes_text.delete("1.0", tk.END)

    # ---------------------------------------------------------------------
    # Session viewer
    # ---------------------------------------------------------------------
    def open_sessions_window(self) -> None:
        win = tk.Toplevel(self)
        win.title("Past Sessions")
        win.geometry("400x300")
        listbox = tk.Listbox(win, width=50, height=10)
        listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scrollbar.set)

        # Populate
        sessions = self.db.get_all_sessions()
        for sess in sessions:
            sid, start_str, dur = sess
            start = datetime.fromisoformat(start_str)
            listbox.insert(tk.END, f"{sid}: {start.strftime('%Y-%m-%d %H:%M')} ({self._format_seconds(dur)})")

        def on_select(event: tk.Event) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            idx = selection[0]
            sess_id = sessions[idx][0]
            session = self.db.get_session(sess_id)
            if session:
                _, start_time, end_time, duration, notes = session
                self._show_session_detail(start_time, end_time, duration, notes)

        listbox.bind("<<ListboxSelect>>", on_select)
        # Apply light background to listbox
        listbox.config(bg="white", selectbackground="#d1e7ff")

    def _show_session_detail(self, start: str, end: str, duration: float, notes: str) -> None:
        win = tk.Toplevel(self)
        win.title("Session Detail")
        win.geometry("400x300")
        txt = tk.Text(win, wrap="word", height=15, width=50)
        txt.pack(padx=10, pady=10)
        txt.config(bg="white", fg="black")
        txt.insert(tk.END, f"Start: {start}\n")
        txt.insert(tk.END, f"End: {end}\n")
        txt.insert(tk.END, f"Duration: {self._format_seconds(duration)}\n\n")
        txt.insert(tk.END, f"Notes:\n{notes}")
        txt.config(state="disabled")


if __name__ == "__main__":
    app = StudyTrackerApp()
    app.mainloop()
