#!/bin/sh
# Render deployment startup script
# Writes Kafka SSL certificates from environment variables to files,
# then starts uvicorn on the Render-assigned PORT.

set -e

CERT_DIR="/app/backend/certs"
mkdir -p "$CERT_DIR"

# If cert contents are provided as env vars, write them to files
if [ -n "$KAFKA_CA_CERT" ]; then
    echo "$KAFKA_CA_CERT" > "$CERT_DIR/ca.pem"
    export KAFKA_SSL_CAFILE="$CERT_DIR/ca.pem"
fi

if [ -n "$KAFKA_SERVICE_CERT" ]; then
    echo "$KAFKA_SERVICE_CERT" > "$CERT_DIR/service.cert"
    export KAFKA_SSL_CERTFILE="$CERT_DIR/service.cert"
fi

if [ -n "$KAFKA_SERVICE_KEY" ]; then
    echo "$KAFKA_SERVICE_KEY" > "$CERT_DIR/service.key"
    export KAFKA_SSL_KEYFILE="$CERT_DIR/service.key"
fi

# Use Render's PORT env var, default to 8000 for local dev
PORT="${PORT:-8000}"

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
