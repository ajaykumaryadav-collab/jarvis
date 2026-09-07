"""
jarvis/providers/wake_word/base.py — Abstract Wake Word Provider
================================================================
Defines the interface every wake word detection implementation must satisfy.

To add a new wake word provider (e.g., Picovoice Porcupine):
  1. Create `jarvis/providers/wake_word/porcupine.py`
  2. Subclass `WakeWordProvider` and implement all abstract methods.
  3. Register it in `jarvis/providers/factory.py`.
  4. Set `WAKE_WORD_PROVIDER = "porcupine"` in `jarvis/config.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class WakeWordProvider(ABC):
    """Abstract interface for wake word detection.

    Implementations must be thread-safe: `start()` opens a background
    audio stream and inference loop; `wait_for_wake_word()` blocks the
    caller until the wake word is detected.
    """

    @abstractmethod
    def load(self) -> None:
        """Load and initialise the wake word model.

        Must be called once at startup before `start()`.
        Raises on failure (bad model path, missing library, etc.).
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """Open the microphone stream and start the detection loop.

        Runs inference in a background thread so the caller is not blocked.
        """
        ...

    @abstractmethod
    def pause(self) -> None:
        """Temporarily pause listening (e.g., while transcribing a command).

        Stops the mic stream to avoid hardware contention with the STT
        provider. Must be resumable via `resume()`.
        """
        ...

    @abstractmethod
    def resume(self) -> None:
        """Resume listening after a pause.

        Clears any stale audio frames from the buffer before resuming.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Shut down the mic stream and background thread cleanly."""
        ...

    @abstractmethod
    def wait_for_wake_word(self, timeout: Optional[float] = None) -> bool:
        """Block until the wake word is detected, the timeout elapses, or
        the global shutdown event is set.

        Parameters
        ----------
        timeout : float, optional
            Maximum seconds to wait. ``None`` means wait indefinitely.

        Returns
        -------
        bool
            ``True`` if the wake word was detected, ``False`` on timeout
            or shutdown.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Clear detection state and flush the audio buffer.

        Call this after each successful detection to prepare for the next
        wake word event.
        """
        ...
