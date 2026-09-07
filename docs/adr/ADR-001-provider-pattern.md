# ADR-001: Provider Pattern for Swappable Subsystems

## Status
`Accepted`

## Date
2026-09-05

## Context
JARVIS depends on several external libraries for its core capabilities:
wake word detection, speech-to-text, text-to-speech, the LLM backend, and
the memory/RAG layer. Initially, each of these was tightly coupled directly
to a single concrete implementation (e.g., `audio/listener.py` directly
importing `openwakeword`). This made it impossible to swap out any component
without editing multiple files across the codebase.

As the project matures, requirements will change:
- The free Gemini API may hit rate limits → need to fall back to Ollama
- Piper may not sound right → want to try ElevenLabs or EdgeTTS
- ChromaDB may be too heavy → want a lighter SQLite-backed memory

## Decision
Adopt the **Provider Pattern** (a variant of the Strategy pattern) for all
major external dependencies. Each capability gets:

1. An `Abstract Base Class` (`base.py`) that defines the required interface.
2. One or more **Concrete Implementations** (e.g., `faster_whisper.py`).
3. A central **Factory** (`factory.py`) that reads `config.py` and returns
   the correct implementation at startup.

Provider selection is controlled by a single string in `config.py`:
```python
STT_PROVIDER = "faster_whisper"  # Change this to swap providers
```

## Consequences

### Positive
- Swapping any provider is a one-line config change, zero code changes.
- Each provider is independently testable against the abstract interface.
- New providers can be added without modifying any existing code.
- The codebase becomes self-documenting: `base.py` is the spec.

### Negative / Trade-offs
- Adds an extra layer of indirection (factory + base class).
- Slightly more boilerplate when adding a new provider.
- Dynamic imports in the factory are slightly harder to trace statically.

## Alternatives Considered
- **Plugin system (entry points)**: More powerful but far too complex for a
  personal project. Rejected in favour of simplicity.
- **Direct concrete imports everywhere**: Simple, but locks in all choices
  forever. Rejected.
- **Dependency injection framework**: Overkill. Rejected.
