"""
main.py — Project JARVIS Entry Point
=====================================
Bootstraps all providers and runs the main voice interaction loop:

    1. Load all providers (TTS, Wake Word, STT, LLM) via factory
    2. Start the WebSocket server for the frontend
    3. Wait for wake word "Hey JARVIS"
    4. Greet the user
    5. Transcribe the user's command
    6. Send command to the LLM provider (which handles tools internally)
    7. Speak the response
    8. Return to step 3

Provider selection is controlled entirely by jarvis/config.py.
No provider classes are imported directly here.

Usage
-----
    python main.py              # Normal voice mode
    python main.py --text       # Text-only mode (type commands)
    python main.py --test       # Smoke test and exit
    python main.py --log-level DEBUG
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# ---------------------------------------------------------------------------
# Windows console encoding fix
# ---------------------------------------------------------------------------
# Windows terminals default to CP1252 which cannot render Unicode characters
# in log messages. Force UTF-8 output so emoji and arrows work correctly.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Logging — must be configured before any local imports
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("jarvis.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")
console = Console()

# ---------------------------------------------------------------------------
# Load .env before importing jarvis modules (they may read os.environ)
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Local imports (after env is loaded)
# ---------------------------------------------------------------------------
import jarvis.config as config
from jarvis.providers.factory import (
    create_wake_word_provider,
    create_stt_provider,
    create_tts_provider,
    create_llm_provider,
)
from jarvis.core.tool_dispatcher import ToolDispatcher
from jarvis.core import websocket_server

# Shutdown events — set by the wake word and TTS providers on Ctrl+C
from jarvis.providers.wake_word import openwakeword as _ww_module
from jarvis.providers.tts import piper as _tts_module


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def print_banner() -> None:
    """Print the JARVIS startup banner to the terminal."""
    console.print(
        Panel.fit(
            f"[bold cyan]⚡ Project JARVIS[/bold cyan]\n"
            f"[dim]Assistant for [bold white]{config.USER_NAME}[/bold white] "
            f"| Wake word: [bold yellow]\"{config.WAKE_WORD_MODEL.replace('_', ' ').title()}\"[/bold yellow][/dim]\n"
            f"[dim]STT: {config.STT_PROVIDER} ({config.WHISPER_MODEL_SIZE}) on {config.WHISPER_DEVICE.upper()} "
            f"| TTS: {config.TTS_PROVIDER} | LLM: {config.LLM_PROVIDER} ({config.GEMINI_MODEL})[/dim]",
            border_style="cyan",
            title="[bold]JARVIS v2.0[/bold]",
        )
    )


# ---------------------------------------------------------------------------
# Component Loading
# ---------------------------------------------------------------------------

def load_components():
    """Instantiate and load all providers via the factory.

    Returns
    -------
    tuple
        (wake_word_provider, stt_provider, tts_provider, llm_provider)

    Raises
    ------
    Exception
        Any failure during loading will propagate and be caught by main().
    """
    with console.status("[cyan]Loading audio providers...[/cyan]"):
        tts = create_tts_provider()
        tts.load()
        console.print(f"  [green]✓[/green] TTS: [bold]{tts.backend}[/bold]")

        stt = create_stt_provider()
        stt.load()
        console.print(
            f"  [green]✓[/green] STT: [bold]{config.STT_PROVIDER}[/bold] "
            f"({config.WHISPER_MODEL_SIZE} on {config.WHISPER_DEVICE.upper()})"
        )

        ww = create_wake_word_provider()
        ww.load()
        console.print(f"  [green]✓[/green] Wake word: [bold]{config.WAKE_WORD_MODEL}[/bold]")

    # Tool dispatcher wires the TTS and STT providers to the safety gate
    dispatcher = ToolDispatcher(tts_provider=tts, stt_provider=stt)

    with console.status("[cyan]Connecting to LLM...[/cyan]"):
        llm = create_llm_provider()
        llm.load(tool_dispatcher=dispatcher)
        console.print(
            f"  [green]✓[/green] LLM: [bold]{config.LLM_PROVIDER}[/bold] "
            f"({config.GEMINI_MODEL})"
        )

    return ww, stt, tts, llm


# ---------------------------------------------------------------------------
# Smoke Test Mode
# ---------------------------------------------------------------------------

def run_smoke_test(ww, stt, tts, llm) -> None:
    """Run a non-interactive component validation and exit."""
    console.rule("[bold yellow]Smoke Test Mode[/bold yellow]")
    errors: list[str] = []

    console.print("[cyan]Testing TTS...[/cyan]")
    try:
        tts.speak(f"Smoke test active. Hello, {config.USER_NAME}.")
        console.print("  [green]✓[/green] TTS OK")
    except Exception as exc:
        errors.append(f"TTS: {exc}")
        console.print(f"  [red]✗[/red] TTS error: {exc}")

    console.print("[cyan]Testing LLM API...[/cyan]")
    try:
        response = asyncio.run(llm.process("Say 'JARVIS online' in exactly those two words."))
        console.print(f"  [green]✓[/green] LLM OK -> '{response}'")
    except Exception as exc:
        errors.append(f"LLM: {exc}")
        console.print(f"  [red]✗[/red] LLM error: {exc}")

    console.print("[cyan]Testing system tools...[/cyan]")
    try:
        from jarvis.tools import system_info
        info = system_info.get_system_info()
        console.print(f"  [green]✓[/green] System info: {info[:80]}")
    except Exception as exc:
        errors.append(f"System info: {exc}")
        console.print(f"  [red]✗[/red] System info error: {exc}")

    console.rule()
    if errors:
        console.print(f"[bold red]Smoke test completed with {len(errors)} error(s):[/bold red]")
        for e in errors:
            console.print(f"  [red]- {e}[/red]")
        sys.exit(1)
    else:
        console.print("[bold green]✓ All smoke tests passed.[/bold green]")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Text Mode
# ---------------------------------------------------------------------------

def run_text_mode(tts, llm) -> None:
    """Interactive text mode — type commands instead of speaking them."""
    console.rule("[bold blue]Text Mode (type 'quit' to exit)[/bold blue]")
    tts.speak(f"Text mode active. Type your commands, {config.USER_NAME}.")

    while True:
        try:
            user_input = input(f"\n[{config.USER_NAME}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.lower() in {"quit", "exit", "bye"}:
            tts.speak(f"Goodbye, {config.USER_NAME}.")
            break
        if not user_input:
            continue

        response = asyncio.run(llm.process(user_input))
        console.print(f"\n[bold cyan][JARVIS][/bold cyan] {response}\n")
        tts.speak(response)


# ---------------------------------------------------------------------------
# Main Voice Loop
# ---------------------------------------------------------------------------

def run_main_loop(ww, stt, tts, llm) -> None:
    """Entry point for the voice loop — delegates to async implementation."""
    asyncio.run(_async_main_loop(ww, stt, tts, llm))


async def _async_main_loop(ww, stt, tts, llm) -> None:
    """Async voice interaction loop.

    All blocking I/O (wake word poll, STT recording) is delegated to threads
    via asyncio.to_thread() so the event loop stays responsive.
    """
    # Start the WebGL frontend WebSocket server in the background
    asyncio.create_task(websocket_server.start_server())

    logger.info("Starting JARVIS main loop...")
    ww.start()
    tts.speak(f"JARVIS online. Listening for your wake word, {config.USER_NAME}.")

    console.print(
        f"\n[bold green]⚡ JARVIS is listening...[/bold green] "
        f"Say [bold yellow]\"{config.WAKE_WORD_MODEL.replace('_', ' ').title()}\"[/bold yellow] to activate.\n"
    )

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    try:
        while True:
            # ── Step 1: Wait for wake word (non-blocking poll) ────────────────
            websocket_server.broadcast("LISTENING")
            wake_detected = await asyncio.to_thread(ww.wait_for_wake_word, 0.5)
            if not wake_detected:
                continue  # Poll timeout — loop and try again

            console.print("[bold yellow]⚡ Wake word detected![/bold yellow]")

            # Pause the wake word listener to release the mic for the STT provider
            ww.pause()

            # ── Step 2: Greet the user ────────────────────────────────────────
            tts.speak(f"Yes, {config.USER_NAME}?")
            time.sleep(0.2)  # Brief gap so mic doesn't capture TTS echo

            # ── Step 3: Transcribe the user's command ─────────────────────────
            logger.info("Listening for command...")
            websocket_server.broadcast("RECORDING")
            try:
                user_text = await asyncio.to_thread(stt.listen_and_transcribe)
                ww.resume()
            except Exception as exc:
                logger.error("Transcription failed: %s", exc)
                tts.speak("Sorry, I had trouble hearing that. Please try again.")
                ww.reset()
                ww.resume()
                continue

            if not user_text.strip():
                tts.speak("I didn't catch that. Please try again.")
                ww.reset()
                ww.resume()
                continue

            console.print(f"[bold white]You:[/bold white] {user_text}")

            # ── Step 4: Process with LLM (25s timeout) ────────────────────────
            try:
                websocket_server.broadcast("THINKING")
                try:
                    response = await asyncio.wait_for(
                        llm.process(user_text), timeout=25.0
                    )
                    consecutive_errors = 0
                except asyncio.TimeoutError:
                    response = (
                        f"Sorry {config.USER_NAME}, the LLM is taking too long. "
                        "Please try again."
                    )
                    logger.warning("LLM timed out after 25s — resetting history.")
                    llm.reset_history()
                    consecutive_errors += 1
            except Exception as exc:
                consecutive_errors += 1
                logger.error("LLM error (%d): %s", consecutive_errors, exc)
                response = "I encountered an error. Please try again."
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    tts.speak("I'm experiencing repeated errors. Restarting the conversation.")
                    llm.reset_history()
                    consecutive_errors = 0

            # ── Step 5: Speak the response ────────────────────────────────────
            console.print(f"[bold cyan]JARVIS:[/bold cyan] {response}")
            websocket_server.broadcast("SPEAKING", text=response)
            tts.speak(response)

            # ── Step 6: Cooldown before re-listening ─────────────────────────
            # Prevents JARVIS's own voice from triggering the wake word
            time.sleep(config.WAKE_WORD_COOLDOWN_SEC)
            ww.reset()
            ww.resume()

    except KeyboardInterrupt:
        console.print("\n[bold red]Shutting down JARVIS... (Ctrl+C received)[/bold red]")
    finally:
        # Signal all blocking calls to exit
        _ww_module.shutdown_event.set()
        _tts_module.shutdown_event.set()

        # Cleanly stop hardware
        try:
            tts.stop()
        except Exception:
            pass
        try:
            ww.stop()
        except Exception:
            pass

        console.print("[dim]JARVIS offline.[/dim]")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and run the appropriate mode."""
    parser = argparse.ArgumentParser(
        description="Project JARVIS — Modular AI Desktop Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run smoke test and exit without starting the voice loop.",
    )
    parser.add_argument(
        "--text", action="store_true",
        help="Text mode: type commands instead of speaking them.",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity.",
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))
    print_banner()

    # Validate API key early so we fail fast with a clear message
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        console.print(
            "[bold red]ERROR:[/bold red] GEMINI_API_KEY is not set.\n"
            "Edit your [bold].env[/bold] file and replace the placeholder with your real key.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )
        sys.exit(1)

    try:
        ww, stt, tts, llm = load_components()
    except Exception as exc:
        console.print(f"[bold red]Failed to initialise JARVIS:[/bold red] {exc}")
        logger.exception("Startup failure")
        sys.exit(1)

    if args.test:
        run_smoke_test(ww, stt, tts, llm)
    elif args.text:
        run_text_mode(tts, llm)
    else:
        run_main_loop(ww, stt, tts, llm)


if __name__ == "__main__":
    main()
