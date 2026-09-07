"""
jarvis/providers/tts/piper.py — Piper TTS Provider
====================================================
Concrete TTSProvider using piper-tts with a pyttsx3 automatic fallback.

Why a combined file instead of two separate files?
---------------------------------------------------
The fallback from Piper → pyttsx3 happens at runtime if the Piper model
file is missing. Both implementations share the same `backend` property
and `speak()` signature, so it's cleaner to handle the fallback logic here
rather than duplicating it in the factory.

Why a persistent pyttsx3 worker thread?
----------------------------------------
pyttsx3.runAndWait() owns a COM event loop. Calling it from multiple threads
(or re-entering it) raises "run loop already started". A single daemon thread
that owns the engine for its lifetime avoids this entirely.

See Also
--------
ADR-004: Why Piper was chosen over ElevenLabs / EdgeTTS.
"""

from __future__ import annotations

import io
import logging
import os
import queue
import struct
import tempfile
import threading
import time
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

from jarvis.providers.tts.base import TTSProvider
import jarvis.config as config

logger = logging.getLogger(__name__)

# Global flag: set by the main entry point on shutdown to abort speech mid-sentence
shutdown_event = threading.Event()

_LOCK_ACQUIRE_TIMEOUT   = 2.0   # seconds to try acquiring the speak lock
_PYTTSX3_SPEAK_TIMEOUT  = 25.0  # max seconds to wait for one pyttsx3 utterance

# Only one utterance plays at a time
_speak_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal pyttsx3 worker thread
# ---------------------------------------------------------------------------

class _Pyttsx3Worker(threading.Thread):
    """Single daemon thread that owns the pyttsx3 COM engine for its lifetime.

    All speak() calls are posted to an internal queue and processed serially,
    so runAndWait() is only ever called from one thread.
    """

    _POISON = object()  # sentinel that stops the worker loop

    def __init__(self) -> None:
        super().__init__(daemon=True, name="Pyttsx3Worker")
        self._q: queue.Queue = queue.Queue()
        self._engine = None
        self._ready  = threading.Event()
        self._error: Optional[Exception] = None

    def run(self) -> None:
        """Initialise the COM engine, then process speak requests from the queue."""
        try:
            import pyttsx3  # type: ignore
            engine = pyttsx3.init("sapi5")
            engine.setProperty("rate",   config.PYTTSX3_RATE)
            engine.setProperty("volume", config.PYTTSX3_VOLUME)
            # Prefer an English voice if multiple SAPI voices are installed
            voices = engine.getProperty("voices")
            for v in voices:
                if "english" in v.name.lower() or "en_us" in v.id.lower():
                    engine.setProperty("voice", v.id)
                    break
            self._engine = engine
        except Exception as exc:
            self._error = exc
            self._ready.set()
            return

        self._ready.set()
        logger.info("pyttsx3 worker thread ready ✓")

        while True:
            item = self._q.get()
            if item is self._POISON:
                break
            text, done_event = item
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as exc:
                logger.error("pyttsx3 engine error: %s", exc)
            finally:
                done_event.set()

    def speak_sync(self, text: str, timeout: float = _PYTTSX3_SPEAK_TIMEOUT) -> bool:
        """Post *text* to the worker and block until it finishes or times out.

        Returns
        -------
        bool
            True on success, False on timeout or shutdown.
        """
        if not self._ready.wait(timeout=5.0):
            logger.warning("pyttsx3 worker not ready.")
            return False
        if self._error:
            logger.error("pyttsx3 worker failed to initialise: %s", self._error)
            return False

        done = threading.Event()
        self._q.put((text, done))

        elapsed, interval = 0.0, 0.1
        while elapsed < timeout:
            if shutdown_event.is_set():
                return False
            if done.wait(timeout=interval):
                return True
            elapsed += interval

        logger.warning("pyttsx3 speak timed out after %.0fs", timeout)
        return False

    def stop(self) -> None:
        """Signal the worker thread to exit."""
        self._q.put(self._POISON)


# ---------------------------------------------------------------------------
# Piper TTS Provider
# ---------------------------------------------------------------------------

class PiperTTSProvider(TTSProvider):
    """High-quality neural TTS via Piper, falling back to pyttsx3 if needed."""

    def __init__(self) -> None:
        self._backend_name: str = "none"
        self._piper_voice = None
        self._piper_sample_rate: int = 22050
        self._pyttsx3_worker: Optional[_Pyttsx3Worker] = None

    # ------------------------------------------------------------------
    # TTSProvider interface
    # ------------------------------------------------------------------

    @property
    def backend(self) -> str:
        """The active TTS backend name ('piper' or 'pyttsx3')."""
        return self._backend_name

    def load(self) -> None:
        """Load Piper voice model; fall back to pyttsx3 if model files are missing."""
        self._log_output_device()

        if self._try_load_piper():
            self._backend_name = "piper"
            logger.info("TTS backend: piper-tts (%s) ✓", config.PIPER_VOICE_MODEL.name)
        else:
            logger.warning(
                "Piper model not found at %s — using pyttsx3.",
                config.PIPER_VOICE_MODEL,
            )
            self._start_pyttsx3_worker()
            self._backend_name = "pyttsx3"

        # Short test tone to confirm audio routing is working at startup
        self._play_test_tone()

    def speak(self, text: str) -> None:
        """Synthesise and play *text*, blocking until playback is complete."""
        if not text.strip() or shutdown_event.is_set():
            return

        acquired = _speak_lock.acquire(timeout=_LOCK_ACQUIRE_TIMEOUT)
        if not acquired:
            return
        try:
            if shutdown_event.is_set():
                return
            logger.info("Speaking: '%s'", text[:80] + ("..." if len(text) > 80 else ""))

            if self._backend_name == "piper":
                self._speak_piper(text)
            elif self._backend_name == "pyttsx3":
                self._speak_pyttsx3(text)
            else:
                logger.error("No TTS backend loaded — call load() first.")
        finally:
            _speak_lock.release()

    def stop(self) -> None:
        """Immediately stop all audio output and clean up resources."""
        shutdown_event.set()
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        sd.stop()
        if self._pyttsx3_worker:
            self._pyttsx3_worker.stop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_output_device(self) -> None:
        """Log the active sounddevice output device at startup."""
        try:
            default_out = sd.query_devices(kind="output")
            name = default_out.get("name", "unknown") if default_out else "unknown"
            out_idx = sd.default.device[1]
            logger.info("Audio OUTPUT device: '%s' (index %s)", name, out_idx)
            logger.info(
                "   Run: python -c \"import sounddevice as sd; print(sd.query_devices())\" to see all devices"
            )
        except Exception as exc:
            logger.warning("Could not query output device: %s", exc)

    def _play_test_tone(self) -> None:
        """Play a 440 Hz beep at startup to confirm audio output is working."""
        try:
            sample_rate = 22050
            duration    = 0.25
            t           = np.linspace(0, duration, int(sample_rate * duration), False)
            tone        = (np.sin(2 * np.pi * 440 * t) * 0.4).astype(np.float32)

            device = getattr(config, "AUDIO_OUTPUT_DEVICE", None)
            with sd.OutputStream(
                samplerate=sample_rate, channels=1, dtype="float32", device=device,
            ) as stream:
                stream.write(tone)
                stream.stop()
            logger.info("Test tone played — if you heard a beep, audio output is working.")
        except Exception as exc:
            logger.error("Test tone failed: %s — audio output may be broken.", exc)

    def _try_load_piper(self) -> bool:
        """Attempt to load the Piper voice model. Returns False on failure."""
        if not config.PIPER_VOICE_MODEL.exists():
            return False
        if not config.PIPER_VOICE_CONFIG.exists():
            logger.warning("Piper config JSON not found: %s", config.PIPER_VOICE_CONFIG)
            return False
        try:
            from piper import PiperVoice  # type: ignore
            voice = PiperVoice.load(
                str(config.PIPER_VOICE_MODEL),
                config_path=str(config.PIPER_VOICE_CONFIG),
                use_cuda=False,
            )
            self._piper_voice = voice
            self._piper_sample_rate = voice.config.sample_rate
            return True
        except Exception as exc:
            logger.error("Error loading piper voice: %s", exc)
            return False

    def _start_pyttsx3_worker(self) -> None:
        """Start the persistent pyttsx3 background thread."""
        logger.info("Starting pyttsx3 worker thread...")
        self._pyttsx3_worker = _Pyttsx3Worker()
        self._pyttsx3_worker.start()
        if self._pyttsx3_worker._ready.wait(timeout=10.0):
            if self._pyttsx3_worker._error:
                raise RuntimeError(
                    f"pyttsx3 failed to start: {self._pyttsx3_worker._error}"
                )
            logger.info("pyttsx3 worker ready ✓")
        else:
            logger.warning("pyttsx3 worker did not become ready in 10s.")

    def _speak_piper(self, text: str) -> None:
        """Synthesise with Piper and play via winsound (default) or sounddevice (pinned)."""
        try:
            chunks = list(self._piper_voice.synthesize(text))
            if not chunks:
                logger.warning("Piper returned empty audio.")
                return
            if shutdown_event.is_set():
                return

            device = getattr(config, "AUDIO_OUTPUT_DEVICE", None)

            if device is not None:
                # Pinned device: stream through sounddevice
                audio_float = np.concatenate([c.audio_float_array for c in chunks])
                chunk_frames = 2048
                with sd.OutputStream(
                    samplerate=self._piper_sample_rate,
                    channels=1, dtype="float32", device=device,
                ) as out_stream:
                    offset = 0
                    while offset < len(audio_float) and not shutdown_event.is_set():
                        chunk = audio_float[offset: offset + chunk_frames]
                        out_stream.write(chunk)
                        offset += len(chunk)
            else:
                # Default device: package into a WAV file and play via winsound
                # winsound follows whatever Windows considers the default output
                raw_bytes = b"".join([c.audio_int16_bytes for c in chunks])
                fd, tmp_path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                try:
                    with wave.open(tmp_path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self._piper_sample_rate)
                        wf.writeframes(raw_bytes)
                    if not shutdown_event.is_set():
                        import winsound
                        winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass

        except Exception as exc:
            logger.error("Piper TTS error: %s — switching to pyttsx3", exc)
            self._backend_name = "pyttsx3"
            if self._pyttsx3_worker is None:
                self._start_pyttsx3_worker()
            self._speak_pyttsx3(text)

    def _speak_pyttsx3(self, text: str) -> None:
        """Post text to the persistent pyttsx3 worker thread."""
        if self._pyttsx3_worker is None:
            self._start_pyttsx3_worker()
        self._pyttsx3_worker.speak_sync(text)
