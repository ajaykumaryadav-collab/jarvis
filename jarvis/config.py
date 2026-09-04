"""
jarvis/config.py — JARVIS Global Configuration
===============================================
All tuneable constants live here. Edit this file to adapt JARVIS to your
hardware, preferences, and workflow.

Provider Selection
------------------
Change the PROVIDER strings to swap a subsystem. The factory in
`jarvis/providers/factory.py` reads these and returns the correct
implementation. No other code needs to change.

Secrets
-------
Do NOT put API keys here. Use the .env file at the project root.
The .env file is loaded by main.py via python-dotenv before any
imports from this module.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# User Identity
# ---------------------------------------------------------------------------
USER_NAME: str = "Arush"
ASSISTANT_NAME: str = "JARVIS"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent  # d:/Projects/Jarvis
MODELS_DIR: Path = BASE_DIR / "models"
PIPER_MODEL_DIR: Path = MODELS_DIR / "piper"
PIPER_VOICE_MODEL: Path = PIPER_MODEL_DIR / "en_US-ryan-high.onnx"
PIPER_VOICE_CONFIG: Path = PIPER_MODEL_DIR / "en_US-ryan-high.onnx.json"
DATA_DIR: Path = BASE_DIR / "data"

# ---------------------------------------------------------------------------
# Provider Selection — change these strings to swap implementations
# ---------------------------------------------------------------------------
# Supported: "openwakeword"
WAKE_WORD_PROVIDER: str = "openwakeword"

# Supported: "faster_whisper"
STT_PROVIDER: str = "faster_whisper"

# Supported: "piper" (auto-falls back to pyttsx3 if model files missing)
TTS_PROVIDER: str = "piper"

# Supported: "gemini"
LLM_PROVIDER: str = "gemini"

# Supported: "chromadb"
MEMORY_PROVIDER: str = "chromadb"

# ---------------------------------------------------------------------------
# Wake Word (openwakeword)
# ---------------------------------------------------------------------------
# openwakeword ships with a "hey_jarvis" model out of the box.
# Set WAKE_WORD_THRESHOLD higher (0.6–0.9) to reduce false positives.
WAKE_WORD_MODEL: str = "hey_jarvis"
WAKE_WORD_THRESHOLD: float = 0.22      # Lowered so normal speech triggers reliably
WAKE_WORD_COOLDOWN_SEC: float = 1.5    # Pause after TTS finishes before re-listening

# ---------------------------------------------------------------------------
# Audio Capture
# ---------------------------------------------------------------------------
SAMPLE_RATE: int = 16_000              # Hz — required by openwakeword & Whisper
CHUNK_DURATION_MS: int = 80            # ms per audio frame fed to openwakeword
SILENCE_THRESHOLD_SEC: float = 1.0    # Seconds of silence to stop STT recording
MAX_RECORD_SEC: float = 12.0           # Hard cap — no natural command is longer
MIC_GAIN: float = 2.5                  # Software gain to boost quiet laptop mics

# ---------------------------------------------------------------------------
# Audio Device Pinning
# ---------------------------------------------------------------------------
# Run: python -c "import sounddevice as sd; print(sd.query_devices())" to list
# all devices and find the right index for your setup.
AUDIO_OUTPUT_DEVICE = None             # None = Windows system default (recommended)
AUDIO_INPUT_DEVICE: int = 1            # Intel Smart Sound mic array

# ---------------------------------------------------------------------------
# Speech-to-Text — faster-whisper settings
# ---------------------------------------------------------------------------
WHISPER_MODEL_SIZE: str = "small"          # "base" or "small" fit in 4 GB VRAM
WHISPER_DEVICE: str = "cuda"               # "cuda" | "cpu"
WHISPER_COMPUTE_TYPE: str = "int8_float16" # Minimises VRAM (~0.6 GB for small)
WHISPER_LANGUAGE: str = "en"

# ---------------------------------------------------------------------------
# Text-to-Speech — piper settings
# ---------------------------------------------------------------------------
# TTS_BACKEND is legacy; use TTS_PROVIDER above for the modular system.
TTS_BACKEND: str = "piper"             # Used by Speaker.backend property / banner
PYTTSX3_RATE: int = 185                # words-per-minute (pyttsx3 fallback)
PYTTSX3_VOLUME: float = 0.9

# ---------------------------------------------------------------------------
# LLM — Gemini settings
# ---------------------------------------------------------------------------
# The Flash model handles fast conversational responses.
# The Pro model is invoked via the delegate_to_pro tool for hard tasks.
GEMINI_MODEL: str = "gemini-3.6-flash"
PRO_GEMINI_MODEL: str = "gemini-3.1-pro"
GEMINI_MAX_TOKENS: int = 1024
GEMINI_TEMPERATURE: float = 0.7
CONVERSATION_HISTORY_LIMIT: int = 20   # Max conversation turns kept in the session

# ---------------------------------------------------------------------------
# RAG Memory — ChromaDB settings
# ---------------------------------------------------------------------------
CHROMA_DB_PATH: Path = DATA_DIR / "chroma"

# ---------------------------------------------------------------------------
# Safety Gate
# ---------------------------------------------------------------------------
# Tools listed here require a spoken "yes" confirmation before executing.
GATED_TOOLS: set[str] = {
    "set_volume",
    "close_app",
    "write_clipboard",
    "system_shutdown",
    "system_reboot",
    "write_file",
}
SAFETY_GATE_TIMEOUT_SEC: float = 10.0

# ---------------------------------------------------------------------------
# Application Launcher — static fallback map
# ---------------------------------------------------------------------------
# The launcher first tries dynamic resolution via the Windows Start Menu index.
# If that fails, it falls back to these hardcoded paths.
APP_MAP: dict[str, str] = {
    "notepad":      r"C:\Windows\System32\notepad.exe",
    "explorer":     r"C:\Windows\explorer.exe",
    "task manager": r"C:\Windows\System32\taskmgr.exe",
    "calculator":   r"C:\Windows\System32\calc.exe",
    "terminal":     r"C:\Windows\System32\wt.exe",
    "powershell":   r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
}
