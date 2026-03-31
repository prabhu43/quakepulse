FROM python:3.11-slim

WORKDIR /app/backend

# Install dependencies first (layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/app/ ./app/

# Copy frontend (served by FastAPI from ../frontend relative to backend/)
COPY frontend/ /app/frontend/

# Kafka SSL certs are mounted at runtime via a volume
ENV KAFKA_SSL_CAFILE=./certs/ca.pem
ENV KAFKA_SSL_CERTFILE=./certs/service.cert
ENV KAFKA_SSL_KEYFILE=./certs/service.key

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
