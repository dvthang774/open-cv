from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    segment_id: str
    video_id: str
    start_time: float
    end_time: float
    path: str

