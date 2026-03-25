import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase
from pydantic import BaseModel


# --- SQLAlchemy ORM model ---

class Base(DeclarativeBase):
    pass


class Earthquake(Base):
    __tablename__ = "earthquakes"

    id = Column(String, primary_key=True)  # USGS earthquake ID
    magnitude = Column(Float, nullable=True)
    place = Column(String, nullable=True)
    time = Column(BigInteger)  # epoch ms from USGS
    updated = Column(BigInteger, nullable=True)
    longitude = Column(Float)
    latitude = Column(Float)
    depth = Column(Float, nullable=True)
    url = Column(String, nullable=True)
    felt = Column(Integer, nullable=True)
    tsunami = Column(Integer, default=0)
    sig = Column(Integer, nullable=True)
    mag_type = Column(String, nullable=True)
    event_type = Column(String, nullable=True)
    title = Column(String, nullable=True)
    alert = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# --- Pydantic response schemas ---

class EarthquakeSchema(BaseModel):
    id: str
    magnitude: float | None = None
    place: str | None = None
    time: int
    updated: int | None = None
    longitude: float
    latitude: float
    depth: float | None = None
    url: str | None = None
    felt: int | None = None
    tsunami: int = 0
    sig: int | None = None
    mag_type: str | None = None
    event_type: str | None = None
    title: str | None = None
    alert: str | None = None

    model_config = {"from_attributes": True}


class StatsSchema(BaseModel):
    total_count: int
    last_24h_count: int
    avg_magnitude: float | None
    max_magnitude: float | None
    magnitude_distribution: dict[str, int]
    hourly_counts: list[dict]
    top_regions: list[dict]
