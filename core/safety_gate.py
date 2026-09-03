"""
core/safety_gate.py — Confirmation Gate for Destructive Actions
================================================================
Before any tool in GATED_TOOLS executes, JARVIS speaks a confirmation
request to the user and waits for a spoken "yes" or "confirm" response.

The gate is integrated into tool_dispatcher.py and never needs to be
called directly.

Flow
----
safety_gate.check(tool_name, args, speaker, transcriber)
    ├── tool NOT in GATED_TOOLS → returns True immediately
    └── tool IS gated:
          JARVIS speaks: "Ajay, should I [human-readable description]? Say yes to confirm."
          Wait up to SAFETY_GATE_TIMEOUT_SEC for user response.
          ├── User says "yes" / "confirm" / "do it" / "proceed" → returns True
          └── Anything else / timeout / "no" / "cancel" → returns False
"""

from __future__ import annotations

import logging
import time
from typing import Any

import config

logger = logging.getLogger(__name__)

# Human-readable action descriptions for each gated tool
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
_YES_WORDS = {"yes", "yeah", "yep", "yup", "confirm", "do it", "proceed",
              "go ahead", "sure", "okay", "ok", "affirmative"}

# Words that count as negative
_NO_WORDS = {"no", "nope", "cancel", "abort", "stop", "don't", "negative",
             "never mind", "nevermind"}


def _build_confirmation_prompt(tool_name: str, args: dict[str, Any]) -> str:
    """Return a natural-language confirmation question."""
    template = _ACTION_DESCRIPTIONS.get(tool_name, f"run the {tool_name} command")
    try:
        description = template.format(**args)
    except KeyError:
        description = template
    return (
        f"{config.USER_NAME}, should I {description}? "
        f"Say yes to confirm or no to cancel."
    )


def check(
    tool_name: str,
    args: dict[str, Any],
    speaker,
    transcriber,
) -> bool:
    """
    Verify user intent before executing a gated tool.

    Parameters
    ----------
    tool_name : str
        The name of the tool about to be executed.
    args : dict
        The arguments that will be passed to the tool.
    speaker : Speaker
        TTS speaker used to voice the confirmation request.
    transcriber : Transcriber
        STT transcriber used to capture the user's spoken answer.

    Returns
    -------
    bool
        True if execution should proceed, False if aborted.
    """
    if tool_name not in config.GATED_TOOLS:
        return True  # Not gated — allow immediately

    prompt = _build_confirmation_prompt(tool_name, args)
    logger.info("Safety gate triggered for '%s'. Asking user…", tool_name)
    speaker.speak(prompt)

    # Give the user a moment to gather their thoughts after the TTS finishes
    time.sleep(0.3)

    start = time.monotonic()
    while time.monotonic() - start < config.SAFETY_GATE_TIMEOUT_SEC:
        try:
            response_text = transcriber.listen_and_transcribe().lower().strip()
        except Exception as exc:
            logger.error("Safety gate transcription error: %s", exc)
            speaker.speak("I had trouble hearing you. Cancelling for safety.")
            return False

        if not response_text:
            continue

        logger.info("Safety gate response: '%s'", response_text)

        # Check for affirmative
        if any(word in response_text for word in _YES_WORDS):
            logger.info("Safety gate: APPROVED for '%s'", tool_name)
            return True

        # Check for negative
        if any(word in response_text for word in _NO_WORDS):
            speaker.speak("Understood. Action cancelled.")
            logger.info("Safety gate: DENIED for '%s'", tool_name)
            return False

        # Unclear response — ask once more
        speaker.speak(
            f"Sorry, I didn't understand. Please say yes or no. "
            f"Should I {_build_confirmation_prompt(tool_name, args).split('should I')[1]}"
        )

    # Timeout
    speaker.speak("No response received. Action cancelled for safety.")
    logger.warning("Safety gate: TIMEOUT for '%s'", tool_name)
    return False
