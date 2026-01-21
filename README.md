# Study Tracker

An easy‑to‑use desktop app that lets a student track how long they study.

## Features
* Stopwatch with **Start**, **Pause/Resume**, and **Stop**.
* Free‑form notes per session.
* Persist all sessions in a SQLite database – data survives reboots.
* View a list of past sessions and see the details (time, duration, notes).

## Running the app

```bash
python3 main.py
```

The program uses only the Python standard library, so no external
dependencies are required.

## Creating a double‑clickable executable

1. Install PyInstaller if you don't already have it:
   ```bash
   pip install pyinstaller
   ```
2. Build the executable:
   ```bash
   pyinstaller --onefile main.py
   ```
3. The resulting binary will be in the `dist` folder (`main` on Linux/macOS or `main.exe` on Windows).
   Simply double‑click it to run the app.

## Project structure
```
├── main.py        # Main application
├── study_sessions.db  # SQLite database (created on first run)
└── README.md
```
