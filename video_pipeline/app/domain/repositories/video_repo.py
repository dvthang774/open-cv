from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.segment import Segment
from app.domain.entities.video import Video


class VideoRepo(ABC):
    @abstractmethod
    def ensure_schema(self) -> None: ...

    @abstractmethod
    def create_video(self, video_id: str, raw_path: str) -> Video: ...

    @abstractmethod
    def get_video(self, video_id: str) -> Video | None: ...

    @abstractmethod
    def set_status(self, video_id: str, status: str) -> None: ...

    @abstractmethod
    def transition_status(self, *, video_id: str, from_status: str, to_status: str) -> bool:
        """
        Atomic transition. Returns True if updated; False if current status != from_status.
        """

    @abstractmethod
    def set_user_id(self, *, video_id: str, user_id: str) -> None: ...

    @abstractmethod
    def set_checksum(self, *, video_id: str, checksum: str | None) -> None: ...

    @abstractmethod
    def upsert_segments(self, segments: list[Segment]) -> None: ...

    @abstractmethod
    def list_segments(self, video_id: str) -> list[Segment]: ...

    @abstractmethod
    def insert_tags(
        self, *, video_id: str, segment_id: str, tags: list[tuple[str, float]]
    ) -> None: ...

    @abstractmethod
    def list_tags(self, video_id: str) -> list[dict]: ...

    @abstractmethod
    def mark_event_processed(self, *, consumer: str, event_id: str) -> bool:
        """
        Returns True if marked now; False if it was already processed.
        """

