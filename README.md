# QuakePulse — Real-Time Earthquake Alert System

> A real-time earthquake monitoring dashboard that streams USGS earthquake data through **Aiven Kafka**, stores it in **Aiven PostgreSQL**, caches hot data in **Aiven Valkey**, and displays everything on a live interactive map with WebSocket-powered updates.

Built for the [Aiven Free Tier Competition](https://aiven.io/blog/the-aiven-free-tier-competition) `#AivenFreeTier`

![QuakePulse Dashboard](assets/dashboard.png)

---

## Table of Contents

- [Architecture](#architecture)
- [How Data Flows](#how-data-flows)
- [Aiven Services Used](#aiven-services-used)
- [Features](#features)
- [Screenshots](#screenshots)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [License](#license)

---

## Architecture

```mermaid
flowchart LR
    USGS["USGS GeoJSON API"]
    KP["Kafka Producer\n(polls every 60s)"]
    KAFKA["Aiven Kafka\nraw-quakes | significant-quakes | quake-alerts"]
    KC["Kafka Consumer"]
    PG["Aiven PostgreSQL\n(persistent storage)"]
    VK["Aiven Valkey\n(cache + pub/sub)"]
    API["FastAPI Backend"]
    WS["WebSocket"]
    FE["Browser\nLeaflet.js + Chart.js"]

    USGS -->|HTTP GET| KP
    KP -->|produce| KAFKA
    KAFKA -->|consume| KC
    KC -->|upsert| PG
    KC -->|cache + publish| VK
    PG --> API
    VK --> API
    VK -->|pub/sub| WS
    API -->|REST| FE
    WS -->|live events| FE
```

<details>
<summary>ASCII version (for terminals without Mermaid support)</summary>

```
USGS GeoJSON API --> [Kafka Producer] --> Aiven Kafka (3 topics)
  (polled every 60s)                          |
                                        [Kafka Consumer]
                                         |           |
                                   Aiven PostgreSQL  Aiven Valkey
                                   (history store)   (cache + pub/sub)
                                         |           |
                                      [FastAPI Backend]
                                              |
                                     [WebSocket to Browser]
                                              |
                                    [Leaflet.js Live Map]
```

</details>

---

## How Data Flows

```
 1. Poll        2. Produce         3. Consume           4. Push           5. Display
+--------+    +------------+    +---------------+    +------------+    +-----------+
|  USGS  |--->|   Kafka    |--->|   Consumer    |--->|   Valkey   |--->|  Browser  |
|  Feed  |    |   Topics   |    |               |    |   Pub/Sub  |    |   (WS)    |
+--------+    +------------+    |   +--------+  |    +------------+    +-----------+
                                |   |  DB    |  |
                                |   | Upsert |  |
                                +---+--------+--+
                                       |
                                   PostgreSQL
```

1. **Kafka Producer** polls the [USGS earthquake feed](https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson) every 60 seconds and deduplicates events by earthquake ID.
2. New earthquakes are produced to **three Kafka topics**:
   - `raw-quakes` — all earthquakes
   - `significant-quakes` — magnitude >= 4.5
   - `quake-alerts` — magnitude >= 6.0 or tsunami warning
3. **Kafka Consumer** reads from all topics and:
   - **Upserts** data into PostgreSQL (`ON CONFLICT DO UPDATE`) for persistent storage and analytics
   - **Caches** recent quakes in a Valkey sorted set (scored by timestamp, last 200 events)
   - **Publishes** live events to the Valkey `live-quakes` pub/sub channel
4. **WebSocket handler** subscribes to the Valkey pub/sub channel and fans out new events to all connected browsers in real time.
5. **Frontend** displays quakes on a Leaflet.js map with animated markers, color-coded by magnitude, plus a Chart.js analytics panel.

On first startup, the system seeds historical data from the USGS `all_day.geojson` feed so the dashboard is populated immediately.

---

## Aiven Services Used

| Service | Purpose | Free Tier Details |
|---------|---------|-------------------|
| **Apache Kafka** | Stream earthquake data via 3 topics (`raw-quakes`, `significant-quakes`, `quake-alerts`) | Up to 5 topics, 3-day retention |
| **PostgreSQL** | Persistent storage for earthquake history, analytics queries | Fully managed instance |
| **Valkey** | Hot cache (sorted sets, individual quake cache, stats cache) + pub/sub for real-time WebSocket push | In-memory data store |

All three services work together naturally — Kafka for reliable ingestion, PostgreSQL for durable analytics, and Valkey for sub-second caching and live event delivery.

---

## Features

- **Live interactive map** — dark-themed Leaflet map with color-coded circle markers sized by magnitude
- **Real-time streaming** — new quakes appear instantly via WebSocket, no page refresh needed
- **Pulse animations** — newly arriving earthquakes animate with a CSS pulse effect
- **Analytics dashboard** — magnitude distribution chart, hourly timeline, top active regions (Chart.js)
- **Filtering** — filter by time range (1h / 24h / 7d / 30d) and minimum magnitude slider
- **Earthquake list** — scrollable side panel; click any event to fly to its location on the map
- **Marker clustering** — uses Leaflet.markercluster to cleanly group markers when zoomed out
- **Day/night toggle** — switch between dark and light map tile layers
- **Health endpoint** — `/api/health` reports live status of all 3 Aiven service connections
- **Auto-reconnect** — WebSocket client reconnects with exponential backoff on disconnection

---

## Screenshots

| Live Map | Analytics Panel |
|----------|-----------------|
| ![Map View](assets/mapview.png) | ![Analytics](assets/analytics.png) |

---

## Prerequisites

- **Python 3.11+**
- **Git**
- An [Aiven account](https://console.aiven.io/signup) (free tier) with the following services provisioned:
  - Aiven for Apache Kafka
  - Aiven for PostgreSQL
  - Aiven for Valkey

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/quakepulse.git
cd quakepulse
```

### 2. Create a Python virtual environment

```bash
cd backend
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Provision Aiven services

1. Sign up at [console.aiven.io](https://console.aiven.io/signup)
2. Create a **free-tier PostgreSQL** instance
   - Note the connection URI from the service overview page
3. Create a **free-tier Kafka** instance
   - Go to **Topics** and create three topics:
     - `raw-quakes`
     - `significant-quakes`
     - `quake-alerts`
   - Go to the **Overview** tab and download the **CA certificate**, **Service certificate**, and **Service key**
4. Create a **free-tier Valkey** instance
   - Note the connection URI (starts with `rediss://`)

### 4. Set up SSL certificates

Place the downloaded Kafka SSL files in the `backend/certs/` directory:

```
backend/certs/
  ca.pem           # CA certificate
  service.cert     # Service certificate
  service.key      # Service key
```

### 5. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your Aiven connection details:

```env
# Aiven PostgreSQL
PG_URI=postgresql+asyncpg://user:password@host:port/defaultdb?ssl=require

# Aiven Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka-host:port
KAFKA_SSL_CAFILE=./certs/ca.pem
KAFKA_SSL_CERTFILE=./certs/service.cert
KAFKA_SSL_KEYFILE=./certs/service.key

# Aiven Valkey
VALKEY_URI=rediss://default:password@valkey-host:port

# App settings (optional)
USGS_POLL_INTERVAL_SECONDS=60
LOG_LEVEL=info
```

> **Security note:** Never commit `.env` or certificate files. Both are listed in `.gitignore`.

### 6. Run the application

**Option A: Run directly with uvicorn**

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Option B: Run with Docker Compose**

```bash
docker compose up --build
```

To run in the background:

```bash
docker compose up --build -d
docker compose logs -f   # follow logs
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.

On startup the app will:
1. Initialize connections to PostgreSQL, Kafka, and Valkey
2. Seed historical data from the USGS `all_day.geojson` feed
3. Begin polling USGS every 60 seconds for new earthquakes
4. Start consuming Kafka messages and pushing updates via WebSocket

---

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `PG_URI` | PostgreSQL async connection URI (`postgresql+asyncpg://` scheme with `?ssl=require`) | Yes | — |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka bootstrap server `host:port` | Yes | — |
| `KAFKA_SSL_CAFILE` | Path to Kafka CA certificate | No | `./certs/ca.pem` |
| `KAFKA_SSL_CERTFILE` | Path to Kafka service certificate | No | `./certs/service.cert` |
| `KAFKA_SSL_KEYFILE` | Path to Kafka service key | No | `./certs/service.key` |
| `VALKEY_URI` | Valkey connection URI (use `rediss://` for TLS) | Yes | — |
| `USGS_POLL_INTERVAL_SECONDS` | How often to poll the USGS feed (seconds) | No | `60` |
| `LOG_LEVEL` | Logging level (`debug`, `info`, `warning`, `error`) | No | `info` |

---

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/earthquakes` | List earthquakes. Query params: `hours` (1-720), `min_mag`, `max_mag`, `limit`, `offset` |
| `GET` | `/api/earthquakes/bbox` | Earthquakes within a map bounding box. Params: `north`, `south`, `east`, `west`, `hours`, `limit` |
| `GET` | `/api/earthquakes/{id}` | Single earthquake detail (Valkey cache with PostgreSQL fallback) |
| `GET` | `/api/stats` | Aggregated statistics: total count, avg/max magnitude, distribution, hourly timeline, top regions |
| `GET` | `/api/health` | Health check — returns status of PostgreSQL, Kafka, and Valkey connections |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `WS /ws/live` | Real-time earthquake feed. On connect: receives last 10 cached quakes. Then streams new events as they arrive. |

### Example Requests

```bash
# List earthquakes from the past 24 hours with magnitude >= 2.5
curl "http://localhost:8000/api/earthquakes?hours=24&min_mag=2.5"

# Get earthquakes within a bounding box (California)
curl "http://localhost:8000/api/earthquakes/bbox?north=42&south=32&east=-114&west=-125&hours=168"

# Get aggregated statistics
curl "http://localhost:8000/api/stats"

# Health check
curl "http://localhost:8000/api/health"
# Response: {"status":"ok","services":{"postgresql":true,"kafka":true,"valkey":true}}
```

---

## Project Structure

```
quakepulse/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app with lifespan (startup/shutdown)
│   │   ├── config.py            # Pydantic Settings — all Aiven connection config
│   │   ├── models.py            # SQLAlchemy ORM model + Pydantic response schemas
│   │   ├── database.py          # Async SQLAlchemy engine & session factory
│   │   ├── kafka_producer.py    # USGS polling -> Kafka producer with deduplication
│   │   ├── kafka_consumer.py    # Kafka consumer -> PostgreSQL upsert + Valkey cache
│   │   ├── cache.py             # Valkey client (sorted sets, pub/sub, stats cache)
│   │   └── routes/
│   │       ├── earthquakes.py   # REST API endpoints + health check
│   │       └── websocket.py     # WebSocket endpoint with Valkey pub/sub subscription
│   ├── certs/                   # Kafka SSL certificates (not committed)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html               # Single-page app shell
│   ├── css/
│   │   └── style.css            # Dark theme, responsive layout, pulse animations
│   └── js/
│       ├── app.js               # App initialization, filter controls, event wiring
│       ├── map.js               # Leaflet map, markers, clustering, popups
│       ├── websocket.js         # WebSocket client with auto-reconnect
│       └── charts.js            # Chart.js analytics (magnitude dist, timeline)
├── plan.md                      # Detailed build plan
└── README.md
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11+, FastAPI, uvicorn, aiokafka, SQLAlchemy (async), redis-py |
| **Frontend** | Vanilla JavaScript, Leaflet.js, Leaflet.markercluster, Chart.js |
| **Data Source** | [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/) — GeoJSON feeds |
| **Streaming** | Aiven for Apache Kafka (3 topics, SSL/TLS) |
| **Database** | Aiven for PostgreSQL (async, SSL) |
| **Cache / Pub-Sub** | Aiven for Valkey (sorted sets, key-value cache, pub/sub) |

---

## License

MIT
