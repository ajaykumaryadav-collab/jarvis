"""
audio/listener.py — Wake Word Detection
========================================
Continuously streams microphone audio through openwakeword.
When "Hey JARVIS" is detected with sufficient confidence, this module
signals the main loop to begin active listening / transcription.

Architecture
------------
- sounddevice InputStream feeds raw 16kHz PCM into a thread-safe queue.
- A background thread drains the queue and runs openwakeword inference.
- Caller uses `wait_for_wake_word()` which blocks until detection or timeout.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd

import config

# Set by main.py on Ctrl+C so wait_for_wake_word() exits its poll loop
shutdown_event = threading.Event()

logger = logging.getLogger(__name__)


class WakeWordListener:
    """Listens on the default microphone and detects the JARVIS wake word."""

    def __init__(self) -> None:
        self._model = None
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=50)
        self._detected_event = threading.Event()
        self._stream: Optional[sd.InputStream] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._paused = False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load the openwakeword model (call once at startup)."""
        logger.info("Loading openwakeword model: %s", config.WAKE_WORD_MODEL)
        try:
            from openwakeword.model import Model  # type: ignore

            self._model = Model(
                wakeword_models=[config.WAKE_WORD_MODEL],
                inference_framework="onnx",
            )
            logger.info("Wake word model loaded ✓")
        except Exception as exc:
            logger.error("Failed to load openwakeword: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Internal audio callback
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice calls this on every audio chunk (runs in audio thread)."""
        if self._paused or shutdown_event.is_set():
            return

        if status:
            logger.debug("Audio stream status: %s", status)

        # Apply software gain then clamp to prevent int16 overflow
        gained = np.clip(indata[:, 0] * config.MIC_GAIN, -1.0, 1.0)
        audio_int16 = (gained * 32767).astype(np.int16)
        try:
            self._audio_queue.put_nowait(audio_int16)
        except queue.Full:
            pass  # Drop oldest frame rather than block the audio thread

    # ------------------------------------------------------------------
    # Inference worker
    # ------------------------------------------------------------------

    def _drain_queue(self) -> None:
        """Discard all pending frames from the audio queue."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _inference_worker(self) -> None:
        """Background thread: drain the audio queue and run openwakeword."""
        logger.debug("Wake word inference worker started.")
        frame_count = 0
        last_status_time = time.monotonic()

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if self._model is None or self._paused:
                continue

            frame_count += 1
            prediction = self._model.predict(chunk)

            # ── Heartbeat: log RMS + best score every 5s ────────────────────
            now = time.monotonic()
            if now - last_status_time >= 5.0:
                best = max(prediction.values()) if prediction else 0.0
                rms  = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                logger.info(
                    "Listening… score=%.3f (thresh=%.2f) | mic_rms=%.1f | frames=%d",
                    best, config.WAKE_WORD_THRESHOLD, rms, frame_count,
                )
                if rms < 1.0:
                    logger.warning(
                        "mic_rms is near-zero (%.1f) — mic may be muted or wrong device.",
                        rms,
                    )
                last_status_time = now

            for model_name, score in prediction.items():
                if score >= config.WAKE_WORD_THRESHOLD and not self._paused:
                    logger.info(
                        "Wake word '%s' detected! Score: %.3f (thresh: %.2f)",
                        model_name, score, config.WAKE_WORD_THRESHOLD,
                    )
                    self._model.reset()
                    self._detected_event.set()
                    break

        logger.debug("Wake word inference worker stopped.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the microphone stream and start the inference worker thread."""
        if self._model is None:
            self.load()

        self._running = True
        self._paused = False
        chunk_size = int(config.SAMPLE_RATE * config.CHUNK_DURATION_MS / 1000)

        try:
            device_info = sd.query_devices(kind="input")
            logger.info(
                "Mic input device: '%s' (index %s)",
                device_info.get("name", "unknown"),
                sd.default.device[0],
            )
        except Exception as e:
            logger.warning("Could not query input device: %s", e)

        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=chunk_size,
            device=getattr(config, "AUDIO_INPUT_DEVICE", None),
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info(
            "Microphone stream opened at %d Hz, chunk=%d samples",
            config.SAMPLE_RATE,
            chunk_size,
        )

        self._worker_thread = threading.Thread(
            target=self._inference_worker, daemon=True, name="WakeWordWorker"
        )
        self._worker_thread.start()

    def pause(self) -> None:
        """
        Temporarily pause listening and stop mic stream.
        Gives transcriber exclusive access to the mic without audio hardware contention.
        """
        self._paused = True
        self._detected_event.clear()
        if self._stream and self._stream.active:
            try:
                self._stream.stop()
            except Exception as exc:
                logger.debug("Error pausing mic stream: %s", exc)
        self._drain_queue()

    def resume(self) -> None:
        """Resume listening for wake word with a fresh buffer."""
        self._drain_queue()
        self._detected_event.clear()
        if self._model:
            self._model.reset()
        if self._stream and not self._stream.active and self._running:
            try:
                self._stream.start()
            except Exception as exc:
                logger.warning("Error restarting mic stream: %s", exc)
        self._paused = False

    def stop(self) -> None:
        """Shut down mic stream and inference worker cleanly."""
        self._running = False
        self._paused = True
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
        logger.info("Wake word listener stopped.")

    def wait_for_wake_word(self, timeout: Optional[float] = None) -> bool:
        """
        Poll until "Hey JARVIS" is detected, *timeout* elapses, or shutdown.
        """
        self._detected_event.clear()
        poll_interval = 0.5  # seconds between checks
        elapsed = 0.0

        while not shutdown_event.is_set():
            triggered = self._detected_event.wait(timeout=poll_interval)
            if triggered and not self._paused:
                return True
            if timeout is not None:
                elapsed += poll_interval
                if elapsed >= timeout:
                    return False

        return False  # shutdown signalled

    def reset(self) -> None:
        """Clear detection state and drain audio buffer."""
        self._detected_event.clear()
        self._drain_queue()
        if self._model:
            self._model.reset()

