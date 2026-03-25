import json
import logging
import time

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_pubsub_client: redis.Redis | None = None

RECENT_QUAKES_KEY = "recent_quakes"
STATS_KEY = "stats:daily"
MAX_RECENT = 200
STATS_TTL = 60


async def init_valkey():
    global _client, _pubsub_client
    _client = redis.from_url(settings.valkey_uri, decode_responses=True)
    _pubsub_client = redis.from_url(settings.valkey_uri, decode_responses=True)
    await _client.ping()
    logger.info("Valkey connected")


async def close_valkey():
    global _client, _pubsub_client
    if _client:
        await _client.aclose()
    if _pubsub_client:
        await _pubsub_client.aclose()
    logger.info("Valkey connections closed")


def get_client() -> redis.Redis:
    assert _client is not None, "Valkey not initialized"
    return _client


def get_pubsub_client() -> redis.Redis:
    assert _pubsub_client is not None, "Valkey pubsub client not initialized"
    return _pubsub_client


async def cache_earthquake(quake_data: dict):
    client = get_client()
    quake_json = json.dumps(quake_data)
    score = quake_data.get("time", int(time.time() * 1000))

    pipe = client.pipeline()
    pipe.zadd(RECENT_QUAKES_KEY, {quake_json: score})
    pipe.set(f"quake:{quake_data['id']}", quake_json, ex=300)
    await pipe.execute()

    # Trim to keep only the most recent entries
    count = await client.zcard(RECENT_QUAKES_KEY)
    if count > MAX_RECENT:
        await client.zremrangebyrank(RECENT_QUAKES_KEY, 0, count - MAX_RECENT - 1)


async def get_recent_cached(limit: int = 50) -> list[dict]:
    client = get_client()
    raw = await client.zrevrange(RECENT_QUAKES_KEY, 0, limit - 1)
    return [json.loads(item) for item in raw]


async def get_cached_quake(quake_id: str) -> dict | None:
    client = get_client()
    raw = await client.get(f"quake:{quake_id}")
    if raw:
        return json.loads(raw)
    return None


async def get_cached_stats() -> dict | None:
    client = get_client()
    raw = await client.get(STATS_KEY)
    if raw:
        return json.loads(raw)
    return None


async def set_cached_stats(stats: dict):
    client = get_client()
    await client.set(STATS_KEY, json.dumps(stats), ex=STATS_TTL)


async def publish_live_event(quake_data: dict):
    client = get_client()
    await client.publish("live-quakes", json.dumps(quake_data))
