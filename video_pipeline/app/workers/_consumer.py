from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer


async def run_consumer(
    *,
    bootstrap_servers: str,
    group_id: str,
    topic: str,
    dlq_topic: str,
    handler: Callable[[dict], Awaitable[None]],
    max_retries: int = 5,
) -> None:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: orjson.loads(v),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: orjson.dumps(v),
        key_serializer=lambda k: k.encode("utf-8"),
    )

    await consumer.start()
    await producer.start()
    try:
        async for msg in consumer:
            event = msg.value
            attempt = int(event.get("_attempt", 0))
            try:
                await handler(event)
                await consumer.commit()
            except Exception as e:  # noqa: BLE001
                if attempt + 1 < max_retries:
                    event["_attempt"] = attempt + 1
                    await asyncio.sleep(min(2**attempt, 10))
                    # re-publish to same topic for retry (POC)
                    await producer.send_and_wait(topic, key=msg.key or "", value=event)
                    await consumer.commit()
                else:
                    failed = {
                        "event_id": event.get("event_id"),
                        "video_id": event.get("video_id"),
                        "source_topic": topic,
                        "error": repr(e),
                        "event": event,
                    }
                    await producer.send_and_wait(dlq_topic, key=event.get("video_id", ""), value=failed)
                    await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()

