import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import cache

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.append(ws)
        logger.info(f"WebSocket connected. Total: {len(self.active)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            try:
                self.active.remove(ws)
            except ValueError:
                pass
        logger.info(f"WebSocket disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: str):
        async with self._lock:
            clients = list(self.active)

        disconnected = []
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    try:
                        self.active.remove(ws)
                    except ValueError:
                        pass


manager = ConnectionManager()


async def _valkey_subscriber():
    """Background task: subscribe to Valkey pub/sub and broadcast to WebSocket clients.

    Automatically reconnects on connection failure with exponential backoff.
    """
    reconnect_delay = 1
    max_reconnect_delay = 60

    while True:
        pubsub = None
        pubsub_client = None
        try:
            pubsub_client = cache.get_pubsub_client()
            pubsub = pubsub_client.pubsub()
            await pubsub.subscribe("live-quakes")
            logger.info("Valkey pub/sub subscriber started")
            reconnect_delay = 1  # reset on successful connection

            async for message in pubsub.listen():
                if message["type"] == "message":
                    await manager.broadcast(message["data"])

        except asyncio.CancelledError:
            if pubsub:
                try:
                    await pubsub.unsubscribe("live-quakes")
                    await pubsub.aclose()
                except Exception:
                    pass
            logger.info("Valkey pub/sub subscriber stopped")
            return
        except Exception:
            logger.exception(
                f"Valkey pub/sub subscriber error, reconnecting in {reconnect_delay}s..."
            )
            if pubsub:
                try:
                    await pubsub.unsubscribe("live-quakes")
                    await pubsub.aclose()
                except Exception:
                    pass
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


_subscriber_task: asyncio.Task | None = None


async def start_subscriber():
    global _subscriber_task
    _subscriber_task = asyncio.create_task(_valkey_subscriber())


async def stop_subscriber():
    global _subscriber_task
    if _subscriber_task:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except asyncio.CancelledError:
            pass


@router.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send recent earthquakes as initial payload
        try:
            recent = await cache.get_recent_cached(limit=20)
        except Exception:
            logger.warning("Failed to fetch recent cache for WS initial payload")
            recent = []
        await ws.send_text(json.dumps({"type": "initial", "data": recent}))

        # Keep connection alive, listen for client messages (e.g., pings)
        while True:
            data = await ws.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        logger.debug("WebSocket connection closed unexpectedly")
        await manager.disconnect(ws)
