"""
jarvis/tools/app_launcher.py — Application Launch and Management
=================================================================
Maps friendly spoken names to executable paths and uses subprocess /
psutil to launch and terminate Windows applications.

Dynamic resolution searches the Windows Start Menu shortcuts (.lnk files)
first, then falls back to the static APP_MAP in config.py.

Note: Requires pywin32 for .lnk file parsing.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

import psutil              # type: ignore
import win32com.client     # type: ignore — requires pywin32

import jarvis.config as config

logger = logging.getLogger(__name__)


def _resolve_lnk_to_exe(lnk_path: str) -> str | None:
    """Resolve a Windows .lnk shortcut to its target executable path.

    Parameters
    ----------
    lnk_path : str
        Absolute path to the .lnk file.

    Returns
    -------
    str | None
        The target executable path, or None if resolution fails.
    """
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        return shortcut.Targetpath
    except Exception as e:
        logger.debug("Failed to resolve shortcut %s: %s", lnk_path, e)
        return None


def _find_app_in_start_menu(name: str) -> str | None:
    """Search Windows Start Menu shortcuts for an app matching *name*.

    Checks both the system-wide and per-user Start Menu directories.

    Parameters
    ----------
    name : str
        Lowercase friendly name to search for.

    Returns
    -------
    str | None
        Resolved .exe path if found, else None.
    """
    start_menu_paths = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]

    for menu_path in start_menu_paths:
        if not menu_path.exists():
            continue
        for lnk in menu_path.rglob("*.lnk"):
            if name in lnk.stem.lower():
                exe_path = _resolve_lnk_to_exe(str(lnk))
                if exe_path and exe_path.lower().endswith(".exe"):
                    return exe_path
    return None


def launch_app(name: str) -> str:
    """Launch an application by its friendly spoken name.

    Resolution order:
      1. Exact match in config.APP_MAP
      2. Fuzzy match in config.APP_MAP
      3. Dynamic search in Windows Start Menu

    Parameters
    ----------
    name : str
        A friendly name like "vs code", "chrome", or "spotify".

    Returns
    -------
    str
        Status message suitable for speaking aloud.
    """
    name_lower = name.strip().lower()

    # 1. Exact match
    exe_path = config.APP_MAP.get(name_lower)

    # 2. Fuzzy match in static map
    if exe_path is None:
        for key, path in config.APP_MAP.items():
            if name_lower in key or key in name_lower:
                exe_path = path
                break

    # 3. Dynamic lookup via Start Menu
    if exe_path is None:
        logger.info("Looking up '%s' in Windows Start Menu...", name)
        exe_path = _find_app_in_start_menu(name_lower)

    if exe_path is None:
        return (
            f"I don't know how to launch '{name}'. "
            "I couldn't find it in the Start Menu or the application map."
        )

    if not Path(exe_path).exists():
        return f"Executable not found at '{exe_path}'."

    try:
        subprocess.Popen([exe_path], shell=False)
        logger.info("Launched: %s (%s)", name, exe_path)
        return f"Launched {name.title()}."
    except Exception as exc:
        logger.error("Failed to launch '%s': %s", name, exc)
        return f"Failed to launch {name}: {exc}"


def close_app(name: str) -> str:
    """Close all running processes whose name matches *name*.

    Parameters
    ----------
    name : str
        Friendly app name or process name fragment (e.g., "chrome", "notepad").

    Returns
    -------
    str
        Status message.
    """
    name_lower = name.strip().lower()

    # Map common friendly names to their Windows process names
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

    target = _process_name_map.get(name_lower, name_lower)
    if not target.endswith(".exe"):
        target += ".exe"

    killed = []
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if proc.info["name"].lower() == target:
                proc.kill()
                killed.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed:
        logger.info("Closed %s (PIDs: %s)", target, killed)
        return f"Closed {name.title()} ({len(killed)} instance(s))."
    return f"No running process found for '{name}'."


def list_running_apps() -> str:
    """Return a summary of named running applications (up to 15).

    Returns
    -------
    str
        Comma-separated list of running .exe names.
    """
    seen: set[str] = set()
    apps: list[str] = []

    for proc in psutil.process_iter(["name", "status"]):
        try:
            pname = proc.info["name"]
            if (pname and pname not in seen
                    and proc.info["status"] == psutil.STATUS_RUNNING):
                seen.add(pname)
                apps.append(pname)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    exe_names = sorted(
        {n for n in apps if n.lower().endswith(".exe")},
        key=str.lower,
    )

    if not exe_names:
        return "No running applications detected."

    display = exe_names[:15]
    result = "Running apps: " + ", ".join(display)
    if len(exe_names) > 15:
        result += f" ... and {len(exe_names) - 15} more."
    return result
