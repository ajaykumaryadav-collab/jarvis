# ⚡ Project JARVIS

A fully local, hands-free hybrid AI desktop assistant for Windows 11.
Built for Ajay — web programmer and college student.

---

## Architecture

```
Microphone → openwakeword → faster-whisper (CUDA) → Gemini API → piper-tts → Speaker
                                                           ↕
                                                     Tool Dispatcher
                                               (Volume / Apps / Clipboard / Search)
```

| Component | Technology | VRAM |
|---|---|---|
| Wake Word | openwakeword (ONNX, CPU) | — |
| Speech-to-Text | faster-whisper small, int8_float16 | ~0.6 GB |
| Intelligence | Gemini 2.0 Flash API | — |
| Text-to-Speech | piper-tts en_US-ryan-high | — |
| TTS Fallback | pyttsx3 (SAPI5) | — |
| **Total VRAM** | | **~0.95 GB / 4 GB** |

---

## Quick Setup

### 1. Create a virtual environment

```powershell
cd E:\projects\jarvis
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install PyTorch with CUDA 12.1

```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Install all other dependencies

```powershell
pip install -r requirements.txt
```

### 4. Set your Gemini API key

Edit `.env` and replace the placeholder:
```
GEMINI_API_KEY=your_real_key_here
```

Get a free key at: https://aistudio.google.com/app/apikey

### 5. Download the piper voice model (~75 MB)

```powershell
python scripts/download_piper_voice.py
```

### 6. Run JARVIS

```powershell
python main.py
```

---

## Run Modes

| Command | Description |
|---|---|
| `python main.py` | Normal voice mode |
| `python main.py --test` | Smoke test (validates all components) |
| `python main.py --text` | Text mode (type instead of speak) |
| `python main.py --log-level DEBUG` | Verbose logging |

---

## Voice Commands (Examples)

| You say | What happens |
|---|---|
| "Hey JARVIS" | Assistant activates → *"Yes, Ajay?"* |
| "What's my CPU usage?" | Spoken system stats |
| "Set volume to 60" | Safety confirmation → volume changes |
| "Open VS Code" | VS Code launches |
| "Close Spotify" | Safety confirmation → Spotify killed |
| "Search for Python async tutorial" | Top 3 DuckDuckGo results spoken aloud |
| "What's in my clipboard?" | Clipboard contents read aloud |
| "What's my GPU VRAM usage?" | NVIDIA stats via pynvml |

---

## Safety Gate

The following commands require you to say **"yes"** to confirm:

- `set_volume` — changing system volume
- `close_app` — killing an application
- `write_clipboard` — overwriting clipboard
- `system_shutdown` / `system_reboot` *(future)*
- `write_file` *(future)*

---

## Project Structure

```
jarvis/
├── main.py                 # Entry point — event loop
├── config.py               # All tuneable constants
├── .env                    # API keys (never commit this)
├── requirements.txt
├── audio/
│   ├── listener.py         # openwakeword wake word detection
│   ├── transcriber.py      # faster-whisper STT
│   └── speaker.py          # piper-tts + pyttsx3 TTS
├── core/
│   ├── agent.py            # Gemini API + tool-calling
│   ├── safety_gate.py      # Confirmation for destructive actions
│   └── tool_dispatcher.py  # Routes tool calls → functions
├── tools/
│   ├── volume.py           # Windows volume (pycaw)
│   ├── app_launcher.py     # Launch/close apps
│   ├── system_info.py      # CPU/RAM/GPU stats
│   ├── clipboard.py        # Clipboard R/W
│   ├── web_search.py       # DuckDuckGo search
│   └── github_tool.py      # Phase 2 stub
├── models/piper/           # Downloaded piper voice files
└── scripts/
    └── download_piper_voice.py
```

---

## Customisation

All settings are in [`config.py`](config.py):

- **Add apps to launch**: Edit `APP_MAP` dict
- **Change wake word sensitivity**: Adjust `WAKE_WORD_THRESHOLD` (0.0–1.0)
- **Switch Gemini model**: Change `GEMINI_MODEL` to `"gemini-1.5-pro"`
- **Use CPU instead of GPU**: Set `WHISPER_DEVICE = "cpu"`

---

## Phase 2 Roadmap

- [ ] GitHub repository analysis (set `GITHUB_PAT` in `.env`)
- [ ] System shutdown / reboot commands
- [ ] File read/write tools
- [ ] Browser control (open tabs, search)
- [ ] Timer and reminder system
- [ ] Custom wake word model training
