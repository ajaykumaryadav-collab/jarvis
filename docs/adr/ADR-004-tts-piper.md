# ADR-004: Piper-TTS for Text-to-Speech (with pyttsx3 fallback)

## Status
`Accepted`

## Date
2026-09-05

## Context
JARVIS needs a TTS engine that produces natural-sounding speech with low
latency. The voice must be pleasant for extended use (not robotic). The
system must also be resilient — if the primary TTS engine fails to load
(e.g., missing model files), JARVIS should degrade gracefully rather than
crashing.

## Decision
Use **Piper TTS** (`piper-tts==1.4.2`) with the `en_US-ryan-high` voice as
the primary TTS engine. Use **pyttsx3** as an automatic fallback if the Piper
voice model file is missing.

The voice model file is downloaded separately via `scripts/download_piper_voice.py`
and stored in `models/piper/`.

## Consequences

### Positive
- Piper produces high-quality, natural-sounding neural TTS entirely offline.
- The `ryan-high` voice is a high-quality American English male voice.
- pyttsx3 fallback ensures JARVIS always has a voice, even without the model.
- Both backends run entirely locally — no API costs.

### Negative / Trade-offs
- Piper model files are ~60-80 MB and must be downloaded separately.
- pyttsx3 fallback uses the Windows SAPI5 voice, which sounds robotic.
- Piper streams audio via `sounddevice`, which may interact with Voicemeeter.

## Alternatives Considered
- **ElevenLabs**: Highest quality voices but requires an API key and charges
  per character. Not suitable for a privacy-focused local assistant. Could be
  added as an optional provider in the future.
- **EdgeTTS (Microsoft)**: Free, excellent quality, but requires internet.
  Rejected for offline-first requirement. Good future provider candidate.
- **Coqui TTS**: Open-source neural TTS but slower and more complex to set up.
  Rejected in favour of Piper's simplicity.
- **Windows SAPI5 (native)**: Always available but sounds robotic. Retained
  as the fallback via pyttsx3.
