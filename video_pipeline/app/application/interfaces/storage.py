from __future__ import annotations

from abc import ABC, abstractmethod


class Storage(ABC):
    @abstractmethod
    def ensure_bucket(self, bucket: str) -> None: ...

    @abstractmethod
    def presign_create_multipart(self, *, key: str, content_type: str | None) -> dict: ...

    @abstractmethod
    def presign_upload_part(
        self, *, key: str, upload_id: str, part_number: int, content_md5: str | None
    ) -> str: ...

    @abstractmethod
    def complete_multipart(self, *, key: str, upload_id: str, parts: list[dict]) -> dict: ...

    @abstractmethod
    def presign_get_object(self, *, key: str) -> str: ...

    @abstractmethod
    def exists(self, *, key: str) -> bool: ...

    @abstractmethod
    def download_to_file(self, *, key: str, local_path: str) -> None: ...

    @abstractmethod
    def upload_file(self, *, local_path: str, key: str, content_type: str | None = None) -> None: ...

    @abstractmethod
    def put_json(self, *, key: str, data: dict) -> None: ...

