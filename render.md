# Deploying QuakePulse to Render

## Prerequisites

- GitHub repo with the latest code pushed
- Aiven services provisioned (PostgreSQL, Kafka, Valkey)
- Kafka SSL certificates downloaded from Aiven console

## Deploy Steps

### 1. Create the Service on Render

- Go to **https://dashboard.render.com** → **New** → **Web Service**
- Connect your GitHub repo (`quakepulse`)
- Render auto-detects the `Dockerfile` — accept the defaults
- Select **Free** plan

### 2. Set Environment Variables

In the Render dashboard under **Environment**, add these variables:

| Variable | Value | Description |
|----------|-------|-------------|
| `PG_URI` | `postgresql+asyncpg://...` | Aiven PostgreSQL connection URI |
| `KAFKA_BOOTSTRAP_SERVERS` | `quakepulse-kafka-...:17354` | Aiven Kafka bootstrap server |
| `VALKEY_URI` | `rediss://default:...` | Aiven Valkey connection URI |
| `KAFKA_CA_CERT` | *(full PEM content)* | Contents of `certs/ca.pem` |
| `KAFKA_SERVICE_CERT` | *(full PEM content)* | Contents of `certs/service.cert` |
| `KAFKA_SERVICE_KEY` | *(full PEM content)* | Contents of `certs/service.key` |

> **Note:** For the Kafka cert variables, open each cert file and paste the **entire contents** (including `-----BEGIN CERTIFICATE-----` / `-----END CERTIFICATE-----` lines) as the value.

### 3. Deploy

Click **Deploy** — Render builds the Docker image and starts the service.

Your app will be live at: `https://quakepulse-xxxx.onrender.com`

## How It Works

- **`start.sh`** runs at container startup — it writes the `KAFKA_CA_CERT`, `KAFKA_SERVICE_CERT`, and `KAFKA_SERVICE_KEY` env vars to files in `/app/backend/certs/`, then starts uvicorn on Render's `$PORT`.
- **`render.yaml`** is the Render blueprint that declares the service and required env vars.
- The **WebSocket URL** is dynamically derived from `window.location.host`, so it works on any domain automatically.

## Free Tier Limitations

- Service **sleeps after 15 minutes** of inactivity
- First request after sleep has a **~30s cold start**
- 512 MB RAM, shared CPU
- 750 free hours/month (enough for one service running 24/7)

## Local Development

The `docker-compose.yml` still works for local development — certs are mounted via volume as before:

```bash
docker compose up --build
```
