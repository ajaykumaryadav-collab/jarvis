"""
scripts/download_piper_voice.py — Piper Voice Model Downloader
===============================================================
Downloads the en_US-ryan-high voice model and config from HuggingFace
into models/piper/.

Usage
-----
    python scripts/download_piper_voice.py

Requires: pip install requests (or use urllib — no extra deps)
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Target voice: en_US-ryan-high
# ---------------------------------------------------------------------------
BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    "/en/en_US/ryan/high"
)

FILES = [
    "en_US-ryan-high.onnx",
    "en_US-ryan-high.onnx.json",
]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "models" / "piper"


def download_file(url: str, dest: Path) -> None:
    """Download *url* to *dest* with a simple progress indicator."""
    print(f"Downloading {dest.name} …", end=" ", flush=True)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(url) as response:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 64  # 64 KB chunks

        with open(dest, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  {dest.name}: {pct}%    ", end="", flush=True)

    print(f"\r  [OK] {dest.name} ({downloaded / 1024:.0f} KB)")


def main() -> None:
    print(f"Output directory: {OUTPUT_DIR}\n")

    for filename in FILES:
        dest = OUTPUT_DIR / filename
        if dest.exists():
            print(f"  [OK] {filename} already exists — skipping.")
            continue
        url = f"{BASE_URL}/{filename}"
        try:
            download_file(url, dest)
        except Exception as exc:
            print(f"\n  [FAIL] Failed to download {filename}: {exc}")
            sys.exit(1)

    print(
        "\nVoice model ready. Run JARVIS with:\n"
        "    python main.py\n"
    )


if __name__ == "__main__":
    main()
