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

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info(f"WebSocket disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: str):
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.active.remove(ws)


manager = ConnectionManager()


async def _valkey_subscriber():
    """Background task: subscribe to Valkey pub/sub and broadcast to WebSocket clients."""
    pubsub_client = cache.get_pubsub_client()
    pubsub = pubsub_client.pubsub()
    await pubsub.subscribe("live-quakes")
    logger.info("Valkey pub/sub subscriber started")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"])
    except asyncio.CancelledError:
        await pubsub.unsubscribe("live-quakes")
        await pubsub.aclose()
        logger.info("Valkey pub/sub subscriber stopped")
    except Exception:
        logger.exception("Valkey pub/sub subscriber error")


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
        recent = await cache.get_recent_cached(limit=20)
        await ws.send_text(json.dumps({"type": "initial", "data": recent}))

        # Keep connection alive, listen for client messages (e.g., pings)
        while True:
            data = await ws.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
