"""
tools/system_info.py — System Resource Statistics
==================================================
Reports CPU usage, RAM stats, and GPU VRAM / temperature via psutil
and pynvml (NVIDIA Management Library).

VRAM tracking serves a dual purpose: user awareness + JARVIS can warn
Ajay if VRAM is running low before loading a large model.
"""

from __future__ import annotations

import logging

import psutil  # type: ignore

logger = logging.getLogger(__name__)


def get_system_info() -> str:
    """
    Collect CPU, RAM, and GPU stats and return a formatted summary string.
    """
    parts: list[str] = []

    # -- CPU ----------------------------------------------------------
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_freq = psutil.cpu_freq()
        freq_str = f" at {cpu_freq.current:.0f} MHz" if cpu_freq else ""
        parts.append(f"CPU: {cpu_pct:.1f}%{freq_str}")
    except Exception as exc:
        parts.append(f"CPU: unavailable ({exc})")

    # -- RAM ----------------------------------------------------------
    try:
        ram = psutil.virtual_memory()
        used_gb = ram.used / (1024 ** 3)
        total_gb = ram.total / (1024 ** 3)
        parts.append(f"RAM: {used_gb:.1f} GB / {total_gb:.1f} GB ({ram.percent:.1f}%)")
    except Exception as exc:
        parts.append(f"RAM: unavailable ({exc})")

    # -- GPU ----------------------------------------------------------
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode()

        vram_used = mem_info.used / (1024 ** 3)
        vram_total = mem_info.total / (1024 ** 3)
        parts.append(
            f"GPU ({gpu_name}): VRAM {vram_used:.2f} GB / {vram_total:.2f} GB, "
            f"Temp {temp}°C"
        )
        pynvml.nvmlShutdown()
    except ImportError:
        parts.append("GPU: pynvml not installed.")
    except Exception as exc:
        parts.append(f"GPU: unavailable ({exc})")

    return " | ".join(parts)
