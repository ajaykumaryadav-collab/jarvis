"""
main.py — Project JARVIS Entry Point
=====================================
Bootstraps all components and runs the main event loop:

    1.  Load all ML models (Whisper, openwakeword, piper-tts)
    2.  Wait for wake word "Hey JARVIS"
    3.  Greet the user
    4.  Transcribe the user's command
    5.  Send command to Gemini agent
    6.  Execute any tool calls (with safety gate)
    7.  Speak the response
    8.  Return to step 2

Usage
-----
    # Normal operation
    python main.py

    # Dry-run smoke test (no live mic, validates all components load)
    python main.py --test

    # Text-only mode (type instead of speak, for debugging)
    python main.py --text
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
from rich import print as rprint

# ---------------------------------------------------------------------------
# Terminal encoding setup for Windows
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Logging setup — must happen before importing our modules
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
# Load environment variables
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Local imports (after env is loaded)
# ---------------------------------------------------------------------------
import config
from audio.listener import WakeWordListener
from audio.transcriber import Transcriber
from audio.speaker import Speaker
from audio import listener as _listener_module
from audio import speaker as _speaker_module
from core.agent import Agent
from core.tool_dispatcher import ToolDispatcher
from core import websocket_server


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def print_banner() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]⚡ Project JARVIS[/bold cyan]\n"
            f"[dim]Assistant for [bold white]{config.USER_NAME}[/bold white] "
            f"| Wake word: [bold yellow]\"{config.WAKE_WORD_MODEL.replace('_', ' ').title()}\"[/bold yellow][/dim]\n"
            f"[dim]STT: faster-whisper ({config.WHISPER_MODEL_SIZE}) on {config.WHISPER_DEVICE.upper()} "
            f"| TTS: {config.TTS_BACKEND} | Model: {config.GEMINI_MODEL}[/dim]",
            border_style="cyan",
            title="[bold]JARVIS v1.0[/bold]",
        )
    )


# ---------------------------------------------------------------------------
# Component Loading
# ---------------------------------------------------------------------------

def load_components() -> tuple[WakeWordListener, Transcriber, Speaker, Agent]:
    """Initialise and load all AI/audio components. May raise on failure."""

    with console.status("[cyan]Loading audio components…[/cyan]"):
        speaker = Speaker()
        speaker.load()
        console.print(f"  [green]✓[/green] TTS backend: [bold]{speaker.backend}[/bold]")

        transcriber = Transcriber()
        transcriber.load()
        console.print(f"  [green]✓[/green] STT: faster-whisper [bold]{config.WHISPER_MODEL_SIZE}[/bold] on [bold]{config.WHISPER_DEVICE.upper()}[/bold]")

        listener = WakeWordListener()
        listener.load()
        console.print(f"  [green]✓[/green] Wake word: [bold]{config.WAKE_WORD_MODEL}[/bold]")

    dispatcher = ToolDispatcher(speaker=speaker, transcriber=transcriber)

    with console.status("[cyan]Connecting to Gemini API…[/cyan]"):
        agent = Agent(tool_dispatcher=dispatcher)
        agent.load()
        console.print(f"  [green]✓[/green] Gemini model: [bold]{config.GEMINI_MODEL}[/bold]")

    return listener, transcriber, speaker, agent


# ---------------------------------------------------------------------------
# Smoke Test Mode
# ---------------------------------------------------------------------------

def run_smoke_test(
    listener: WakeWordListener,
    transcriber: Transcriber,
    speaker: Speaker,
    agent: Agent,
) -> None:
    """Run a non-interactive component validation."""
    console.rule("[bold yellow]Smoke Test Mode[/bold yellow]")
    errors: list[str] = []

    # Test TTS
    console.print("[cyan]Testing TTS…[/cyan]")
    try:
        speaker.speak(f"Smoke test active. Hello, {config.USER_NAME}.")
        console.print("  [green]✓[/green] TTS OK")
    except Exception as exc:
        errors.append(f"TTS: {exc}")
        console.print(f"  [red]✗[/red] TTS error: {exc}")

    # Test Gemini (simple text query, no tools)
    console.print("[cyan]Testing Gemini API…[/cyan]")
    try:
        response = asyncio.run(agent.process("Say 'JARVIS online' in exactly those two words."))
        console.print(f"  [green]✓[/green] Gemini OK → '{response}'")
    except Exception as exc:
        errors.append(f"Gemini: {exc}")
        console.print(f"  [red]✗[/red] Gemini error: {exc}")

    # Test system tools
    console.print("[cyan]Testing system tools…[/cyan]")
    try:
        from tools import system_info
        info = system_info.get_system_info()
        console.print(f"  [green]✓[/green] System info: {info}")
    except Exception as exc:
        errors.append(f"System info: {exc}")
        console.print(f"  [red]✗[/red] System info error: {exc}")

    console.rule()
    if errors:
        console.print(f"[bold red]Smoke test completed with {len(errors)} error(s):[/bold red]")
        for e in errors:
            console.print(f"  [red]• {e}[/red]")
        sys.exit(1)
    else:
        console.print("[bold green]✓ All smoke tests passed.[/bold green]")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Text Mode (keyboard input instead of mic)
# ---------------------------------------------------------------------------

def run_text_mode(speaker: Speaker, agent: Agent) -> None:
    """Interactive text mode — type commands instead of speaking them."""
    console.rule("[bold blue]Text Mode (type 'quit' to exit)[/bold blue]")
    speaker.speak(f"Text mode active. Type your commands, {config.USER_NAME}.")

    while True:
        try:
            user_input = input(f"\n[{config.USER_NAME}] ▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.lower() in {"quit", "exit", "bye"}:
            speaker.speak(f"Goodbye, {config.USER_NAME}.")
            break

        if not user_input:
            continue

        response = asyncio.run(agent.process(user_input))
        console.print(f"\n[bold cyan][JARVIS][/bold cyan] {response}\n")
        speaker.speak(response)


# ---------------------------------------------------------------------------
# Main Event Loop
# ---------------------------------------------------------------------------

def run_main_loop(
    listener: WakeWordListener,
    transcriber: Transcriber,
    speaker: Speaker,
    agent: Agent,
) -> None:
    asyncio.run(_run_main_loop_async(listener, transcriber, speaker, agent))

async def _run_main_loop_async(
    listener: WakeWordListener,
    transcriber: Transcriber,
    speaker: Speaker,
    agent: Agent,
) -> None:
    """
    The primary voice interaction loop:
    Listen → Wake → Transcribe → Think → Speak → Repeat
    """
    # Start the websocket server in the background
    asyncio.create_task(websocket_server.start_server())
    
    logger.info("Starting main event loop...")
    
    listener.start()
    speaker.speak(
        f"JARVIS online. I'm listening for your wake word, {config.USER_NAME}."
    )
    console.print(
        f"\n[bold green]⚡ JARVIS is listening…[/bold green] "
        f"Say [bold yellow]\"{config.WAKE_WORD_MODEL.replace('_', ' ').title()}\"[/bold yellow] to activate.\n"
    )

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    try:
        while True:
            # ── Step 1: Wait for wake word ──────────────────────────────
            websocket_server.broadcast("LISTENING")
            wake_detected = await asyncio.to_thread(listener.wait_for_wake_word, 0.5)
            if not wake_detected:
                continue

            console.print("[bold yellow]⚡ Wake word detected![/bold yellow]")

            # Pause listener to avoid mic contention and stop recording JARVIS's own speech
            listener.pause()

            # ── Step 2: Greet and prompt for input ──────────────────────
            speaker.speak(f"Yes, {config.USER_NAME}?")
            time.sleep(0.2)

            # ── Step 3: Transcribe user command ─────────────────────────
            logger.info("Listening for command…")
            websocket_server.broadcast("RECORDING")
            try:
                user_text = await asyncio.to_thread(transcriber.listen_and_transcribe)
                listener.resume()
            except Exception as exc:
                logger.error("Transcription failed: %s", exc)
                speaker.speak("Sorry, I had trouble hearing that. Please try again.")
                listener.reset()
                listener.resume()
                continue

            if not user_text.strip():
                speaker.speak("I didn't catch that. Please try again.")
                listener.reset()
                listener.resume()
                continue

            console.print(f"[bold white]You:[/bold white] {user_text}")

            # ── Step 4: Process with Gemini (25s timeout) ────────────────
            try:
                websocket_server.broadcast("THINKING")
                try:
                    response = await asyncio.wait_for(agent.process(user_text), timeout=25.0)
                    consecutive_errors = 0
                except asyncio.TimeoutError:
                    response = (
                        f"Sorry {config.USER_NAME}, I'm having trouble connecting to Gemini. "
                        "Please try again."
                    )
                    logger.warning("Gemini API timed out after 25s — resetting history.")
                    agent.reset_history()
                    consecutive_errors += 1
            except Exception as exc:
                consecutive_errors += 1
                logger.error("Agent error (%d): %s", consecutive_errors, exc)
                response = "I encountered an error. Please try again."
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    speaker.speak(
                        "I'm experiencing repeated errors. Restarting the conversation."
                    )
                    agent.reset_history()
                    consecutive_errors = 0

            # ── Step 5: Speak the response ───────────────────────────────
            console.print(f"[bold cyan]JARVIS:[/bold cyan] {response}")
            speaker.speak(response)

            # ── Step 6: Cooldown → reset → resume listening ──────────────
            # Wait for acoustic echo to die down, then hard-reset the
            # openwakeword model so TTS audio doesn't bleed into the next
            # detection window and cause missed or phantom wake words.
            time.sleep(config.WAKE_WORD_COOLDOWN_SEC)
            listener.reset()
            listener.resume()


    except KeyboardInterrupt:
        console.print("\n[bold red]Shutting down JARVIS… (Ctrl+C received)[/bold red]")
    finally:
        # ── Signal ALL blocking calls to exit immediately ─────────────
        _listener_module.shutdown_event.set()
        _speaker_module.shutdown_event.set()

        # ── Stop hardware cleanly ─────────────────────────────────────
        try:
            speaker.stop()      # calls sd.stop() — kills any active audio
        except Exception:
            pass
        try:
            listener.stop()     # stops mic stream and worker thread
        except Exception:
            pass

        # NOTE: Do NOT call speaker.speak() here — pyttsx3/sounddevice
        # may already be in a broken state and will freeze the process.
        console.print("[dim]JARVIS offline.[/dim]")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project JARVIS — AI Desktop Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run smoke test and exit without starting the voice loop."
    )
    parser.add_argument(
        "--text", action="store_true",
        help="Text mode: type commands instead of speaking them."
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity."
    )
    args = parser.parse_args()

    # Apply log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    print_banner()

    # Validate API key early
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        console.print(
            "[bold red]ERROR:[/bold red] GEMINI_API_KEY is not set.\n"
            "Edit [bold]E:\\projects\\jarvis\\.env[/bold] and replace the placeholder with your real key.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )
        sys.exit(1)

    try:
        listener, transcriber, speaker, agent = load_components()
    except Exception as exc:
        console.print(f"[bold red]Failed to initialise JARVIS:[/bold red] {exc}")
        logger.exception("Startup failure")
        sys.exit(1)

    if args.test:
        run_smoke_test(listener, transcriber, speaker, agent)
    elif args.text:
        run_text_mode(speaker, agent)
    else:
        run_main_loop(listener, transcriber, speaker, agent)


if __name__ == "__main__":
    main()
