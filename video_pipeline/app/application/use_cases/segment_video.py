from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone

from app.application.interfaces.event_bus import EventBus
from app.application.interfaces.segmenter import Segmenter
from app.application.interfaces.storage import Storage
from app.config import Settings
from app.domain.entities.segment import Segment
from app.domain.repositories.video_repo import VideoRepo


class SegmentVideo:
    def __init__(
        self,
        *,
        repo: VideoRepo,
        storage: Storage,
        segmenter: Segmenter,
        bus: EventBus,
        settings: Settings,
    ):
        self.repo = repo
        self.storage = storage
        self.segmenter = segmenter
        self.bus = bus
        self.settings = settings

    async def run(self, *, event: dict) -> dict:
        video_id = event["video_id"]
        raw_key = f"raw/{video_id}.mp4"

        # Entity-level idempotency:
        # if segments already exist for this video, do not re-run ffmpeg.
        existing = self.repo.list_segments(video_id)
        if existing:
            segment_events: list[dict] = []
            for s in existing:
                duration = max(0.0, float(s.end_time) - float(s.start_time))
                segment_events.append(
                    {
                        "segment_id": s.segment_id,
                        "start_time": float(s.start_time),
                        "end_time": float(s.end_time),
                        "duration": duration,
                        "file_path": s.path,
                        # Backward compatible aliases (migration window)
                        "id": s.segment_id,
                        "start": float(s.start_time),
                        "end": float(s.end_time),
                        "path": s.path,
                    }
                )

            self.repo.set_status(video_id, "SEGMENTED")
            await self.bus.publish(
                topic="video.status",
                key=video_id,
                event={
                    "video_id": video_id,
                    "status": "SEGMENTED",
                    "progress": 70,
                    "message": "Segmentation already completed (idempotent skip)",
                },
            )
            out_event = {
                "event_id": str(uuid.uuid4()),
                "video_id": video_id,
                "type": "VIDEO_SEGMENTED",
                "segments": segment_events,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await self.bus.publish(topic="video.segment.completed", key=video_id, event=out_event)
            return out_event

        workdir = f"/tmp/vp_{video_id}"
        os.makedirs(workdir, exist_ok=True)
        local_raw = os.path.join(workdir, "input.mp4")
        out_dir = os.path.join(workdir, "segments")
        os.makedirs(out_dir, exist_ok=True)

        self.repo.set_status(video_id, "SEGMENTING")
        await self.bus.publish(
            topic="video.status",
            key=video_id,
            event={"video_id": video_id, "status": "SEGMENTING", "progress": 10, "message": "Starting segmentation"},
        )

        self.storage.download_to_file(key=raw_key, local_path=local_raw)

        produced = self.segmenter.segment(
            input_path=local_raw,
            output_dir=out_dir,
            segment_seconds=self.settings.segment_seconds,
        )

        segments: list[Segment] = []
        segment_events: list[dict] = []
        total = max(len(produced), 1)
        for idx, item in enumerate(produced, start=1):
            segment_id = item.get("segment_id") or f"s{idx:04d}"
            seg_key = f"segments/{video_id}/{segment_id}.mp4"
            self.storage.upload_file(local_path=item["local_path"], key=seg_key, content_type="video/mp4")
            start_time = float(item["start_time"])
            end_time = float(item["end_time"])
            duration = max(0.0, end_time - start_time)
            if duration <= 0:
                await self.bus.publish(
                    topic="video.status",
                    key=video_id,
                    event={
                        "video_id": video_id,
                        "status": "SEGMENTING",
                        "progress": 10 + int((idx / total) * 60),
                        "message": f"Skipped invalid segment {segment_id} (duration<=0)",
                    },
                )
                continue

            seg = Segment(
                segment_id=segment_id,
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
                path=f"s3://{self.settings.s3_bucket}/{seg_key}",
            )
            segments.append(seg)
            segment_events.append(
                {
                    "segment_id": segment_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "file_path": seg.path,
                    # Backward compatible aliases (migration window)
                    "id": segment_id,
                    "path": seg.path,
                    "start": start_time,
                    "end": end_time,
                }
            )
            await self.bus.publish(
                topic="video.status",
                key=video_id,
                event={
                    "video_id": video_id,
                    "status": "SEGMENTING",
                    "progress": 10 + int((idx / total) * 60),
                    "message": f"Segmented {idx}/{total}",
                },
            )

        self.repo.upsert_segments(segments)
        self.repo.set_status(video_id, "SEGMENTED")
        await self.bus.publish(
            topic="video.status",
            key=video_id,
            event={"video_id": video_id, "status": "SEGMENTED", "progress": 70, "message": "Segmentation done"},
        )

        out_event = {
            "event_id": str(uuid.uuid4()),
            "video_id": video_id,
            "type": "VIDEO_SEGMENTED",
            "segments": segment_events,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.bus.publish(topic="video.segment.completed", key=video_id, event=out_event)

        shutil.rmtree(workdir, ignore_errors=True)
        return out_event

