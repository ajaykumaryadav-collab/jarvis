"""
audio/speaker.py — Text-to-Speech Output
==========================================
Primary backend: piper-tts using synthesize_stream_raw() → winsound.
Fallback backend: pyttsx3 via a persistent background thread.

Why synthesize_stream_raw instead of synthesize(wav_file)
----------------------------------------------------------
piper's synthesize() calls wave.Wave_write internally and on some Windows
installs raises "# channels not specified" before writing any audio.
synthesize_stream_raw() skips the wave layer entirely and yields raw 16-bit
mono PCM bytes, which we wrap in a proper WAV header ourselves.

Why a persistent pyttsx3 thread
--------------------------------
pyttsx3.runAndWait() owns a COM event loop. Calling it from multiple threads
(or re-entering it) raises "run loop already started". A single daemon thread
that owns the engine for its lifetime avoids this completely.
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

import config

logger = logging.getLogger(__name__)

# ─── Global shutdown flag ────────────────────────────────────────────────────
shutdown_event = threading.Event()

_LOCK_ACQUIRE_TIMEOUT   = 2.0   # seconds to try acquiring the speak lock
_PYTTSX3_SPEAK_TIMEOUT  = 25.0  # max seconds to wait for one pyttsx3 utterance


# ─────────────────────────────────────────────────────────────────────────────
# Persistent pyttsx3 worker thread
# ─────────────────────────────────────────────────────────────────────────────

class _Pyttsx3Worker(threading.Thread):
    """
    Single daemon thread that owns the pyttsx3 engine for its lifetime.

    All speak() requests are posted to an internal queue and processed
    serially by this thread — runAndWait() is only ever called from one
    thread, so "run loop already started" is impossible.
    """

    _POISON = object()  # sentinel that stops the thread

    def __init__(self) -> None:
        super().__init__(daemon=True, name="Pyttsx3Worker")
        self._q: queue.Queue = queue.Queue()
        self._engine = None
        self._ready  = threading.Event()
        self._error: Optional[Exception] = None

    def run(self) -> None:
        try:
            import pyttsx3  # type: ignore
            engine = pyttsx3.init("sapi5")
            engine.setProperty("rate",   config.PYTTSX3_RATE)
            engine.setProperty("volume", config.PYTTSX3_VOLUME)
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
        """
        Post *text* to the worker and block until it finishes or timeout.
        Returns True on success, False on timeout / shutdown.
        """
        if not self._ready.wait(timeout=5.0):
            logger.warning("pyttsx3 worker not ready.")
            return False
        if self._error:
            logger.error("pyttsx3 worker failed to initialise: %s", self._error)
            return False

        done = threading.Event()
        self._q.put((text, done))

        elapsed = 0.0
        interval = 0.1
        while elapsed < timeout:
            if shutdown_event.is_set():
                return False
            if done.wait(timeout=interval):
                return True
            elapsed += interval

        logger.warning("pyttsx3 speak timed out after %.0fs for: '%s'", timeout, text[:60])
        return False

    def stop(self) -> None:
        self._q.put(self._POISON)


# ─────────────────────────────────────────────────────────────────────────────
# Speaker
# ─────────────────────────────────────────────────────────────────────────────

_speak_lock = threading.Lock()


class Speaker:
    """Handles TTS synthesis and audio playback for JARVIS."""

    def __init__(self) -> None:
        self._backend: str = "none"
        self._piper_voice = None
        self._piper_sample_rate: int = 22050
        self._pyttsx3_worker: Optional[_Pyttsx3Worker] = None

    # ── Initialisation ────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load and pre-warm the best available TTS backend."""
        # ── Log output device so we can catch wrong-device issues ────────
        self._log_output_device()

        if config.TTS_BACKEND == "piper" and self._try_load_piper():
            self._backend = "piper"
            logger.info("TTS backend: piper-tts (%s) ✓", config.PIPER_VOICE_MODEL.name)
        else:
            logger.warning(
                "Piper model not found at %s — using pyttsx3.",
                config.PIPER_VOICE_MODEL,
            )
            self._start_pyttsx3_worker()
            self._backend = "pyttsx3"

        # ── Play a short test tone so we know audio output is working ─────
        self._play_test_tone()

    def _log_output_device(self) -> None:
        """Log the sounddevice default output device at startup."""
        try:
            out_idx = sd.default.device[1]
            if out_idx is None or out_idx < 0:
                out_idx = sd.default.device
            devices = sd.query_devices()
            if isinstance(devices, dict):
                name = devices.get("name", "unknown")
            else:
                # List of devices — find the default output
                default_out = sd.query_devices(kind="output")
                name = default_out.get("name", "unknown") if default_out else "unknown"
            logger.info("🔊 Audio OUTPUT device: '%s' (index %s)", name, out_idx)
            logger.info(
                "   To see ALL devices run: python -c \"import sounddevice as sd; print(sd.query_devices())\""
            )
        except Exception as exc:
            logger.warning("Could not query output device: %s", exc)

    def _play_test_tone(self) -> None:
        """
        Play a short 440 Hz beep to confirm audio output is alive.
        If you hear this beep at startup, TTS audio routing is working.
        If silent, run: python -c "import sounddevice as sd; print(sd.query_devices())"
        and set AUDIO_OUTPUT_DEVICE in config.py to the correct index.
        """
        try:
            sample_rate = 22050
            duration    = 0.25   # seconds — short enough not to be annoying
            t           = np.linspace(0, duration, int(sample_rate * duration), False)
            tone        = (np.sin(2 * np.pi * 440 * t) * 0.4).astype(np.float32)

            device = getattr(config, "AUDIO_OUTPUT_DEVICE", None)
            with sd.OutputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=device,
            ) as stream:
                stream.write(tone)
                stream.stop()
            logger.info("🔊 Test tone played — if you heard a beep, audio output is working.")
        except Exception as exc:
            logger.error("Test tone failed: %s — audio output may be broken.", exc)


    def _try_load_piper(self) -> bool:
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
        logger.info("Starting pyttsx3 worker thread…")
        self._pyttsx3_worker = _Pyttsx3Worker()
        self._pyttsx3_worker.start()
        # Wait for it to be ready (max 10s)
        if self._pyttsx3_worker._ready.wait(timeout=10.0):
            if self._pyttsx3_worker._error:
                raise RuntimeError(
                    f"pyttsx3 failed to start: {self._pyttsx3_worker._error}"
                )
            logger.info("pyttsx3 worker ready ✓")
        else:
            logger.warning("pyttsx3 worker did not become ready in 10s.")

    # ── Public API ────────────────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        """Synthesise *text* and play it. Skips silently if shutting down."""
        if not text.strip() or shutdown_event.is_set():
            return

        acquired = _speak_lock.acquire(timeout=_LOCK_ACQUIRE_TIMEOUT)
        if not acquired:
            return
        try:
            if shutdown_event.is_set():
                return
            logger.info("Speaking: '%s'", text[:80] + ("…" if len(text) > 80 else ""))

            if self._backend == "piper":
                self._speak_piper(text)
            elif self._backend == "pyttsx3":
                self._speak_pyttsx3(text)
            else:
                logger.error("No TTS backend loaded — call load() first.")
        finally:
            _speak_lock.release()

    def stop(self) -> None:
        """Abort all audio output immediately. Call from shutdown handler."""
        shutdown_event.set()
        sd.stop()
        if self._pyttsx3_worker:
            self._pyttsx3_worker.stop()

    # ── Piper backend ─────────────────────────────────────────────────────────

    def _speak_piper(self, text: str) -> None:
        """
        Synthesise with piper then stream via sd.OutputStream chunked write.

        Why OutputStream instead of sd.play():
          sd.play() with an active InputStream silently drops audio on some
          Windows PortAudio/WASAPI drivers. OutputStream.write() blocks per
          chunk guaranteeing every sample is delivered, is interruptible via
          shutdown_event, and never calls sd.stop() so the mic stays alive.
        """
        try:
            # ── 1. Synthesise raw 16-bit mono PCM ───────────────────────
            raw_audio = b"".join(
                self._piper_voice.synthesize_stream_raw(text)
            )
            if not raw_audio:
                logger.warning("Piper returned empty audio.")
                return

            if shutdown_event.is_set():
                return

            # ── 2. Convert int16 → float32 [-1, 1] ──────────────────────
            audio_int16 = np.frombuffer(raw_audio, dtype=np.int16)
            audio_float = audio_int16.astype(np.float32) / 32768.0

            # ── 3. Stream via OutputStream in small chunks ───────────────
            chunk_frames = 2048  # ~93 ms per chunk at 22050 Hz
            device = getattr(config, "AUDIO_OUTPUT_DEVICE", None)
            with sd.OutputStream(
                samplerate=self._piper_sample_rate,
                channels=1,
                dtype="float32",
                device=device,
            ) as out_stream:

                offset = 0
                total = len(audio_float)
                while offset < total:
                    if shutdown_event.is_set():
                        break
                    chunk = audio_float[offset : offset + chunk_frames]
                    out_stream.write(chunk)  # blocks until buffer has room
                    offset += len(chunk)
                # Drain the PortAudio buffer so the last word isn't cut off
                if not shutdown_event.is_set():
                    out_stream.stop()


        except AttributeError:
            # Older piper-tts without synthesize_stream_raw → wave fallback
            logger.debug("synthesize_stream_raw not found — using wave fallback.")
            self._speak_piper_wave_fallback(text)

        except Exception as exc:
            logger.error("Piper TTS error: %s — switching to pyttsx3", exc)
            self._backend = "pyttsx3"
            if self._pyttsx3_worker is None:
                self._start_pyttsx3_worker()
            self._speak_pyttsx3(text)


    def _speak_piper_wave_fallback(self, text: str) -> None:
        """
        Wave-file fallback for piper versions without synthesize_stream_raw.
        Pre-configures all wave headers before calling synthesize() so the
        'channels not specified' error cannot occur.
        """
        try:
            import winsound
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                with wave.open(tmp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self._piper_sample_rate)
                    self._piper_voice.synthesize(text, wf)
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as exc:
            logger.error("Piper wave fallback error: %s — switching to pyttsx3", exc)
            self._backend = "pyttsx3"
            if self._pyttsx3_worker is None:
                self._start_pyttsx3_worker()
            self._speak_pyttsx3(text)

    # ── pyttsx3 backend ───────────────────────────────────────────────────────

    def _speak_pyttsx3(self, text: str) -> None:
        """Post text to the persistent pyttsx3 worker thread."""
        if self._pyttsx3_worker is None:
            self._start_pyttsx3_worker()
        self._pyttsx3_worker.speak_sync(text)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def backend(self) -> str:
        return self._backend
