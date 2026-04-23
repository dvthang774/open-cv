from __future__ import annotations

import json

import boto3

from app.application.interfaces.storage import Storage
from app.config import settings


class S3Storage(Storage):
    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        region: str,
        bucket: str,
    ):
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._public_endpoint_url = public_endpoint_url
        self._public_client = (
            boto3.client(
                "s3",
                endpoint_url=public_endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            if public_endpoint_url
            else self._client
        )

    def ensure_bucket(self, bucket: str) -> None:
        buckets = [b["Name"] for b in self._client.list_buckets().get("Buckets", [])]
        if bucket in buckets:
            return
        self._client.create_bucket(Bucket=bucket)

    def presign_create_multipart(self, *, key: str, content_type: str | None) -> dict:
        params: dict = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        resp = self._client.create_multipart_upload(**params)
        return {"upload_id": resp["UploadId"], "key": key, "bucket": self.bucket}

    def presign_upload_part(
        self, *, key: str, upload_id: str, part_number: int, content_md5: str | None
    ) -> str:
        params: dict = {
            "Bucket": self.bucket,
            "Key": key,
            "UploadId": upload_id,
            "PartNumber": part_number,
        }
        if content_md5:
            params["ContentMD5"] = content_md5
        return self._public_client.generate_presigned_url(
            ClientMethod="upload_part",
            Params=params,
            ExpiresIn=settings.presign_expires_seconds,
            HttpMethod="PUT",
        )

    def complete_multipart(self, *, key: str, upload_id: str, parts: list[dict]) -> dict:
        resp = self._client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        return {"location": resp.get("Location"), "etag": resp.get("ETag")}

    def presign_get_object(self, *, key: str) -> str:
        return self._public_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=settings.presign_expires_seconds,
            HttpMethod="GET",
        )

    def exists(self, *, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def download_to_file(self, *, key: str, local_path: str) -> None:
        self._client.download_file(self.bucket, key, local_path)

    def upload_file(self, *, local_path: str, key: str, content_type: str | None = None) -> None:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        if extra:
            self._client.upload_file(local_path, self.bucket, key, ExtraArgs=extra)
        else:
            self._client.upload_file(local_path, self.bucket, key)

    def put_json(self, *, key: str, data: dict) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data).encode("utf-8"),
            ContentType="application/json",
        )

