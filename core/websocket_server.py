import asyncio
import json
import logging
import websockets

logger = logging.getLogger(__name__)

_CLIENTS = set()
_MAIN_LOOP = None

async def handler(websocket):
    _CLIENTS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        _CLIENTS.remove(websocket)

async def start_server():
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()
    try:
        async with websockets.serve(handler, "localhost", 8765):
            logger.info("WebSocket server running on ws://localhost:8765")
            await asyncio.Future()  # run forever
    except Exception as e:
        logger.error(f"WebSocket server error: {e}")

def broadcast(state: str, volume: float = 0.0, text: str = ""):
    if not _CLIENTS or not _MAIN_LOOP:
        return
    message = json.dumps({"state": state, "volume": volume, "text": text})
    for client in _CLIENTS:
        try:
            asyncio.run_coroutine_threadsafe(client.send(message), _MAIN_LOOP)
        except Exception as e:
            pass
