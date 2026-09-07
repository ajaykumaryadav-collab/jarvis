# JARVIS — Next Steps Roadmap
> Prepared: 2026-09-05 | Author: Antigravity

---

## Where We Are Right Now

JARVIS is a fully functional, locally-running AI voice assistant with:
- ✅ Wake word detection (OpenWakeWord)
- ✅ GPU-accelerated speech-to-text (faster-whisper on GTX 1650)
- ✅ Neural text-to-speech (Piper, Ryan voice)
- ✅ LLM brain with tool calling (Gemini Flash + Pro routing)
- ✅ Semantic conversation memory (ChromaDB RAG)
- ✅ OS tools (volume, apps, clipboard, web search, system info)
- ✅ Real-time 3D WebGL frontend (Three.js morphing orb)
- ✅ Modular provider architecture (swappable everything)
- ✅ Architecture Decision Records + Agent coding guidelines

---

## Priority 1 — Fix Before Building New Features

These are things that will bite you soon if not addressed.

### 1.1 — Add a `.gitignore` entry for `data/`
The ChromaDB files in `data/chroma/` are being committed to git right now. This will balloon your repo size fast as JARVIS accumulates conversation history. Add `data/` to `.gitignore` and let it generate locally.

### 1.2 — `run.bat` references old paths
`run.bat` was written before the modular refactor. It likely still references the old `audio/`, `core/` structure for its startup checks. Audit and update it to match the new `jarvis/` package layout.

### 1.3 — No graceful restart on crash
If the Gemini API throws a fatal exception, JARVIS dies. Add a top-level watchdog (`while True: subprocess.run(["python", "main.py"])`) or a Windows Task Scheduler entry to auto-restart.

### 1.4 — User email in `web_search.py`
The Wikipedia API User-Agent header still has the old email. Update it to the GitHub repo URL.

---

## Priority 2 — Core Experience Improvements

### 2.1 — Streaming TTS (Dramatically Reduces Latency)
**Current flow**: LLM generates full response → TTS renders full audio → plays.
**Proposed flow**: LLM streams tokens → sentences are piped to TTS as they arrive → speech starts within ~0.5s of the first sentence.

This would make JARVIS feel dramatically more responsive, especially for longer answers. Implementation requires:
- Switch Gemini to streaming mode (`generate_content_async` with `stream=True`)
- Pipe completed sentences (split on `.`, `?`, `!`) to the TTS provider
- Run TTS synthesis and playback in an asyncio pipeline

**Impact**: Perceived latency drops from 3–5s to ~0.5s. This is the single highest-impact improvement possible right now.

### 2.2 — Audio-Reactive Frontend Volume
Right now the frontend orb transitions between states but doesn't react to actual audio volume. To make it truly reactive:
- In `providers/tts/piper.py`, calculate RMS of the audio being played
- Broadcast `volume` level over WebSocket in real-time (currently always `0.0`)
- In `frontend/orb.js`, use the `volume` field to drive the orb's displacement intensity frame-by-frame

**Impact**: The orb would pulse and breathe perfectly in sync with JARVIS's voice.

### 2.3 — Smarter Conversation Memory
Currently a simple sliding window of the last N turns. Better approaches:
- **Summarisation**: When history exceeds the limit, call the LLM to summarise older turns into a compact "memory summary" chunk instead of discarding them.
- **Topic-aware retrieval**: Retrieve the most recent turns AND the most similar turns, merged and deduplicated.

### 2.4 — Multi-wake-word Support
Currently only "Hey Jarvis" is active. OpenWakeWord supports loading multiple models simultaneously. You could add a custom personal wake word trained on your own voice using the OpenWakeWord training guide.

---

## Priority 3 — New Provider Implementations

The Provider Pattern is in place — these are concrete implementations waiting to be written.

### 3.1 — `providers/tts/edge_tts.py` (Microsoft EdgeTTS)
Microsoft's neural TTS accessed via a free, unofficial API (no key needed). Voices like `en-US-GuyNeural` are significantly higher quality than Piper and sound almost indistinguishable from human speech. Requires internet but has zero cost.

```
pip install edge-tts
```

**Trade-off**: Requires internet. Great as an "online mode" TTS provider.

### 3.2 — `providers/llm/ollama.py` (Local LLM — Offline Mode)
When your GTX 1650 is not under heavy load, `llama3.2:3b` or `phi3.5:mini` via Ollama can run at ~4 GB VRAM. This gives JARVIS a fully offline, private mode.

**Use case**: Toggle with `LLM_PROVIDER = "ollama"` in config when you don't want queries leaving the machine.

### 3.3 — `providers/memory/sqlite.py` (Lightweight Memory)
ChromaDB pulls in ~300 MB of dependencies (gRPC, kubernetes client, etc.) for what is at this scale a simple keyword search problem. A SQLite FTS5 memory provider would have zero extra dependencies, start instantly, and be fast enough.

### 3.4 — `providers/stt/whisper_local.py` (CPU Fallback)
A CPU-only STT fallback for when the GPU is occupied (e.g., while gaming).

---

## Priority 4 — New Tools

New tools follow the established pattern: one file in `jarvis/tools/`, one entry in `tool_dispatcher.py`. No other changes.

### 4.1 — `tools/file_manager.py`
- `read_file(path)` — read a file and give it to the LLM as context
- `write_file(path, content)` — write/overwrite a file (gated)
- `list_directory(path)` — list files in a folder

**Use case**: "Hey JARVIS, read my `index.js` and tell me what this function does."

### 4.2 — `tools/browser_control.py`
Using `playwright`:
- `open_url(url)` — open a URL in the default browser
- `get_page_content(url)` — scrape a URL and give content to the LLM

**Use case**: "Hey JARVIS, open the MDN docs for CSS grid."

### 4.3 — `tools/media_control.py`
Using Windows Media Control API:
- `play_pause_media()`
- `next_track()` / `prev_track()`
- `get_now_playing()` — return artist and track name

**Use case**: "Hey JARVIS, skip this song."

### 4.4 — `tools/reminder.py`
- `set_reminder(message, delay_minutes)` — schedule a spoken reminder using `asyncio` sleep

**Use case**: "Hey JARVIS, remind me in 30 minutes to take a break."

### 4.5 — `tools/code_runner.py` (gated)
- `run_python_snippet(code)` — execute a short Python snippet in a subprocess sandbox and return stdout/stderr to the LLM

**Use case**: "Hey JARVIS, run this Python snippet and tell me the output."

### 4.6 — `tools/weather.py`
Using Open-Meteo (free, no API key required):
- `get_weather(city)` — current conditions + today's forecast

**Use case**: "Hey JARVIS, what's the weather like today?"

---

## Priority 5 — Frontend / UI

### 5.1 — Native Desktop App (Tauri)
Wrapping the frontend in Tauri would make it a proper borderless native Windows app with:
- System tray icon
- Always-on-top mode
- Startup with Windows
- No Chrome window visible

**Effort**: Medium. Requires Rust toolchain installed once, then `npm create tauri-app`.

### 5.2 — Transcript Panel
A slide-in panel showing the last few conversation turns, live-updating as JARVIS speaks.

### 5.3 — Settings UI
A minimal settings panel inside the frontend to toggle wake word sensitivity, volume, active provider display, and a "clear memory" button.

### 5.4 — Microphone Visualiser
When you're speaking (RECORDING state), show a waveform ring around the orb reacting to your microphone's RMS level in real-time.

---

## Priority 6 — Infrastructure & Quality

### 6.1 — Proper Test Suite
`python main.py --test` is a smoke test. Add:
- Unit tests for each provider using `unittest.mock`
- Integration tests for the tool dispatcher
- A test that verifies the factory returns the correct types

### 6.2 — Startup Environment Validation
A `startup_check()` function that validates all `.env` keys are set, model files exist, GPU is accessible, and port 8765 is free — with clear, actionable error messages for each.

### 6.3 — Profile & Reduce Startup Time
JARVIS takes ~10–15s to start. Profile with `python -m cProfile main.py` and see if Whisper and Piper models can be loaded lazily (only when first needed).

---

## Long-Term Vision (6–12 months)

| Feature | Description |
|---|---|
| **Custom wake word** | Train a custom wake word on your own voice using OpenWakeWord's training pipeline |
| **Personality memory** | Let JARVIS remember your preferences, projects, and habits persistently |
| **Multi-modal input** | Add a screenshot tool so JARVIS can "see" your screen |
| **Code assistant mode** | Deep VS Code integration — JARVIS reads your open file and answers questions |
| **Home automation** | Connect to Home Assistant or MQTT for smart home control |
| **Proactive mode** | JARVIS speaks to you unprompted — new GitHub PR, calendar reminder, low battery |

---

## Recommended Order of Attack

| # | Task | Effort | Impact |
|---|---|---|---|
| 1 | 🔴 Fix `data/` in `.gitignore` | 5 min | Prevents repo bloat |
| 2 | 🔴 Fix `run.bat` | 10 min | Makes launcher work again |
| 3 | 🟡 Streaming TTS | 2–4 hrs | Biggest UX improvement possible |
| 4 | 🟡 EdgeTTS provider | 1 hr | Better voice quality |
| 5 | 🟡 Media control tool | 1–2 hrs | High practical daily use |
| 6 | 🟢 Weather tool | 30 min | Trivial win |
| 7 | 🟢 Reminder tool | 1 hr | Practical and fun |
| 8 | 🔵 Tauri wrapper | Half day | Feels like a real product |
| 9 | 🔵 Streaming frontend audio reactivity | Half day | Looks incredible |

---

*JARVIS is in good shape — build something great.*
