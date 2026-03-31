FROM python:3.11-slim

WORKDIR /app/backend

# Install dependencies first (layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/app/ ./app/

# Copy frontend (served by FastAPI from ../frontend relative to backend/)
COPY frontend/ /app/frontend/

# Default cert paths (overridden by start.sh when using env-var certs)
ENV KAFKA_SSL_CAFILE=./certs/ca.pem
ENV KAFKA_SSL_CERTFILE=./certs/service.cert
ENV KAFKA_SSL_KEYFILE=./certs/service.key

# Copy startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
