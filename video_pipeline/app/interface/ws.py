from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class WsHub:
    """
    POC in-memory hub keyed by video_id.
    In production: Redis/pubsub + auth + fanout.
    """

    def __init__(self) -> None:
        self._by_video: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, *, video_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._by_video[video_id].add(ws)

    async def disconnect(self, *, video_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._by_video[video_id].discard(ws)
            if not self._by_video[video_id]:
                self._by_video.pop(video_id, None)

    async def broadcast(self, *, video_id: str, message: dict) -> None:
        async with self._lock:
            targets = list(self._by_video.get(video_id, set()))
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                await self.disconnect(video_id=video_id, ws=ws)

