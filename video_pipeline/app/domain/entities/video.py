from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Video:
    video_id: str
    raw_path: str
    status: str
    checksum: str | None
    created_at: datetime
    updated_at: datetime

