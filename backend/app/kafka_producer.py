import asyncio
import json
import logging
import time

import httpx
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError, KafkaError

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

# --- Circuit breaker state ---
_circuit_failures: int = 0
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RESET_TIMEOUT = 60  # seconds
_circuit_open_until: float = 0


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


async def init_producer(max_retries: int = 5):
    global _producer
    for attempt in range(1, max_retries + 1):
        try:
            _producer = AIOKafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                security_protocol="SSL",
                ssl_context=settings.kafka_ssl_context(),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                request_timeout_ms=15000,
                retry_backoff_ms=500,
            )
            await _producer.start()
            logger.info("Kafka producer started")
            return
        except (KafkaConnectionError, KafkaError, OSError) as exc:
            logger.warning(
                f"Kafka producer connect attempt {attempt}/{max_retries} failed: {exc}"
            )
            _producer = None
            if attempt < max_retries:
                delay = min(2 ** attempt, 30)
                await asyncio.sleep(delay)
    logger.error("Kafka producer failed to start after all retries")


async def stop_producer():
    global _producer
    if _producer:
        await _producer.stop()
        logger.info("Kafka producer stopped")


def _is_circuit_open() -> bool:
    return _circuit_failures >= CIRCUIT_FAILURE_THRESHOLD and time.time() < _circuit_open_until


def _record_circuit_failure():
    global _circuit_failures, _circuit_open_until
    _circuit_failures += 1
    if _circuit_failures >= CIRCUIT_FAILURE_THRESHOLD:
        _circuit_open_until = time.time() + CIRCUIT_RESET_TIMEOUT
        logger.warning(
            f"Circuit breaker OPEN — suppressing Kafka sends for {CIRCUIT_RESET_TIMEOUT}s"
        )


def _record_circuit_success():
    global _circuit_failures, _circuit_open_until
    if _circuit_failures > 0:
        _circuit_failures = 0
        _circuit_open_until = 0


async def _produce_quake(quake: dict):
    if _producer is None:
        logger.debug("Kafka producer not initialized — skipping produce")
        return

    if _is_circuit_open():
        logger.debug("Circuit breaker open — skipping produce")
        return

    quake_id = quake["id"]
    mag = quake.get("magnitude") or 0
    tsunami = quake.get("tsunami", 0)

    try:
        await _producer.send_and_wait(TOPIC_RAW, value=quake, key=quake_id)

        if mag >= 4.5:
            await _producer.send_and_wait(TOPIC_SIGNIFICANT, value=quake, key=quake_id)

        if mag >= 6.0 or tsunami == 1:
            await _producer.send_and_wait(TOPIC_ALERTS, value=quake, key=quake_id)

        _record_circuit_success()
    except (KafkaConnectionError, KafkaError) as exc:
        _record_circuit_failure()
        logger.error(f"Kafka produce failed for {quake_id}: {exc}")


async def _fetch_and_produce(feed_url: str, retries: int = 3):
    global _seen_ids

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                data = resp.json()
            break
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            logger.warning(
                f"USGS fetch attempt {attempt}/{retries} failed for {feed_url}: {exc}"
            )
            if attempt < retries:
                await asyncio.sleep(min(2 ** attempt, 15))
    else:
        logger.error(f"USGS fetch failed after {retries} retries: {last_exc}")
        return

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
