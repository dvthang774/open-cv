from __future__ import annotations

from abc import ABC, abstractmethod


class EventBus(ABC):
    @abstractmethod
    async def publish(self, *, topic: str, key: str, event: dict) -> None: ...

