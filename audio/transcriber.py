"""
audio/transcriber.py — Speech-to-Text via faster-whisper
==========================================================
Records audio from the default microphone until a silence gap is detected,
then transcribes with faster-whisper running on CUDA.

VRAM usage: ~0.6 GB (small model, int8_float16 compute type).

Speed tuning
------------
- MAX_RECORD_SEC reduced to 12s (was 30s) — no natural command is that long.
- SILENCE_THRESHOLD_SEC = 1.0s — stops faster after you finish speaking.
- Adaptive RMS threshold: calibrates against ambient noise on the first 0.5s
  of each recording, so it works regardless of mic sensitivity.
- Whisper beam_size=1 for faster inference (was 5).

Usage
-----
    transcriber = Transcriber()
    transcriber.load()
    text = transcriber.listen_and_transcribe()
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
import sounddevice as sd

import config

logger = logging.getLogger(__name__)

# How long (seconds) to sample ambient noise at the start of each recording
_AMBIENT_SAMPLE_SEC = 0.4
# Multiplier above ambient RMS that counts as speech
_SPEECH_RMS_MULTIPLIER = 3.5


class Transcriber:
    """CUDA-accelerated speech-to-text using faster-whisper."""

    def __init__(self) -> None:
        self._model = None

    # ------------------------------------------------------------------
    # Model Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load the Whisper model onto the GPU (call once at startup)."""
        logger.info(
            "Loading faster-whisper '%s' model on %s (%s) …",
            config.WHISPER_MODEL_SIZE,
            config.WHISPER_DEVICE,
            config.WHISPER_COMPUTE_TYPE,
        )
        try:
            import sys
            import os
            if sys.platform == "win32":
                try:
                    import torch
                    torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
                    if os.path.exists(torch_lib):
                        os.add_dll_directory(torch_lib)
                except Exception as e:
                    logger.debug("Could not add torch lib to DLL path: %s", e)

            from faster_whisper import WhisperModel  # type: ignore

            self._model = WhisperModel(
                config.WHISPER_MODEL_SIZE,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
            logger.info("Whisper model loaded ✓")
        except Exception as exc:
            logger.error("Failed to load faster-whisper: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Audio Recording
    # ------------------------------------------------------------------

    def _record_until_silence(self) -> np.ndarray:
        """
        Record audio until SILENCE_THRESHOLD_SEC of silence or MAX_RECORD_SEC.

        Uses an adaptive RMS threshold calibrated against the first
        _AMBIENT_SAMPLE_SEC of ambient noise, so it works across
        different microphones and room environments.

        Returns a 1-D float32 numpy array (16 kHz).
        """
        sample_rate = config.SAMPLE_RATE
        chunk_sec   = 0.08                # seconds per analysis chunk (~80ms)
        chunk_size  = int(sample_rate * chunk_sec)

        silence_chunks_needed = max(1, int(config.SILENCE_THRESHOLD_SEC / chunk_sec))
        max_chunks = int(config.MAX_RECORD_SEC / chunk_sec)
        # Minimum chunks before we allow silence detection (avoids cutting on leading silence)
        min_chunks_before_speech = int(0.3 / chunk_sec)

        recorded_chunks: list[np.ndarray] = []
        silence_count   = 0
        speech_detected = False
        rms_threshold   = 0.02  # default fallback

        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_size,
        ) as stream:

            # ── Phase 1: Ambient noise calibration ──────────────────────
            ambient_chunks = max(1, int(_AMBIENT_SAMPLE_SEC / chunk_sec))
            ambient_samples: list[float] = []
            for _ in range(ambient_chunks):
                chunk, _ = stream.read(chunk_size)
                audio = chunk[:, 0]
                recorded_chunks.append(audio.copy())
                ambient_samples.append(float(np.sqrt(np.mean(audio ** 2))))

            ambient_rms   = float(np.mean(ambient_samples)) if ambient_samples else 0.01
            rms_threshold = max(0.005, ambient_rms * _SPEECH_RMS_MULTIPLIER)
            logger.debug(
                "Ambient RMS=%.4f → speech threshold=%.4f", ambient_rms, rms_threshold
            )

            # ── Phase 2: Record until silence ───────────────────────────
            for chunk_idx in range(max_chunks - ambient_chunks):
                chunk, _ = stream.read(chunk_size)
                audio = chunk[:, 0]
                recorded_chunks.append(audio.copy())

                rms = float(np.sqrt(np.mean(audio ** 2)))

                if rms >= rms_threshold:
                    speech_detected = True
                    silence_count   = 0
                else:
                    if speech_detected:
                        silence_count += 1

                # Stop if we have detected speech AND enough trailing silence
                if (speech_detected
                        and silence_count >= silence_chunks_needed
                        and chunk_idx >= min_chunks_before_speech):
                    logger.debug(
                        "Silence detected after %.1fs of recording.",
                        len(recorded_chunks) * chunk_sec,
                    )
                    break

            if not speech_detected:
                logger.debug("No speech detected in recording window.")

        return np.concatenate(recorded_chunks) if recorded_chunks else np.array([], dtype=np.float32)

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def transcribe(self, audio: np.ndarray) -> str:
        """Run faster-whisper on a float32 audio array."""
        if self._model is None:
            raise RuntimeError("Transcriber not loaded. Call load() first.")

        segments, _info = self._model.transcribe(
            audio,
            language=config.WHISPER_LANGUAGE,
            beam_size=1,             # beam_size=1 is 2-3× faster; quality fine for voice commands
            best_of=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )

        text_parts = [segment.text.strip() for segment in segments]
        result = " ".join(text_parts).strip()
        logger.info("Transcription: '%s'", result)
        return result

    def listen_and_transcribe(self) -> str:
        """Record then transcribe. Returns empty string if nothing detected."""
        audio = self._record_until_silence()
        if len(audio) < config.SAMPLE_RATE * 0.3:  # ignore clips shorter than 0.3s
            logger.debug("Audio too short to transcribe.")
            return ""
        return self.transcribe(audio)
