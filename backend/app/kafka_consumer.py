import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError, KafkaError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import async_session
from app.models import Earthquake
from app import cache

logger = logging.getLogger(__name__)

TOPIC_RAW = "raw-quakes"
TOPIC_SIGNIFICANT = "significant-quakes"
TOPIC_ALERTS = "quake-alerts"

_consumer: AIOKafkaConsumer | None = None


async def init_consumer(max_retries: int = 5):
    global _consumer
    for attempt in range(1, max_retries + 1):
        try:
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
            return
        except (KafkaConnectionError, KafkaError, OSError) as exc:
            logger.warning(
                f"Kafka consumer connect attempt {attempt}/{max_retries} failed: {exc}"
            )
            _consumer = None
            if attempt < max_retries:
                delay = min(2 ** attempt, 30)
                await asyncio.sleep(delay)
    logger.error("Kafka consumer failed to start after all retries")


async def stop_consumer():
    global _consumer
    if _consumer:
        await _consumer.stop()
        logger.info("Kafka consumer stopped")


def _validate_quake_data(data: dict) -> bool:
    """Validate that required fields are present and sane."""
    required = ("id", "longitude", "latitude")
    for field in required:
        if field not in data or data[field] is None:
            return False
    try:
        float(data["longitude"])
        float(data["latitude"])
    except (TypeError, ValueError):
        return False
    return True


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
    """Main consumer loop — processes messages from Kafka with auto-reconnect."""
    reconnect_delay = 5
    max_reconnect_delay = 120

    while True:
        if _consumer is None:
            logger.warning("Kafka consumer not available, retrying init...")
            await init_consumer()
            if _consumer is None:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                continue
            reconnect_delay = 5  # reset on success

        logger.info("Starting Kafka consumer loop")
        try:
            async for msg in _consumer:
                try:
                    quake_data = msg.value

                    # Validate deserialized message
                    if not isinstance(quake_data, dict):
                        logger.warning(
                            f"Skipping non-dict message on {msg.topic}: {type(quake_data)}"
                        )
                        continue

                    if msg.topic == TOPIC_RAW:
                        if not _validate_quake_data(quake_data):
                            logger.warning(
                                f"Skipping malformed quake message: missing required fields "
                                f"(id={quake_data.get('id')})"
                            )
                            continue

                        # Store in PostgreSQL
                        try:
                            await _upsert_earthquake(quake_data)
                        except SQLAlchemyError:
                            logger.exception(
                                f"DB upsert failed for quake {quake_data.get('id')}"
                            )

                        # Cache in Valkey (best-effort)
                        try:
                            await cache.cache_earthquake(quake_data)
                        except Exception:
                            logger.exception("Valkey cache_earthquake failed")

                        # Publish live event for WebSocket clients (best-effort)
                        try:
                            await cache.publish_live_event(quake_data)
                        except Exception:
                            logger.exception("Valkey publish_live_event failed")

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

                except json.JSONDecodeError:
                    logger.error(
                        f"Failed to decode JSON from {msg.topic}, offset={msg.offset}"
                    )
                except Exception:
                    logger.exception(
                        f"Error processing message from {msg.topic}, "
                        f"offset={msg.offset}"
                    )

        except (KafkaConnectionError, KafkaError) as exc:
            logger.error(f"Kafka consumer connection lost: {exc}. Reconnecting...")
            # Try to cleanly stop the broken consumer
            try:
                await stop_consumer()
            except Exception:
                pass
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected error in consumer loop")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
