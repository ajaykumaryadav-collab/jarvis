"""
jarvis/providers/factory.py — Provider Factory
===============================================
Reads provider selections from config.py and returns the appropriate
concrete implementation. This is the ONLY place in the codebase where
concrete provider classes are imported.

Usage (in main.py or core/agent.py):
    from jarvis.providers.factory import (
        create_wake_word_provider,
        create_stt_provider,
        create_tts_provider,
        create_llm_provider,
        create_memory_provider,
    )

    tts = create_tts_provider()   # Returns a TTSProvider
    tts.load()
    tts.speak("Hello, Arush!")

Adding a new provider
---------------------
1. Create the implementation file (e.g., jarvis/providers/tts/elevenlabs.py).
2. Add an elif branch to the relevant factory function below.
3. Change the config.py selector string (e.g., TTS_PROVIDER = "elevenlabs").
   Nothing else needs to change.
"""

from __future__ import annotations

import jarvis.config as config
from jarvis.providers.wake_word.base import WakeWordProvider
from jarvis.providers.stt.base import STTProvider
from jarvis.providers.tts.base import TTSProvider
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.base import MemoryProvider


def create_wake_word_provider() -> WakeWordProvider:
    """Instantiate and return the configured wake word provider.

    Controlled by: config.WAKE_WORD_PROVIDER
    """
    name = config.WAKE_WORD_PROVIDER
    if name == "openwakeword":
        from jarvis.providers.wake_word.openwakeword import OpenWakeWordProvider
        return OpenWakeWordProvider()
    raise ValueError(
        f"Unknown wake word provider: '{name}'. "
        f"Add it to jarvis/providers/factory.py and jarvis/providers/wake_word/."
    )


def create_stt_provider() -> STTProvider:
    """Instantiate and return the configured STT provider.

    Controlled by: config.STT_PROVIDER
    """
    name = config.STT_PROVIDER
    if name == "faster_whisper":
        from jarvis.providers.stt.faster_whisper import FasterWhisperSTT
        return FasterWhisperSTT()
    raise ValueError(
        f"Unknown STT provider: '{name}'. "
        f"Add it to jarvis/providers/factory.py and jarvis/providers/stt/."
    )


def create_tts_provider() -> TTSProvider:
    """Instantiate and return the configured TTS provider.

    Controlled by: config.TTS_PROVIDER
    """
    name = config.TTS_PROVIDER
    if name in ("piper", "pyttsx3"):
        # Both are handled by the same PiperTTSProvider class, which auto-falls
        # back to pyttsx3 if the Piper model files are missing.
        from jarvis.providers.tts.piper import PiperTTSProvider
        return PiperTTSProvider()
    raise ValueError(
        f"Unknown TTS provider: '{name}'. "
        f"Add it to jarvis/providers/factory.py and jarvis/providers/tts/."
    )


def create_llm_provider() -> LLMProvider:
    """Instantiate and return the configured LLM provider.

    Controlled by: config.LLM_PROVIDER
    """
    name = config.LLM_PROVIDER
    if name == "gemini":
        from jarvis.providers.llm.gemini import GeminiProvider
        return GeminiProvider()
    raise ValueError(
        f"Unknown LLM provider: '{name}'. "
        f"Add it to jarvis/providers/factory.py and jarvis/providers/llm/."
    )


def create_memory_provider() -> MemoryProvider:
    """Instantiate and return the configured memory/RAG provider.

    Controlled by: config.MEMORY_PROVIDER
    """
    name = config.MEMORY_PROVIDER
    if name == "chromadb":
        from jarvis.providers.memory.chromadb import ChromaDBMemoryProvider
        return ChromaDBMemoryProvider()
    raise ValueError(
        f"Unknown memory provider: '{name}'. "
        f"Add it to jarvis/providers/factory.py and jarvis/providers/memory/."
    )
