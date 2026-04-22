from __future__ import annotations

from app.config import settings
from app.infrastructure.messaging.kafka_bus import KafkaBus
from app.infrastructure.persistence.postgres_repo import PostgresVideoRepo
from app.infrastructure.processing.ffmpeg_segmenter import FfmpegSegmenter
from app.infrastructure.storage.s3_storage import S3Storage


def build_repo() -> PostgresVideoRepo:
    repo = PostgresVideoRepo(dsn=settings.db_dsn)
    repo.ensure_schema()
    return repo


def build_storage() -> S3Storage:
    storage = S3Storage(
        endpoint_url=settings.s3_endpoint,
        public_endpoint_url=settings.public_s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        bucket=settings.s3_bucket,
    )
    storage.ensure_bucket(settings.s3_bucket)
    return storage


def build_bus() -> KafkaBus:
    return KafkaBus(bootstrap_servers=settings.kafka_bootstrap)


def build_segmenter() -> FfmpegSegmenter:
    return FfmpegSegmenter()

