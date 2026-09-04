"""
config.py — Project JARVIS Global Configuration
================================================
All tuneable constants live here. Edit this file to adapt JARVIS to your
hardware, preferences, and workflow. Do NOT put secrets here; use .env.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# User Identity
# ---------------------------------------------------------------------------
USER_NAME: str = "Ajay"
ASSISTANT_NAME: str = "JARVIS"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
MODELS_DIR: Path = BASE_DIR / "models"
PIPER_MODEL_DIR: Path = MODELS_DIR / "piper"
PIPER_VOICE_MODEL: Path = PIPER_MODEL_DIR / "en_US-ryan-high.onnx"
PIPER_VOICE_CONFIG: Path = PIPER_MODEL_DIR / "en_US-ryan-high.onnx.json"

# ---------------------------------------------------------------------------
# Wake Word (openwakeword)
# ---------------------------------------------------------------------------
# openwakeword ships with a "hey_jarvis" model out of the box.
# Set WAKE_WORD_THRESHOLD higher (0.6–0.9) to reduce false positives.
WAKE_WORD_MODEL: str = "hey_jarvis"
WAKE_WORD_THRESHOLD: float = 0.22  # Lowered so normal, conversational speech triggers it effortlessly
 
# ---------------------------------------------------------------------------
# Audio Capture
# ---------------------------------------------------------------------------
SAMPLE_RATE: int = 16_000          # Hz — required by both openwakeword & Whisper
CHUNK_DURATION_MS: int = 80        # ms per audio frame fed to openwakeword
SILENCE_THRESHOLD_SEC: float = 1.0  # seconds of silence before STT stops recording
MAX_RECORD_SEC: float = 12.0        # hard cap — no command is longer than this
MIC_GAIN: float = 2.5               # Boosts quiet laptop mic to healthy level without clipping
WAKE_WORD_COOLDOWN_SEC: float = 1.5 # pause after TTS finishes before accepting wake word again

# ---------------------------------------------------------------------------
# Audio Device Pinning  (run: python -c "import sounddevice as sd; print(sd.query_devices())")
# ---------------------------------------------------------------------------
# You have Voicemeeter installed which creates 100+ virtual devices and
# causes sounddevice to pick wrong outputs/inputs by default.
#
# Pinned output choices:
#   19 → Speakers (Realtek) MME          ← laptop speakers, always available
#   12 → Headphones (WH-CH720N) MME      ← Sony headphones (only when connected)
#   53 → Speakers (Realtek) WASAPI       ← laptop speakers, lowest latency
#
# Pinned input choices:
#    1 → Microphone Array (Intel Smart)  ← laptop built-in mic  ✅ working
#    3 → Headset mic (WH-CH720N)         ← Sony headset mic (only when connected)
#
AUDIO_OUTPUT_DEVICE = None  # Use Windows system default output (confirmed working)
                            # Change to 12 for Sony WH-CH720N, 53 for Realtek WASAPI
AUDIO_INPUT_DEVICE:  int = 1    # Intel Smart Sound mic array


# ---------------------------------------------------------------------------
# Speech-to-Text (faster-whisper)
# ---------------------------------------------------------------------------
WHISPER_MODEL_SIZE: str = "small"          # "base" or "small" — both fit in 4 GB VRAM
WHISPER_DEVICE: str = "cuda"              # "cuda" | "cpu"
WHISPER_COMPUTE_TYPE: str = "int8_float16" # Minimizes VRAM; ~0.6 GB for small model
WHISPER_LANGUAGE: str = "en"

# ---------------------------------------------------------------------------
# Text-to-Speech (piper-tts / pyttsx3 fallback)
# ---------------------------------------------------------------------------
# pyttsx3 = uses Windows SAPI5 → works through Voicemeeter, guaranteed audio
# piper   = uses sounddevice OutputStream → confirmed working with device=None
TTS_BACKEND: str = "piper"          # High-quality Ryan voice via piper
PYTTSX3_RATE: int = 185             # words-per-minute (pyttsx3 fallback)
PYTTSX3_VOLUME: float = 0.9

# ---------------------------------------------------------------------------
# Intelligence Engine (Gemini API)
# ---------------------------------------------------------------------------
# Gemini Flash → fast conversational responses
# Switch to "gemini-1.5-pro" for complex multi-step reasoning
GEMINI_MODEL: str = "gemini-3.6-flash"
GEMINI_MAX_TOKENS: int = 1024
GEMINI_TEMPERATURE: float = 0.7
CONVERSATION_HISTORY_LIMIT: int = 20  # max turns kept in memory

# ---------------------------------------------------------------------------
# Safety Gate — tools that require spoken confirmation before execution
# ---------------------------------------------------------------------------
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
# Application Launcher — friendly name → executable
# ---------------------------------------------------------------------------
APP_MAP: dict[str, str] = {
    "vs code":      r"C:\Users\AJAY YADAV\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "vscode":       r"C:\Users\AJAY YADAV\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "chrome":       r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "browser":      r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "spotify":      r"C:\Users\AJAY YADAV\AppData\Roaming\Spotify\Spotify.exe",
    "notepad":      r"C:\Windows\System32\notepad.exe",
    "explorer":     r"C:\Windows\explorer.exe",
    "task manager": r"C:\Windows\System32\taskmgr.exe",
    "calculator":   r"C:\Windows\System32\calc.exe",
    "terminal":     r"C:\Windows\System32\wt.exe",   # Windows Terminal
    "powershell":   r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
}
