# 🌍 QuakePulse — Real-Time Earthquake Monitor

A real-time earthquake monitoring dashboard that streams USGS earthquake data through **Aiven Kafka**, stores history in **Aiven PostgreSQL**, caches hot data in **Aiven Valkey**, and displays everything on a live interactive map.

Built for the [Aiven Free Tier Competition](https://aiven.io/blog/the-aiven-free-tier-competition) `#AivenFreeTier`

## Architecture

```
USGS GeoJSON API ──→ [Kafka Producer] ──→ Aiven Kafka (3 topics)
  (polled every 60s)                          │
                                        [Kafka Consumer]
                                         │           │
                                   Aiven PostgreSQL  Aiven Valkey
                                   (history store)   (cache + pub/sub)
                                         │           │
                                      [FastAPI Backend]
                                              │
                                     [WebSocket to Browser]
                                              │
                                    [Leaflet.js Live Map]
```

### How data flows

1. **Kafka Producer** polls the USGS earthquake feed every 60 seconds
2. New earthquakes are produced to Kafka topics: `raw-quakes`, `significant-quakes` (M4.5+), `quake-alerts` (M6+ or tsunami)
3. **Kafka Consumer** reads from all topics and:
   - Upserts data into **PostgreSQL** for persistent storage & analytics
   - Caches recent quakes in **Valkey** (sorted set) for fast retrieval
   - Publishes live events to a **Valkey pub/sub** channel
4. **WebSocket handler** subscribes to the Valkey pub/sub channel and fans out new events to all connected browsers
5. **Frontend** displays quakes on a live Leaflet map with real-time animations

### Aiven Services Used

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| **Apache Kafka** | Stream earthquake data via 3 topics | 5 topics, 3-day retention |
| **PostgreSQL** | Persistent storage, analytics queries | Managed instance |
| **Valkey** | Cache, pub/sub for real-time WebSocket push | In-memory data store |

## Features

- 🗺️ **Live interactive map** with color-coded earthquake markers (by magnitude)
- ⚡ **Real-time streaming** — new quakes appear without page refresh via WebSocket
- 📊 **Analytics dashboard** — magnitude distribution, hourly timeline, top regions
- 🔍 **Filtering** — filter by time range and minimum magnitude
- 📋 **Earthquake list** — click to fly to location on map
- 💓 **Health endpoint** — monitors all 3 Aiven service connections

## Prerequisites

- Python 3.11+
- An [Aiven account](https://console.aiven.io/signup) with free-tier services:
  - Aiven for Apache Kafka
  - Aiven for PostgreSQL
  - Aiven for Valkey

## Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/quakepulse.git
cd quakepulse/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Provision Aiven services

1. Sign up at [console.aiven.io](https://console.aiven.io/signup)
2. Create a **free-tier PostgreSQL** instance
3. Create a **free-tier Kafka** instance
   - Create topics: `raw-quakes`, `significant-quakes`, `quake-alerts`
   - Download the SSL certificates (CA cert, service cert, service key)
4. Create a **free-tier Valkey** instance

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your Aiven connection details:

```env
PG_URI=postgresql+asyncpg://user:password@host:port/defaultdb?ssl=require
KAFKA_BOOTSTRAP_SERVERS=kafka-host:port
KAFKA_SSL_CAFILE=./certs/ca.pem
KAFKA_SSL_CERTFILE=./certs/service.cert
KAFKA_SSL_KEYFILE=./certs/service.key
VALKEY_URI=rediss://default:password@valkey-host:port
```

Place your Kafka SSL certificates in `backend/certs/`.

### 4. Run

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PG_URI` | PostgreSQL async connection URI | (required) |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka bootstrap servers | (required) |
| `KAFKA_SSL_CAFILE` | Path to Kafka CA certificate | `./certs/ca.pem` |
| `KAFKA_SSL_CERTFILE` | Path to Kafka service certificate | `./certs/service.cert` |
| `KAFKA_SSL_KEYFILE` | Path to Kafka service key | `./certs/service.key` |
| `VALKEY_URI` | Valkey connection URI | (required) |
| `USGS_POLL_INTERVAL_SECONDS` | How often to poll USGS (seconds) | `60` |
| `LOG_LEVEL` | Logging level | `info` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/earthquakes` | List earthquakes (query: `hours`, `min_mag`, `max_mag`, `limit`, `offset`) |
| GET | `/api/earthquakes/bbox` | Earthquakes in map bounding box |
| GET | `/api/earthquakes/{id}` | Single earthquake detail |
| GET | `/api/stats` | Aggregated statistics |
| GET | `/api/health` | Health check for all 3 services |
| WS | `/ws/live` | WebSocket for real-time updates |

## Tech Stack

- **Backend**: Python, FastAPI, aiokafka, SQLAlchemy (async), redis-py
- **Frontend**: Vanilla JS, Leaflet.js, Chart.js
- **Data Source**: [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/)
- **Infrastructure**: Aiven Free Tier (Kafka, PostgreSQL, Valkey)

## License

MIT
