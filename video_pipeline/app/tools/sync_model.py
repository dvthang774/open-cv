from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class S3Conn:
    endpoint: str
    access_key: str
    secret_key: str
    region: str


def _s3_conn_from_env() -> S3Conn:
    endpoint = os.getenv("VP_S3_ENDPOINT", "").strip()
    access_key = os.getenv("VP_S3_ACCESS_KEY", "").strip()
    secret_key = os.getenv("VP_S3_SECRET_KEY", "").strip()
    region = os.getenv("VP_S3_REGION", "us-east-1").strip() or "us-east-1"
    if not endpoint or not access_key or not secret_key:
        raise RuntimeError(
            "Missing S3 env. Need VP_S3_ENDPOINT, VP_S3_ACCESS_KEY, VP_S3_SECRET_KEY (MinIO/S3 connection)."
        )
    return S3Conn(endpoint=endpoint, access_key=access_key, secret_key=secret_key, region=region)


def _client():
    import boto3  # local import keeps base import cheap

    c = _s3_conn_from_env()
    return boto3.client(
        "s3",
        endpoint_url=c.endpoint,
        aws_access_key_id=c.access_key,
        aws_secret_access_key=c.secret_key,
        region_name=c.region,
    )


def _meta_path(cache_dir: str, key: str) -> str:
    safe = key.replace("/", "__")
    return os.path.join(cache_dir, f".{safe}.meta.json")


def _load_cached_meta(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_cached_meta(path: str, meta: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, sort_keys=True, indent=2)
    os.replace(tmp, path)


def _normalize_etag(etag: str | None) -> str | None:
    if not etag:
        return None
    return etag.strip().strip('"')


def sync_model(*, bucket: str, key: str, cache_dir: str) -> str:
    """
    Ensures cache_dir/key exists and is up-to-date vs S3.
    Uses HeadObject to compare ETag and/or LastModified.
    Returns local cached model path.
    """
    os.makedirs(cache_dir, exist_ok=True)
    local_path = os.path.join(cache_dir, key)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    s3 = _client()
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as e:  # noqa: BLE001
        msg = (
            "Model not found on S3/MinIO. "
            f"Expected s3://{bucket}/{key}. "
            "Upload the model file to MinIO (bucket + key) and retry."
        )
        raise RuntimeError(msg) from e

    remote_etag = _normalize_etag(head.get("ETag"))
    remote_last_modified = head.get("LastModified")
    remote_last_modified_iso = (
        remote_last_modified.isoformat() if isinstance(remote_last_modified, datetime) else None
    )

    meta_path = _meta_path(cache_dir, key)
    cached_meta = _load_cached_meta(meta_path)
    cached_etag = cached_meta.get("etag")
    cached_last_modified = cached_meta.get("last_modified")

    has_local = os.path.exists(local_path) and os.path.getsize(local_path) > 0
    up_to_date = False

    if has_local and remote_etag and cached_etag:
        up_to_date = str(remote_etag) == str(cached_etag)
    elif has_local and remote_last_modified_iso and cached_last_modified:
        up_to_date = str(remote_last_modified_iso) == str(cached_last_modified)

    if not up_to_date:
        tmp = f"{local_path}.downloading"
        s3.download_file(bucket, key, tmp)
        os.replace(tmp, local_path)
        _write_cached_meta(
            meta_path,
            {
                "bucket": bucket,
                "key": key,
                "etag": remote_etag,
                "last_modified": remote_last_modified_iso,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            },
        )

    print(local_path, flush=True)
    return local_path


def main() -> None:
    p = argparse.ArgumentParser(description="Sync a model file from S3/MinIO into container cache.")
    p.add_argument("--bucket", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--cache-dir", required=True)
    args = p.parse_args()

    sync_model(bucket=args.bucket, key=args.key, cache_dir=args.cache_dir)


if __name__ == "__main__":
    main()

