import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db, close_db
from app import cache
from app.kafka_producer import init_producer, stop_producer, seed_from_daily, poll_usgs_loop
from app.kafka_consumer import init_consumer, stop_consumer, consume_loop
from app.routes.earthquakes import router as earthquakes_router
from app.routes.websocket import router as ws_router, start_subscriber, stop_subscriber

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

_bg_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Starting QuakePulse...")

    # Initialize services
    await init_db()
    await cache.init_valkey()
    await init_producer()
    await init_consumer()

    # Start background tasks
    _bg_tasks.append(asyncio.create_task(seed_and_poll()))
    _bg_tasks.append(asyncio.create_task(consume_loop()))
    await start_subscriber()

    logger.info("QuakePulse started successfully")
    yield

    # --- Shutdown ---
    logger.info("Shutting down QuakePulse...")
    for task in _bg_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await stop_subscriber()
    await stop_consumer()
    await stop_producer()
    await cache.close_valkey()
    await close_db()
    logger.info("QuakePulse shutdown complete")


async def seed_and_poll():
    """Seed from daily feed, then start the regular poll loop."""
    await seed_from_daily()
    await poll_usgs_loop()


app = FastAPI(
    title="QuakePulse",
    description="Real-time earthquake monitoring powered by Aiven",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(earthquakes_router)
app.include_router(ws_router)

# Serve frontend static files
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
