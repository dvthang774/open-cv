from __future__ import annotations

import orjson
from aiokafka import AIOKafkaProducer

from app.application.interfaces.event_bus import EventBus


class KafkaBus(EventBus):
    def __init__(self, *, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer:
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            key_serializer=lambda k: k.encode("utf-8"),
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def publish(self, *, topic: str, key: str, event: dict) -> None:
        if not self._producer:
            await self.start()
        assert self._producer is not None
        await self._producer.send_and_wait(topic, key=key, value=event)

