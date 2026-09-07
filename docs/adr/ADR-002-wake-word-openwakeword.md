# ADR-002: OpenWakeWord for Wake Word Detection

## Status
`Accepted`

## Date
2026-09-05

## Context
JARVIS requires an always-on, low-latency wake word detector that can run
entirely on CPU without blocking the GPU for other tasks. The detector must
recognize "Hey Jarvis" reliably with a laptop microphone in a home environment.

## Decision
Use **OpenWakeWord** (`openwakeword==0.6.0`) as the default wake word provider.
The `hey_jarvis` model is shipped with the library's model pack and requires
no custom training.

## Consequences

### Positive
- Ships with a pre-trained `hey_jarvis` model — zero training needed.
- Runs on CPU via ONNX runtime, leaving the GPU free for Whisper.
- Open-source (Apache 2.0), no API costs or usage limits.
- Supports custom models if the default is replaced in the future.

### Negative / Trade-offs
- False positive rate is slightly higher than commercial alternatives.
- The pre-trained model is English-only.
- No cloud-based accuracy improvements over time.

## Alternatives Considered
- **Picovoice Porcupine**: Very accurate but requires a free API key and has
  restrictive commercial licensing. Rejected for privacy reasons.
- **Snowboy**: Deprecated and unmaintained since 2020. Rejected.
- **Rolling keyword detection with Whisper**: Too slow (~1s latency for each
  check window) and too GPU-intensive to run continuously. Rejected.
