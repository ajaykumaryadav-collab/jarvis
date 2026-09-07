"""
jarvis/providers/stt/base.py — Abstract Speech-to-Text Provider
===============================================================
Defines the interface every STT implementation must satisfy.

To add a new STT provider (e.g., Google Cloud Speech):
  1. Create `jarvis/providers/stt/google_cloud.py`
  2. Subclass `STTProvider` and implement all abstract methods.
  3. Register it in `jarvis/providers/factory.py`.
  4. Set `STT_PROVIDER = "google_cloud"` in `jarvis/config.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class STTProvider(ABC):
    """Abstract interface for speech-to-text transcription.

    Implementations own both the audio recording logic and the inference
    step. This allows providers that stream audio directly to a cloud API
    (e.g., Google Cloud Speech) to work the same as fully local providers
    (e.g., faster-whisper).
    """

    @abstractmethod
    def load(self) -> None:
        """Load and initialise the STT model or API client.

        Must be called once at startup. Raises on failure.
        """
        ...

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a pre-recorded audio array to text.

        Parameters
        ----------
        audio : np.ndarray
            1-D float32 array of raw PCM samples at 16 kHz.

        Returns
        -------
        str
            The transcribed text, or an empty string if nothing was
            detected.
        """
        ...

    @abstractmethod
    def listen_and_transcribe(self) -> str:
        """Record audio from the microphone and transcribe it.

        Handles silence detection internally; returns when the user
        stops speaking or the maximum recording duration is reached.

        Returns
        -------
        str
            The transcribed command text, or empty string on failure.
        """
        ...
