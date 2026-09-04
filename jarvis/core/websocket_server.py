"""
jarvis/core/websocket_server.py — Frontend WebSocket Bridge
============================================================
Runs a lightweight asyncio WebSocket server that broadcasts JARVIS's
internal state to any connected frontend clients (e.g., the WebGL orb).

Message Format
--------------
Every broadcast is a JSON object:
    {
        "state": "LISTENING" | "RECORDING" | "THINKING" | "SPEAKING",
        "volume": float,   # 0.0–1.0 (reserved for future audio reactivity)
        "text": str        # The text being spoken (optional)
    }

Usage
-----
    from jarvis.core import websocket_server

    # In the async main loop, start the server as a background task:
    asyncio.create_task(websocket_server.start_server())

    # Broadcast a state change from anywhere (thread-safe):
    websocket_server.broadcast("SPEAKING", text="Hello, Arush!")
"""

from __future__ import annotations

import asyncio
import json
import logging

import websockets  # type: ignore

logger = logging.getLogger(__name__)

# Set of all currently connected WebSocket clients
_CLIENTS: set = set()

# The running asyncio event loop — set when start_server() is called.
# broadcast() uses this to safely schedule coroutines from sync threads.
_MAIN_LOOP: asyncio.AbstractEventLoop | None = None


async def _handler(websocket) -> None:
    """Handle a new WebSocket client connection.

    Registers the client in _CLIENTS for the duration of its connection,
    then removes it automatically when it disconnects.
    """
    _CLIENTS.add(websocket)
    logger.debug("Frontend client connected. Total: %d", len(_CLIENTS))
    try:
        await websocket.wait_closed()
    finally:
        _CLIENTS.discard(websocket)
        logger.debug("Frontend client disconnected. Total: %d", len(_CLIENTS))


async def start_server(host: str = "localhost", port: int = 8765) -> None:
    """Start the WebSocket server and run it indefinitely.

    This coroutine never returns under normal operation. It should be
    launched as an asyncio background task:
        asyncio.create_task(websocket_server.start_server())

    Parameters
    ----------
    host : str
        The hostname to bind to (default: localhost).
    port : int
        The TCP port to listen on (default: 8765).
    """
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()
    try:
        async with websockets.serve(_handler, host, port):
            logger.info("WebSocket server running on ws://%s:%d", host, port)
            await asyncio.Future()  # Suspend forever — never resolves
    except Exception as e:
        logger.error("WebSocket server error: %s", e)


def broadcast(state: str, volume: float = 0.0, text: str = "") -> None:
    """Send a state update to all connected frontend clients.

    Thread-safe: uses asyncio.run_coroutine_threadsafe() so this can be
    called safely from the synchronous main loop or any thread.

    Parameters
    ----------
    state : str
        Current JARVIS state: "LISTENING", "RECORDING", "THINKING", or "SPEAKING".
    volume : float
        Audio volume level 0.0–1.0 (reserved for future use).
    text : str
        The text being processed (optional, for display in the frontend).
    """
    if not _CLIENTS or not _MAIN_LOOP:
        return  # No clients connected or server not started yet

    message = json.dumps({"state": state, "volume": volume, "text": text})
    for client in list(_CLIENTS):  # Snapshot to avoid mutation during iteration
        try:
            asyncio.run_coroutine_threadsafe(client.send(message), _MAIN_LOOP)
        except Exception as e:
            logger.debug("Failed to send to client: %s", e)
