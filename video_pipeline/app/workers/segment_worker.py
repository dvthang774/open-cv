from __future__ import annotations

import asyncio

from app.application.use_cases.segment_video import SegmentVideo
from app.config import settings
from app.infrastructure.messaging.kafka_bus import KafkaBus
from app.wiring import build_repo, build_segmenter, build_storage
from app.workers._consumer import run_consumer


async def main() -> None:
    repo = build_repo()
    storage = build_storage()
    segmenter = build_segmenter()
    bus = KafkaBus(bootstrap_servers=settings.kafka_bootstrap)
    await bus.start()

    uc = SegmentVideo(repo=repo, storage=storage, segmenter=segmenter, bus=bus, settings=settings)

    async def handler(event: dict) -> None:
        event_id = event.get("event_id")
        if event_id and not repo.mark_event_processed(consumer="segment_worker", event_id=event_id):
            return
        await uc.run(event=event)

    await run_consumer(
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="segment-worker",
        topic="video.raw.uploaded",
        dlq_topic="video.failed",
        handler=handler,
    )


if __name__ == "__main__":
    asyncio.run(main())

