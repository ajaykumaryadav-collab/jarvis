"""
jarvis/core/safety_gate.py — Confirmation Gate for Destructive Actions
=======================================================================
Before any tool listed in config.GATED_TOOLS executes, JARVIS speaks a
natural-language confirmation request to the user and waits for a spoken
"yes" or "no" response.

Flow
----
    safety_gate.check(tool_name, args, tts_provider, stt_provider)
        |
        ├── tool NOT in GATED_TOOLS  →  returns True immediately
        └── tool IS gated:
              JARVIS speaks: "{USER_NAME}, should I {action}? Say yes to confirm."
              Waits up to SAFETY_GATE_TIMEOUT_SEC for user's spoken response.
              ├── "yes" / "confirm" / "proceed" / ...  →  True
              └── "no" / "cancel" / timeout            →  False

This module is called exclusively by tool_dispatcher.py.
It must never import from providers directly — it receives them as arguments.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import jarvis.config as config

logger = logging.getLogger(__name__)

# Map gated tool names to human-readable action descriptions.
# Use {kwarg_name} placeholders to interpolate tool arguments.
_ACTION_DESCRIPTIONS: dict[str, str] = {
    "set_volume":       "set the volume to {level} percent",
    "mute_volume":      "mute the audio",
    "close_app":        "close {name}",
    "write_clipboard":  "write text to your clipboard",
    "system_shutdown":  "SHUT DOWN your computer",
    "system_reboot":    "REBOOT your computer",
    "write_file":       "write to the file system",
}

# Words that count as affirmative
_YES_WORDS = {
    "yes", "yeah", "yep", "yup", "confirm", "do it",
    "proceed", "go ahead", "sure", "okay", "ok", "affirmative",
}

# Words that count as negative
_NO_WORDS = {
    "no", "nope", "cancel", "abort", "stop", "don't",
    "negative", "never mind", "nevermind",
}


def _build_confirmation_prompt(tool_name: str, args: dict[str, Any]) -> str:
    """Return a natural-language confirmation question for the given tool call.

    Parameters
    ----------
    tool_name : str
        The name of the gated tool.
    args : dict
        The arguments that will be passed to the tool.

    Returns
    -------
    str
        A spoken-friendly confirmation prompt.
    """
    template = _ACTION_DESCRIPTIONS.get(tool_name, f"run the {tool_name} command")
    try:
        description = template.format(**args)
    except KeyError:
        description = template
    return (
        f"{config.USER_NAME}, should I {description}? "
        "Say yes to confirm or no to cancel."
    )


def check(
    tool_name: str,
    args: dict[str, Any],
    tts_provider,   # TTSProvider — passed by tool_dispatcher to avoid circular import
    stt_provider,   # STTProvider
) -> bool:
    """Verify user intent before executing a potentially dangerous tool.

    Parameters
    ----------
    tool_name : str
        The name of the tool about to be executed.
    args : dict
        The arguments that will be passed to the tool.
    tts_provider : TTSProvider
        Used to speak the confirmation request aloud.
    stt_provider : STTProvider
        Used to capture the user's spoken response.

    Returns
    -------
    bool
        True if the user confirmed (execution should proceed).
        False if denied, ambiguous, or timed out.
    """
    if tool_name not in config.GATED_TOOLS:
        return True  # Not gated — allow immediately

    prompt = _build_confirmation_prompt(tool_name, args)
    logger.info("Safety gate triggered for '%s'. Asking user for confirmation.", tool_name)
    tts_provider.speak(prompt)

    # Brief pause so TTS audio clears the mic before we start listening
    time.sleep(0.3)

    start = time.monotonic()
    while time.monotonic() - start < config.SAFETY_GATE_TIMEOUT_SEC:
        try:
            response = stt_provider.listen_and_transcribe().lower().strip()
        except Exception as exc:
            logger.error("Safety gate transcription error: %s", exc)
            tts_provider.speak("I had trouble hearing you. Cancelling for safety.")
            return False

        if not response:
            continue  # Empty transcription — keep waiting

        logger.info("Safety gate response: '%s'", response)

        if any(word in response for word in _YES_WORDS):
            logger.info("Safety gate: APPROVED for '%s'.", tool_name)
            return True

        if any(word in response for word in _NO_WORDS):
            tts_provider.speak("Understood. Action cancelled.")
            logger.info("Safety gate: DENIED for '%s'.", tool_name)
            return False

        # Ambiguous response — ask once more
        tts_provider.speak(
            "Sorry, I didn't understand. Please say yes or no. "
            + _build_confirmation_prompt(tool_name, args)
        )

    # Timeout — cancel for safety
    tts_provider.speak("No response received. Action cancelled for safety.")
    logger.warning("Safety gate: TIMEOUT for '%s'.", tool_name)
    return False
