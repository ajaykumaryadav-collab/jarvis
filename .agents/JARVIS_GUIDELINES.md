# JARVIS Coding Guidelines
# Agent-Mandatory Reference Document
# ====================================
# Every developer or AI agent working on this codebase MUST read and follow
# this document before making any changes. These rules exist to maintain the
# modular, swappable architecture that makes JARVIS future-proof.

---

## 1. The Prime Directive: The Provider Pattern

JARVIS uses the **Provider Pattern** for every major external dependency.
This means each capability (STT, TTS, LLM, etc.) has:

1. An **Abstract Base Class** in `jarvis/providers/<domain>/base.py`
2. One or more **Concrete Implementations** in `jarvis/providers/<domain>/<name>.py`
3. A **Factory** in `jarvis/providers/factory.py` that reads `config.py` and
   returns the right implementation.

**You MUST NEVER import a concrete provider class directly from `main.py` or
`jarvis/core/agent.py`.** Always go through the factory.

```python
# ✅ CORRECT
from jarvis.providers.factory import create_stt_provider
stt = create_stt_provider()

# ❌ WRONG — breaks swappability
from jarvis.providers.stt.faster_whisper import FasterWhisperSTT
stt = FasterWhisperSTT()
```

---

## 2. Directory Structure

```
jarvis/
├── providers/          # All swappable providers live here
│   ├── wake_word/      # Wake word detection (openwakeword, picovoice, ...)
│   ├── stt/            # Speech-to-text (faster_whisper, google_cloud, ...)
│   ├── tts/            # Text-to-speech (piper, pyttsx3, elevenlabs, ...)
│   ├── llm/            # Large language model (gemini, openai, ollama, ...)
│   ├── memory/         # RAG / memory backend (chromadb, sqlite, pinecone, ...)
│   └── factory.py      # Reads config.py and instantiates the right provider
│
├── core/               # Orchestration logic (NO provider imports)
│   ├── agent.py        # Main event loop — wires providers + tools
│   ├── safety_gate.py  # Confirmation for destructive actions
│   ├── tool_dispatcher.py
│   └── websocket_server.py
│
├── tools/              # OS-level tool implementations
│   ├── app_launcher.py
│   ├── clipboard.py
│   ├── system_info.py
│   ├── volume.py
│   └── web_search.py
│
└── config.py           # All configuration, including active provider names
```

---

## 3. How to Add a New Provider

Example: adding ElevenLabs as an alternative TTS engine.

### Step 1: Create the implementation file
```python
# jarvis/providers/tts/elevenlabs.py
from jarvis.providers.tts.base import TTSProvider

class ElevenLabsTTS(TTSProvider):
    def load(self) -> None:
        # initialize ElevenLabs client
        ...

    def speak(self, text: str) -> None:
        # call ElevenLabs API
        ...

    def stop(self) -> None:
        ...
```

### Step 2: Register it in the factory
```python
# jarvis/providers/factory.py
def create_tts_provider() -> TTSProvider:
    provider_name = config.TTS_PROVIDER
    if provider_name == "piper":
        from jarvis.providers.tts.piper import PiperTTS
        return PiperTTS()
    elif provider_name == "pyttsx3":
        from jarvis.providers.tts.pyttsx3 import Pyttsx3TTS
        return Pyttsx3TTS()
    elif provider_name == "elevenlabs":          # ← Add this
        from jarvis.providers.tts.elevenlabs import ElevenLabsTTS
        return ElevenLabsTTS()
    raise ValueError(f"Unknown TTS provider: {provider_name}")
```

### Step 3: Switch the active provider
```python
# jarvis/config.py
TTS_PROVIDER = "elevenlabs"   # ← This is the ONLY line that needs to change
```

---

## 4. How to Add a New Tool

### Step 1: Create/modify a tool file in `jarvis/tools/`
```python
# jarvis/tools/my_new_tool.py
def do_something(target: str) -> str:
    """One-line description used as the Gemini tool description.

    Parameters
    ----------
    target : str
        The target to operate on.
    """
    return f"Did something to {target}"
```

### Step 2: Register it in `jarvis/core/tool_dispatcher.py`
```python
from jarvis.tools import my_new_tool

# Inside _build_registry():
"do_something": my_new_tool.do_something,
```

### Step 3: Add to safety gate if destructive
```python
# jarvis/config.py
GATED_TOOLS: set[str] = {
    ...
    "do_something",  # ← Add here if it requires confirmation
}
```

**The Gemini tool schema is auto-generated from the function signature and
docstring. No other changes are needed.**

---

## 5. Abstract Base Class Contract

Every provider base class must define the **minimum required interface**
using Python's `abc.ABC` and `@abstractmethod`. No provider implementation
is allowed to skip any abstract method.

Concrete implementations may add extra methods, but `core/agent.py` must
**only call methods defined on the abstract base class**. This guarantees
that swapping providers does not require changes to the agent.

---

## 6. Configuration Rules

- **All** tuneable constants go in `jarvis/config.py`. No magic numbers in
  provider files.
- **Secrets** (API keys, tokens) go in `.env` ONLY, never in `config.py`.
- **Provider selection** (e.g., `STT_PROVIDER = "faster_whisper"`) goes in
  `config.py`. This is the single source of truth.

---

## 7. ADR Policy

Every significant **architectural decision** (choosing a library, changing the
directory structure, introducing a new pattern) MUST have a corresponding
Architecture Decision Record (ADR) in `docs/adr/`.

Use the template in `docs/adr/ADR-000-template.md`. ADRs are append-only:
once written, a record is never deleted. If a decision is reversed, a NEW
ADR is written that supersedes the old one.

---

## 8. Commenting & Documentation Standards

- Every **module** must have a module-level docstring explaining its purpose,
  its place in the architecture, and usage examples.
- Every **class** must have a class docstring.
- Every **public method** must have a docstring with Parameters and Returns sections.
- **Inline comments** are required for any logic that is not self-evident.
- Avoid commenting the obvious (`# increment counter`). Comment the *why*,
  not the *what*.

---

## 9. No Circular Imports

The import chain is strictly **one-directional**:

```
main.py
  → jarvis.providers.factory
      → jarvis.providers.<domain>.<impl>
  → jarvis.core.agent
      → jarvis.core.tool_dispatcher
          → jarvis.tools.*
      → jarvis.core.safety_gate
      → jarvis.core.websocket_server
  → jarvis.config
```

**`jarvis.config` must never import from any other jarvis module.**
**`jarvis.tools.*` must never import from `jarvis.core.*`.**

---

## 10. Testing

- All new provider implementations should be smoke-testable by running
  `python main.py --test`.
- Use `jarvis/providers/<domain>/base.py` as the contract for writing tests
  against the abstract interface, not the concrete implementation.
