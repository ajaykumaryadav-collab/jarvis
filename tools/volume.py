"""
tools/volume.py — Windows System Volume Control
================================================
Uses pycaw (Python Core Audio for Windows) to read and write the
master audio volume via the Windows Audio Session API (WASAPI).

All functions return a human-readable string suitable for JARVIS's
spoken or text response.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_master_volume_interface():
    """Return the pycaw AudioUtilities master volume interface."""
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL  # type: ignore
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume() -> str:
    """Return the current master volume as a percentage string."""
    try:
        volume_iface = _get_master_volume_interface()
        scalar = volume_iface.GetMasterVolumeLevelScalar()
        level = int(scalar * 100)
        muted = volume_iface.GetMute()
        mute_str = " (muted)" if muted else ""
        return f"Volume is at {level}%{mute_str}."
    except Exception as exc:
        logger.error("get_volume error: %s", exc)
        return f"Could not read volume: {exc}"


def set_volume(level: int) -> str:
    """
    Set the master volume to *level* (0–100).

    Parameters
    ----------
    level : int
        Target volume (0 = silent, 100 = max).
    """
    level = max(0, min(100, int(level)))
    try:
        volume_iface = _get_master_volume_interface()
        scalar = level / 100.0
        volume_iface.SetMasterVolumeLevelScalar(scalar, None)
        # Unmute automatically when setting volume > 0
        if level > 0:
            volume_iface.SetMute(0, None)
        logger.info("Volume set to %d%%", level)
        return f"Volume set to {level}%."
    except Exception as exc:
        logger.error("set_volume error: %s", exc)
        return f"Could not set volume: {exc}"


def mute() -> str:
    """Mute the master audio output."""
    try:
        volume_iface = _get_master_volume_interface()
        volume_iface.SetMute(1, None)
        logger.info("Audio muted.")
        return "Audio muted."
    except Exception as exc:
        logger.error("mute error: %s", exc)
        return f"Could not mute audio: {exc}"


def unmute() -> str:
    """Unmute the master audio output."""
    try:
        volume_iface = _get_master_volume_interface()
        volume_iface.SetMute(0, None)
        logger.info("Audio unmuted.")
        return "Audio unmuted."
    except Exception as exc:
        logger.error("unmute error: %s", exc)
        return f"Could not unmute audio: {exc}"
