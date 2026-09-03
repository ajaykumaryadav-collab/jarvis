"""
tools/app_launcher.py — Application Launch and Management
==========================================================
Maps friendly spoken names to executable paths and uses subprocess /
psutil to launch and terminate Windows applications.

APP_MAP is defined in config.py so the user can customise it without
touching this module.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import psutil  # type: ignore

import config

logger = logging.getLogger(__name__)


def launch_app(name: str) -> str:
    """
    Launch an application by its friendly name.

    Parameters
    ----------
    name : str
        A friendly name like "vs code", "chrome", "spotify".

    Returns
    -------
    str
        Status message.
    """
    name_lower = name.strip().lower()

    exe_path = config.APP_MAP.get(name_lower)

    # Fuzzy match: check if any key contains the search term
    if exe_path is None:
        for key, path in config.APP_MAP.items():
            if name_lower in key or key in name_lower:
                exe_path = path
                break

    if exe_path is None:
        return (
            f"I don't know how to launch '{name}'. "
            f"You can add it to APP_MAP in config.py."
        )

    if not Path(exe_path).exists():
        return f"Executable not found at '{exe_path}'. Please check the path in config.py."

    try:
        subprocess.Popen([exe_path], shell=False)
        logger.info("Launched: %s (%s)", name, exe_path)
        return f"Launched {name.title()}."
    except Exception as exc:
        logger.error("Failed to launch '%s': %s", name, exc)
        return f"Failed to launch {name}: {exc}"


def close_app(name: str) -> str:
    """
    Close all running processes whose name contains *name*.

    Parameters
    ----------
    name : str
        Friendly app name or process name fragment.

    Returns
    -------
    str
        Status message.
    """
    name_lower = name.strip().lower()

    # Map friendly names to known process names
    _process_name_map = {
        "chrome":       "chrome.exe",
        "vs code":      "code.exe",
        "vscode":       "code.exe",
        "spotify":      "spotify.exe",
        "notepad":      "notepad.exe",
        "explorer":     "explorer.exe",
        "task manager": "taskmgr.exe",
        "calculator":   "calc.exe",
        "terminal":     "wt.exe",
        "powershell":   "powershell.exe",
    }

    target_process = _process_name_map.get(name_lower, name_lower)
    if not target_process.endswith(".exe"):
        target_process += ".exe"

    killed = []
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if proc.info["name"].lower() == target_process:
                proc.kill()
                killed.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed:
        logger.info("Closed %s (PIDs: %s)", target_process, killed)
        return f"Closed {name.title()} ({len(killed)} instance(s))."
    else:
        return f"No running process found for '{name}'."


def list_running_apps() -> str:
    """Return a summary of visible/named running applications."""
    seen: set[str] = set()
    apps: list[str] = []

    for proc in psutil.process_iter(["name", "status"]):
        try:
            pname = proc.info["name"]
            if pname and pname not in seen and proc.info["status"] == psutil.STATUS_RUNNING:
                seen.add(pname)
                apps.append(pname)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Filter to just .exe files for readability
    exe_names = sorted(
        {n for n in apps if n.lower().endswith(".exe")},
        key=str.lower,
    )

    if not exe_names:
        return "No running applications detected."

    # Return a manageable subset
    display = exe_names[:15]
    result = "Running apps: " + ", ".join(display)
    if len(exe_names) > 15:
        result += f" … and {len(exe_names) - 15} more."
    return result
