import json
import logging

from aiokafka import AIOKafkaConsumer
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.database import async_session
from app.models import Earthquake
from app import cache

logger = logging.getLogger(__name__)

TOPIC_RAW = "raw-quakes"
TOPIC_SIGNIFICANT = "significant-quakes"
TOPIC_ALERTS = "quake-alerts"

_consumer: AIOKafkaConsumer | None = None


async def init_consumer():
    global _consumer
    _consumer = AIOKafkaConsumer(
        TOPIC_RAW,
        TOPIC_SIGNIFICANT,
        TOPIC_ALERTS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol="SSL",
        ssl_context=settings.kafka_ssl_context(),
        group_id="quakepulse-consumer",
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=True,
    )
    await _consumer.start()
    logger.info("Kafka consumer started")


async def stop_consumer():
    global _consumer
    if _consumer:
        await _consumer.stop()
        logger.info("Kafka consumer stopped")


async def _upsert_earthquake(quake_data: dict):
    """Insert or update an earthquake record in PostgreSQL."""
    async with async_session() as session:
        stmt = pg_insert(Earthquake).values(
            id=quake_data["id"],
            magnitude=quake_data.get("magnitude"),
            place=quake_data.get("place"),
            time=quake_data.get("time"),
            updated=quake_data.get("updated"),
            longitude=quake_data["longitude"],
            latitude=quake_data["latitude"],
            depth=quake_data.get("depth"),
            url=quake_data.get("url"),
            felt=quake_data.get("felt"),
            tsunami=quake_data.get("tsunami", 0),
            sig=quake_data.get("sig"),
            mag_type=quake_data.get("mag_type"),
            event_type=quake_data.get("event_type"),
            title=quake_data.get("title"),
            alert=quake_data.get("alert"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "magnitude": stmt.excluded.magnitude,
                "updated": stmt.excluded.updated,
                "felt": stmt.excluded.felt,
                "sig": stmt.excluded.sig,
                "alert": stmt.excluded.alert,
            },
        )
        await session.execute(stmt)
        await session.commit()


async def consume_loop():
    """Main consumer loop — processes messages from Kafka."""
    if _consumer is None:
        return

    logger.info("Starting Kafka consumer loop")
    async for msg in _consumer:
        try:
            quake_data = msg.value

            if msg.topic == TOPIC_RAW:
                # Store in PostgreSQL
                await _upsert_earthquake(quake_data)

                # Cache in Valkey
                await cache.cache_earthquake(quake_data)

                # Publish live event for WebSocket clients
                await cache.publish_live_event(quake_data)

            elif msg.topic == TOPIC_SIGNIFICANT:
                logger.info(
                    f"Significant quake: M{quake_data.get('magnitude')} "
                    f"at {quake_data.get('place')}"
                )

            elif msg.topic == TOPIC_ALERTS:
                logger.warning(
                    f"ALERT quake: M{quake_data.get('magnitude')} "
                    f"at {quake_data.get('place')} "
                    f"tsunami={quake_data.get('tsunami')}"
                )

        except Exception:
            logger.exception(f"Error processing message from {msg.topic}")
