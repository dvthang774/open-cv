from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from app.application.interfaces.event_bus import EventBus
from app.application.interfaces.storage import Storage
from app.config import Settings
from app.domain.repositories.video_repo import VideoRepo


class ProcessAI:
    """
    POC AI: stub tags per segment (replace with real models later).
    """

    TAG_POOL = ["person", "car", "text", "logo", "animal", "bicycle"]

    def __init__(self, *, repo: VideoRepo, storage: Storage, bus: EventBus, settings: Settings):
        self.repo = repo
        self.storage = storage
        self.bus = bus
        self.settings = settings

    async def run(self, *, event: dict) -> dict:
        video_id = event["video_id"]
        segments = event.get("segments", [])

        self.repo.set_status(video_id, "AI_PROCESSING")
        await self.bus.publish(
            topic="video.status",
            key=video_id,
            event={"video_id": video_id, "status": "AI_PROCESSING", "progress": 75, "message": "Starting AI"},
        )

        completed: list[dict] = []
        total = max(len(segments), 1)
        for seg in segments:
            segment_id = seg["id"]
            tags = random.sample(self.TAG_POOL, k=min(2, len(self.TAG_POOL)))
            scores = [round(random.uniform(0.7, 0.99), 2) for _ in tags]

            meta = {
                "video_id": video_id,
                "segment_id": segment_id,
                "tags": tags,
                "confidence": scores,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            meta_key = f"metadata/{video_id}/segments/{segment_id}.json"
            self.storage.put_json(key=meta_key, data=meta)

            self.repo.insert_tags(
                video_id=video_id,
                segment_id=segment_id,
                tags=list(zip(tags, scores, strict=False)),
            )

            out = {
                "event_id": str(uuid.uuid4()),
                "video_id": video_id,
                "type": "SEGMENT_AI_COMPLETED",
                "segment_id": segment_id,
                "tags": tags,
                "confidence": scores,
                "created_at": meta["created_at"],
            }
            await self.bus.publish(topic="video.ai.completed", key=video_id, event=out)
            completed.append(out)
            await self.bus.publish(
                topic="video.status",
                key=video_id,
                event={
                    "video_id": video_id,
                    "status": "AI_PROCESSING",
                    "progress": 75 + int((len(completed) / total) * 20),
                    "message": f"AI processed {len(completed)}/{total}",
                },
            )

        self.repo.set_status(video_id, "DONE")
        final = {
            "event_id": str(uuid.uuid4()),
            "video_id": video_id,
            "status": "DONE",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "segments_processed": len(segments),
        }
        await self.bus.publish(
            topic="video.status",
            key=video_id,
            event={"video_id": video_id, "status": "DONE", "progress": 100, "message": "Completed"},
        )
        await self.bus.publish(topic="video.finalized", key=video_id, event=final)
        return {"final": final, "ai_events": completed}

