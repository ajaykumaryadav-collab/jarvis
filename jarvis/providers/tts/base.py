"""
jarvis/providers/tts/base.py — Abstract Text-to-Speech Provider
===============================================================
Defines the interface every TTS implementation must satisfy.

To add a new TTS provider (e.g., ElevenLabs, EdgeTTS):
  1. Create `jarvis/providers/tts/elevenlabs.py`
  2. Subclass `TTSProvider` and implement all abstract methods.
  3. Register it in `jarvis/providers/factory.py`.
  4. Set `TTS_PROVIDER = "elevenlabs"` in `jarvis/config.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class TTSProvider(ABC):
    """Abstract interface for text-to-speech synthesis.

    Implementations convert a text string to audible speech. They are
    responsible for managing their own audio output device or stream.
    """

    @abstractmethod
    def load(self) -> None:
        """Initialise the TTS engine (load voice model, connect to API, etc.).

        Must be called once at startup. Raises on failure.
        The implementation should log its backend name and output device.
        """
        ...

    @abstractmethod
    def speak(self, text: str) -> None:
        """Synthesise and play `text` as speech, blocking until done.

        Parameters
        ----------
        text : str
            The text to speak. May contain punctuation but should not
            contain markdown, HTML, or other markup.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Immediately stop any ongoing speech and clean up resources.

        Must be safe to call from any thread and must not raise.
        """
        ...

    @property
    @abstractmethod
    def backend(self) -> str:
        """A human-readable name for this TTS backend (e.g., 'piper').

        Used for logging and the startup banner.
        """
        ...
