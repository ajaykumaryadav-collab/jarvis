"""
tools/clipboard.py — Windows Clipboard Access
==============================================
Read and write clipboard text content via pyperclip.
write_clipboard is a GATED tool — requires user confirmation via safety gate.
"""

from __future__ import annotations

import logging

import pyperclip  # type: ignore

logger = logging.getLogger(__name__)


def read_clipboard() -> str:
    """Return the current text content of the Windows clipboard."""
    try:
        content = pyperclip.paste()
        if not content:
            return "The clipboard is empty."
        preview = content[:200]
        suffix = "…" if len(content) > 200 else ""
        logger.info("Clipboard read: %d chars", len(content))
        return f"Clipboard contains: {preview}{suffix}"
    except Exception as exc:
        logger.error("read_clipboard error: %s", exc)
        return f"Could not read clipboard: {exc}"


def write_clipboard(text: str) -> str:
    """
    Write *text* to the Windows clipboard.

    This is a safety-gated operation — the tool_dispatcher will call the
    safety gate before invoking this function.

    Parameters
    ----------
    text : str
        The text to copy to the clipboard.
    """
    try:
        pyperclip.copy(text)
        preview = text[:80] + ("…" if len(text) > 80 else "")
        logger.info("Clipboard written: %d chars", len(text))
        return f"Copied to clipboard: '{preview}'"
    except Exception as exc:
        logger.error("write_clipboard error: %s", exc)
        return f"Could not write to clipboard: {exc}"
