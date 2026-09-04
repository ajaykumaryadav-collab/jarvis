# ADR-003: faster-whisper for Speech-to-Text

## Status
`Accepted`

## Date
2026-09-05

## Context
JARVIS needs speech-to-text that is fast, accurate, and runs locally with no
API costs. The transcription must complete within ~1-2 seconds on a GTX 1650
(4 GB VRAM) to maintain a natural conversation pace.

## Decision
Use **faster-whisper** (`faster-whisper==1.1.0`) with the `small` model,
running on CUDA with `int8_float16` quantization.

- Model: `small` (~244M params, ~500 MB on disk)
- Device: `cuda` (GTX 1650, 4 GB VRAM)
- Compute type: `int8_float16` (~0.6 GB VRAM usage)
- VAD filter: enabled (skips silence, speeds up inference)

## Consequences

### Positive
- Runs locally — no API costs, no data leaves the machine.
- ~3-5× faster than original OpenAI Whisper on the same hardware via CTranslate2.
- `int8_float16` quantization keeps VRAM usage to ~0.6 GB (out of 4 GB).
- The built-in VAD filter automatically removes silence from recordings.
- Supports offline operation.

### Negative / Trade-offs
- Requires CUDA toolkit DLLs (`cublas64_12.dll`) to be accessible at runtime.
  Mitigated by adding torch's `lib/` folder to the DLL search path at startup.
- First run downloads ~500 MB model weights from Hugging Face.
- Accuracy slightly lower than `medium` or `large` models.

## Alternatives Considered
- **Google Cloud Speech-to-Text**: High accuracy but costs money and requires
  internet. Rejected for privacy and cost reasons.
- **SpeechRecognition (CMU Sphinx)**: Offline but very low accuracy on
  conversational speech. Rejected.
- **Whisper.cpp**: CPU-only by default; slower on GTX 1650. Rejected.
- **OpenAI Whisper (original)**: Slower than faster-whisper on same hardware.
  Rejected.
