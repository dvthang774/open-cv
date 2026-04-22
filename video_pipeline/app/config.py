from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app import env


# Load repo-level .env:
# this file lives in `video_pipeline/app/config.py`, while `.env` is at repo root `../.env`.
env.load_env_file(Path(__file__).resolve().parent.parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    env: str

    kafka_bootstrap: str
    db_dsn: str

    s3_endpoint: str
    public_s3_endpoint: str | None
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str

    segment_seconds: int

    # Upload safety limits (POC)
    max_file_bytes: int
    presign_expires_seconds: int
    upload_part_timeout_seconds: int
    max_parallel_uploads: int

    # Ops: cleanup/retention (POC; used by cleanup tool)
    abort_incomplete_multipart_after_hours: int
    retention_raw_days: int
    retention_processed_days: int
    retention_metadata_days: int


settings = Settings(
    env=env.get_env("VP_ENV", "dev"),
    kafka_bootstrap=env.get_env("VP_KAFKA_BOOTSTRAP", "localhost:9092"),
    db_dsn=env.get_env("VP_DB_DSN", "postgresql://vp:vp@localhost:5432/vp"),
    s3_endpoint=env.get_env("VP_S3_ENDPOINT", "http://localhost:9000"),
    public_s3_endpoint=env.get_env("VP_PUBLIC_S3_ENDPOINT", None),
    s3_access_key=env.get_env("VP_S3_ACCESS_KEY", "minioadmin"),
    s3_secret_key=env.get_env("VP_S3_SECRET_KEY", "minioadmin"),
    s3_bucket=env.get_env("VP_S3_BUCKET", "videos"),
    s3_region=env.get_env("VP_S3_REGION", "us-east-1"),
    segment_seconds=env.get_env("VP_SEGMENT_SECONDS", 10, int),
    max_file_bytes=env.get_env("VP_MAX_FILE_BYTES", 2_000_000_000, int),
    presign_expires_seconds=env.get_env("VP_PRESIGN_EXPIRES_SECONDS", 3600, int),
    upload_part_timeout_seconds=env.get_env("VP_UPLOAD_PART_TIMEOUT_SECONDS", 300, int),
    max_parallel_uploads=env.get_env("VP_MAX_PARALLEL_UPLOADS", 8, int),
    abort_incomplete_multipart_after_hours=env.get_env(
        "VP_ABORT_INCOMPLETE_MULTIPART_AFTER_HOURS", 24, int
    ),
    retention_raw_days=env.get_env("VP_RETENTION_RAW_DAYS", 30, int),
    retention_processed_days=env.get_env("VP_RETENTION_PROCESSED_DAYS", 30, int),
    retention_metadata_days=env.get_env("VP_RETENTION_METADATA_DAYS", 30, int),
)

