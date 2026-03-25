import os
import ssl
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    pg_uri: str

    # Kafka
    kafka_bootstrap_servers: str
    kafka_ssl_cafile: str = "./certs/ca.pem"
    kafka_ssl_certfile: str = "./certs/service.cert"
    kafka_ssl_keyfile: str = "./certs/service.key"

    # Valkey
    valkey_uri: str

    # App
    usgs_poll_interval_seconds: int = 60
    log_level: str = "info"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def kafka_ssl_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=self.kafka_ssl_cafile,
        )
        context.load_cert_chain(
            certfile=self.kafka_ssl_certfile,
            keyfile=self.kafka_ssl_keyfile,
        )
        return context


settings = Settings()
