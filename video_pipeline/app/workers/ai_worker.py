from __future__ import annotations

import asyncio

from app.application.use_cases.process_ai import ProcessAI
from app.config import settings
from app.infrastructure.messaging.kafka_bus import KafkaBus
from app.wiring import build_repo, build_storage
from app.workers._consumer import run_consumer


async def main() -> None:
    repo = build_repo()
    storage = build_storage()
    bus = KafkaBus(bootstrap_servers=settings.kafka_bootstrap)
    await bus.start()

    uc = ProcessAI(repo=repo, storage=storage, bus=bus, settings=settings)

    async def handler(event: dict) -> None:
        event_id = event.get("event_id")
        if event_id and not repo.mark_event_processed(consumer="ai_worker", event_id=event_id):
            return
        await uc.run(event=event)

    await run_consumer(
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="ai-worker",
        topic="video.segment.completed",
        dlq_topic="video.failed",
        handler=handler,
    )


if __name__ == "__main__":
    asyncio.run(main())

