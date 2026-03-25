import asyncio
import json
import logging

import httpx
from aiokafka import AIOKafkaProducer

from app.config import settings

logger = logging.getLogger(__name__)

USGS_FEEDS = {
    "all_hour": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson",
    "all_day": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
}

TOPIC_RAW = "raw-quakes"
TOPIC_SIGNIFICANT = "significant-quakes"
TOPIC_ALERTS = "quake-alerts"

_producer: AIOKafkaProducer | None = None
_seen_ids: set[str] = set()
MAX_SEEN_IDS = 5000


def _parse_feature(feature: dict) -> dict | None:
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates", [None, None, None])

    quake_id = feature.get("id")
    if not quake_id or len(coords) < 2:
        return None

    return {
        "id": quake_id,
        "magnitude": props.get("mag"),
        "place": props.get("place"),
        "time": props.get("time"),
        "updated": props.get("updated"),
        "longitude": coords[0],
        "latitude": coords[1],
        "depth": coords[2] if len(coords) > 2 else None,
        "url": props.get("url"),
        "felt": props.get("felt"),
        "tsunami": props.get("tsunami", 0),
        "sig": props.get("sig"),
        "mag_type": props.get("magType"),
        "event_type": props.get("type"),
        "title": props.get("title"),
        "alert": props.get("alert"),
    }


async def init_producer():
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol="SSL",
        ssl_context=settings.kafka_ssl_context(),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )
    await _producer.start()
    logger.info("Kafka producer started")


async def stop_producer():
    global _producer
    if _producer:
        await _producer.stop()
        logger.info("Kafka producer stopped")


async def _produce_quake(quake: dict):
    if _producer is None:
        return

    quake_id = quake["id"]
    mag = quake.get("magnitude") or 0
    tsunami = quake.get("tsunami", 0)

    await _producer.send_and_wait(TOPIC_RAW, value=quake, key=quake_id)

    if mag >= 4.5:
        await _producer.send_and_wait(TOPIC_SIGNIFICANT, value=quake, key=quake_id)

    if mag >= 6.0 or tsunami == 1:
        await _producer.send_and_wait(TOPIC_ALERTS, value=quake, key=quake_id)


async def _fetch_and_produce(feed_url: str):
    global _seen_ids

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(feed_url)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features", [])
    new_count = 0

    for feature in features:
        quake = _parse_feature(feature)
        if quake is None:
            continue

        if quake["id"] in _seen_ids:
            continue

        _seen_ids.add(quake["id"])
        await _produce_quake(quake)
        new_count += 1

    # Prevent unbounded memory growth
    if len(_seen_ids) > MAX_SEEN_IDS:
        _seen_ids = set(list(_seen_ids)[-MAX_SEEN_IDS:])

    if new_count > 0:
        logger.info(f"Produced {new_count} new earthquakes from {feed_url}")


async def seed_from_daily():
    """Fetch the past-day feed on startup to populate initial data."""
    logger.info("Seeding initial data from USGS all_day feed...")
    try:
        await _fetch_and_produce(USGS_FEEDS["all_day"])
    except Exception:
        logger.exception("Failed to seed from daily feed")


async def poll_usgs_loop():
    """Main producer loop — polls USGS every interval."""
    logger.info(
        f"Starting USGS poll loop (interval={settings.usgs_poll_interval_seconds}s)"
    )
    while True:
        try:
            await _fetch_and_produce(USGS_FEEDS["all_hour"])
        except Exception:
            logger.exception("Error in USGS poll loop")
        await asyncio.sleep(settings.usgs_poll_interval_seconds)
