# J.A.R.V.I.S. – Desktop AI Assistant

> Just A Rather Very Intelligent System  
> Production-grade desktop AI agent powered by Gemini 2.0 Flash

---

## Architecture Overview

```
Girdi (ses/yazı)
    │
    ▼
SpeechListener / GUI Entry
    │
    ▼
AgentLoop ──────────────── 3-Layer Memory
    │  PLAN                  ├─ Short-term (deque)
    │  ACT                   ├─ Working  (dict)
    │  OBSERVE               └─ Long-term (SQLite)
    │  MEMORY UPDATE
    │
    ├──► AIBrain (Gemini 2.0 Flash)
    │        └─ Structured JSON plan
    │
    ├──► ActionExecutor
    │        ├─ OS Control (subprocess, pyautogui)
    │        ├─ File System
    │        ├─ Browser
    │        └─ System Info
    │
    ├──► VisionModule (OpenCV)
    │        ├─ Face Detection (Haar Cascade)
    │        ├─ Face Recognition (embeddings)
    │        └─ Motion Detection
    │
    └──► SpeechSpeaker (pyttsx3 TTS)
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Windows 10/11 (Linux/macOS partial support)
- Webcam (optional)
- Microphone (optional)
- Gemini API key: https://aistudio.google.com/

### 2. Install

```bash
git clone <repo>
cd jarvis
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY
```

Your `.env` should contain:
```
GEMINI_API_KEY=AIzaSy...your_real_key_here
```

### 4. Run

```bash
python main.py
```

---

## File Structure

```
jarvis/
├── main.py                  # Entry point
├── requirements.txt
├── .env.example             # Template – copy to .env
├── .env                     # YOUR secrets (never commit!)
│
├── config/
│   └── settings.py          # Config loader (reads .env)
│
├── core/
│   ├── logger.py            # Loguru setup
│   ├── ai_brain.py          # Gemini integration + PLAN loop
│   └── agent.py             # PLAN → ACT → OBSERVE → MEMORY loop
│
├── memory/
│   └── memory_manager.py    # 3-layer memory (RAM + SQLite)
│
├── modules/
│   ├── speech.py            # STT + TTS
│   ├── vision.py            # OpenCV camera / face / motion
│   └── action_executor.py   # OS, file, browser, mouse automation
│
├── gui/
│   └── main_window.py       # CustomTkinter holographic UI
│
├── tools/
│   └── autostart.py         # Windows registry autostart
│
├── data/
│   ├── jarvis.db            # SQLite (auto-created)
│   ├── faces/               # Registered face images
│   └── embeddings/          # (reserved)
│
└── logs/                    # Rotating logs (auto-created)
```

---

## Example Commands

| Voice / Text | What JARVIS does |
|---|---|
| "Open Chrome" | Launches Chrome |
| "Take a screenshot" | Saves PNG to data/ |
| "Search for Python tutorials" | Opens Google search |
| "Create a file called notes.txt" | Creates the file |
| "What's my CPU usage?" | Reads psutil and responds |
| "Register my face" | Captures & stores face embedding |
| "Shut down the computer" | Asks for confirmation first |

---

## Security Notes

- API key lives ONLY in `.env` – never in code
- High-risk actions require explicit user confirmation
- Shell commands are filtered against a blocked-list
- `.env` is in `.gitignore` by default

---

## Extending JARVIS

### Add a new tool

1. Implement the method in `modules/action_executor.py`
2. Add the tool name to the dispatch table
3. Add the tool description to the system prompt in `core/ai_brain.py`
4. Gemini will automatically use it when appropriate

### Add a new memory type

Extend `memory/memory_manager.py` with a new SQLAlchemy model and methods.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `GEMINI_API_KEY not configured` | Check `.env` file exists with real key |
| `Cannot open camera index 0` | Change `CAMERA_INDEX` in `.env` or check webcam |
| TTS no sound | Check speakers; try changing voice in settings |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| GUI won't open | Ensure `customtkinter` installed; try headless mode |

---

## Improvement Roadmap

1. **Better face recognition** – Replace Haar+histogram with FaceNet/ArcFace
2. **Wake word** – Add "Hey JARVIS" detection (Porcupine / Picovoice)
3. **Multi-monitor support** – Detect active screen in screenshot
4. **Plugin system** – Hot-loadable tool modules
5. **Voice cloning** – ElevenLabs for more realistic J.A.R.V.I.S. voice
6. **Screen understanding** – GPT-4o / Gemini Vision for GUI automation
7. **Task scheduler** – `schedule` library integration for recurring tasks
