import time
import logging
from collections import Counter

from fastapi import APIRouter, Query
from sqlalchemy import select, func, case, text

from app.database import async_session, engine
from app.models import Earthquake, EarthquakeSchema, StatsSchema
from app import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["earthquakes"])


@router.get("/earthquakes", response_model=list[EarthquakeSchema])
async def list_earthquakes(
    hours: int = Query(24, ge=1, le=720),
    min_mag: float = Query(0, ge=-2, le=10),
    max_mag: float = Query(10, ge=-2, le=10),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    cutoff_ms = int((time.time() - hours * 3600) * 1000)

    async with async_session() as session:
        stmt = (
            select(Earthquake)
            .where(Earthquake.time >= cutoff_ms)
            .where(Earthquake.magnitude >= min_mag)
            .where(Earthquake.magnitude <= max_mag)
            .order_by(Earthquake.time.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        quakes = result.scalars().all()
    return quakes


@router.get("/earthquakes/bbox", response_model=list[EarthquakeSchema])
async def earthquakes_in_bbox(
    north: float = Query(..., ge=-90, le=90),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    west: float = Query(..., ge=-180, le=180),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(500, ge=1, le=2000),
):
    cutoff_ms = int((time.time() - hours * 3600) * 1000)

    async with async_session() as session:
        stmt = (
            select(Earthquake)
            .where(Earthquake.time >= cutoff_ms)
            .where(Earthquake.latitude >= south)
            .where(Earthquake.latitude <= north)
            .where(Earthquake.longitude >= west)
            .where(Earthquake.longitude <= east)
            .order_by(Earthquake.time.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        quakes = result.scalars().all()
    return quakes


@router.get("/earthquakes/{quake_id}", response_model=EarthquakeSchema)
async def get_earthquake(quake_id: str):
    # Check Valkey cache first
    cached = await cache.get_cached_quake(quake_id)
    if cached:
        return cached

    async with async_session() as session:
        result = await session.get(Earthquake, quake_id)
        if result is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Earthquake not found")
        return result


@router.get("/stats", response_model=StatsSchema)
async def get_stats():
    # Check cache first
    cached = await cache.get_cached_stats()
    if cached:
        return cached

    now_ms = int(time.time() * 1000)
    day_ago_ms = now_ms - 86400_000
    week_ago_ms = now_ms - 7 * 86400_000

    async with async_session() as session:
        # Total count (last 7 days)
        total_result = await session.execute(
            select(func.count(Earthquake.id)).where(Earthquake.time >= week_ago_ms)
        )
        total_count = total_result.scalar() or 0

        # Last 24h count
        day_result = await session.execute(
            select(func.count(Earthquake.id)).where(Earthquake.time >= day_ago_ms)
        )
        last_24h_count = day_result.scalar() or 0

        # Avg and max magnitude (last 7 days)
        agg_result = await session.execute(
            select(
                func.avg(Earthquake.magnitude),
                func.max(Earthquake.magnitude),
            ).where(Earthquake.time >= week_ago_ms)
        )
        row = agg_result.one()
        avg_mag = round(float(row[0]), 2) if row[0] is not None else None
        max_mag = float(row[1]) if row[1] is not None else None

        # Magnitude distribution
        mag_dist_result = await session.execute(
            select(
                case(
                    (Earthquake.magnitude < 1, "< 1"),
                    (Earthquake.magnitude < 2, "1-2"),
                    (Earthquake.magnitude < 3, "2-3"),
                    (Earthquake.magnitude < 4, "3-4"),
                    (Earthquake.magnitude < 5, "4-5"),
                    (Earthquake.magnitude < 6, "5-6"),
                    else_="6+",
                ).label("bucket"),
                func.count().label("count"),
            )
            .where(Earthquake.time >= week_ago_ms)
            .where(Earthquake.magnitude.isnot(None))
            .group_by(text("bucket"))
        )
        magnitude_distribution = {r.bucket: r.count for r in mag_dist_result.all()}

        # Hourly counts (last 24h)
        hour_ms = 3600_000
        time_result = await session.execute(
            select(Earthquake.time).where(Earthquake.time >= day_ago_ms)
        )
        times = [r[0] for r in time_result.all()]
        hourly_buckets = Counter(t // hour_ms for t in times)
        hourly_counts = sorted(
            [{"hour_ms": bucket * hour_ms, "count": count} for bucket, count in hourly_buckets.items()],
            key=lambda x: x["hour_ms"],
        )

        # Top regions (extract first part after "of" in place string)
        region_result = await session.execute(
            select(
                Earthquake.place,
                func.count().label("count"),
            )
            .where(Earthquake.time >= week_ago_ms)
            .where(Earthquake.place.isnot(None))
            .group_by(Earthquake.place)
            .order_by(text("count DESC"))
            .limit(10)
        )
        top_regions = [
            {"place": r.place, "count": r.count}
            for r in region_result.all()
        ]

    stats = StatsSchema(
        total_count=total_count,
        last_24h_count=last_24h_count,
        avg_magnitude=avg_mag,
        max_magnitude=max_mag,
        magnitude_distribution=magnitude_distribution,
        hourly_counts=hourly_counts,
        top_regions=top_regions,
    )

    # Cache the stats
    await cache.set_cached_stats(stats.model_dump())

    return stats


@router.get("/health")
async def health_check():
    status = {"postgresql": False, "kafka": False, "valkey": False}

    # Check PostgreSQL
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        status["postgresql"] = True
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")

    # Check Valkey
    try:
        client = cache.get_client()
        await client.ping()
        status["valkey"] = True
    except Exception as e:
        logger.error(f"Valkey health check failed: {e}")

    # Kafka is checked implicitly — if producer/consumer are running
    from app.kafka_producer import _producer
    from app.kafka_consumer import _consumer
    status["kafka"] = _producer is not None and _consumer is not None

    all_healthy = all(status.values())
    return {"status": "ok" if all_healthy else "degraded", "services": status}
