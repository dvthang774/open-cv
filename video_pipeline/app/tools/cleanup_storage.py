from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import boto3

from app.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def abort_incomplete_multipart(*, older_than_hours: int) -> int:
    c = _client()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    aborted = 0
    key_marker = None
    upload_id_marker = None
    while True:
        resp = c.list_multipart_uploads(
            Bucket=settings.s3_bucket,
            **({} if not key_marker else {"KeyMarker": key_marker, "UploadIdMarker": upload_id_marker}),
        )
        for up in resp.get("Uploads", []):
            initiated = up["Initiated"]
            if initiated.tzinfo is None:
                initiated = initiated.replace(tzinfo=timezone.utc)
            if initiated < cutoff:
                c.abort_multipart_upload(
                    Bucket=settings.s3_bucket,
                    Key=up["Key"],
                    UploadId=up["UploadId"],
                )
                aborted += 1
        if not resp.get("IsTruncated"):
            break
        key_marker = resp.get("NextKeyMarker")
        upload_id_marker = resp.get("NextUploadIdMarker")
    return aborted


def delete_older_than(*, prefix: str, older_than_days: int) -> int:
    c = _client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    deleted = 0
    token = None
    while True:
        resp = c.list_objects_v2(
            Bucket=settings.s3_bucket,
            Prefix=prefix,
            **({} if not token else {"ContinuationToken": token}),
        )
        for obj in resp.get("Contents", []) or []:
            lm = obj["LastModified"]
            if lm.tzinfo is None:
                lm = lm.replace(tzinfo=timezone.utc)
            if lm < cutoff:
                c.delete_object(Bucket=settings.s3_bucket, Key=obj["Key"])
                deleted += 1
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return deleted


def main() -> None:
    p = argparse.ArgumentParser(description="POC cleanup: abort multipart + retention deletes")
    p.add_argument("--abort-hours", type=int, default=settings.abort_incomplete_multipart_after_hours)
    p.add_argument("--retention-raw-days", type=int, default=settings.retention_raw_days)
    p.add_argument("--retention-processed-days", type=int, default=settings.retention_processed_days)
    p.add_argument("--retention-metadata-days", type=int, default=settings.retention_metadata_days)
    args = p.parse_args()

    aborted = abort_incomplete_multipart(older_than_hours=args.abort_hours)
    deleted_raw = delete_older_than(prefix="raw/", older_than_days=args.retention_raw_days)
    deleted_processed = delete_older_than(prefix="processed/", older_than_days=args.retention_processed_days)
    deleted_metadata = delete_older_than(prefix="metadata/", older_than_days=args.retention_metadata_days)

    print(
        {
            "aborted_incomplete_multipart": aborted,
            "deleted_raw": deleted_raw,
            "deleted_processed": deleted_processed,
            "deleted_metadata": deleted_metadata,
        }
    )


if __name__ == "__main__":
    main()

