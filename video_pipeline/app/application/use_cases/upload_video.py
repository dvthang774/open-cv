from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.application.interfaces.event_bus import EventBus
from app.application.interfaces.storage import Storage
from app.config import Settings
from app.domain.repositories.video_repo import VideoRepo


class UploadVideo:
    def __init__(self, *, repo: VideoRepo, storage: Storage, bus: EventBus, settings: Settings):
        self.repo = repo
        self.storage = storage
        self.bus = bus
        self.settings = settings

    def create_video_id(self) -> str:
        return f"v_{uuid.uuid4().hex}"

    def raw_key(self, video_id: str) -> str:
        return f"raw/{video_id}.mp4"

    async def emit_uploaded(self, *, video_id: str, key: str, checksum: str | None) -> None:
        event = {
            "event_id": str(uuid.uuid4()),
            "video_id": video_id,
            "type": "VIDEO_UPLOADED",
            "path": f"s3://{self.settings.s3_bucket}/{key}",
            "status": "UPLOADED",
            "checksum": checksum,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.bus.publish(topic="video.raw.uploaded", key=video_id, event=event)

