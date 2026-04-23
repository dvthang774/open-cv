from __future__ import annotations

import asyncio
from typing import Any

from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
import orjson
from pydantic import BaseModel, Field

from app.application.use_cases.upload_video import UploadVideo
from app.config import settings
from app.interface.ws import WsHub
from app.wiring import build_bus, build_repo, build_storage


repo = build_repo()
storage = build_storage()
bus = build_bus()
upload_uc = UploadVideo(repo=repo, storage=storage, bus=bus, settings=settings)
ws_hub = WsHub()
_consumer_task: asyncio.Task | None = None


class CreateVideoResponse(BaseModel):
    video_id: str
    raw_key: str


class InitMultipartRequest(BaseModel):
    content_type: str | None = "video/mp4"
    file_size_bytes: int | None = None


class InitMultipartResponse(BaseModel):
    upload_id: str
    key: str
    bucket: str


class CompleteMultipartRequest(BaseModel):
    upload_id: str
    parts: list[dict] = Field(
        description="List of {'ETag': '...', 'PartNumber': 1} (ETag should include quotes if returned that way)"
    )
    checksum: str | None = None


app = FastAPI(title="video-pipeline POC")


@app.on_event("startup")
async def _startup() -> None:
    await bus.start()
    global _consumer_task
    _consumer_task = asyncio.create_task(_kafka_status_fanout())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _consumer_task
    if _consumer_task:
        _consumer_task.cancel()
    await bus.stop()


@app.post("/videos", response_model=CreateVideoResponse)
async def create_video(user_id: str | None = None) -> CreateVideoResponse:
    video_id = upload_uc.create_video_id()
    raw_key = upload_uc.raw_key(video_id)
    repo.create_video(video_id, raw_path=f"s3://{settings.s3_bucket}/{raw_key}")
    if user_id:
        repo.set_user_id(video_id=video_id, user_id=user_id)
    return CreateVideoResponse(video_id=video_id, raw_key=raw_key)


@app.post("/videos/{video_id}/multipart/init", response_model=InitMultipartResponse)
async def init_multipart(video_id: str, req: InitMultipartRequest) -> InitMultipartResponse:
    key = upload_uc.raw_key(video_id)
    if not repo.get_video(video_id):
        repo.create_video(video_id, raw_path=f"s3://{settings.s3_bucket}/{key}")
    if req.file_size_bytes is not None and req.file_size_bytes > settings.max_file_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {req.file_size_bytes} > max_file_bytes={settings.max_file_bytes}",
        )
    resp = storage.presign_create_multipart(key=key, content_type=req.content_type)
    return InitMultipartResponse(**resp)


@app.post("/videos/{video_id}/multipart/part-url")
async def presign_part(
    video_id: str,
    upload_id: str = Query(...),
    part_number: int = Query(..., ge=1, le=10000),
    content_md5: str | None = Query(None, description="Base64 MD5 to let S3/MinIO verify chunk"),
) -> dict[str, Any]:
    key = upload_uc.raw_key(video_id)
    url = storage.presign_upload_part(
        key=key, upload_id=upload_id, part_number=part_number, content_md5=content_md5
    )
    return {"url": url, "method": "PUT", "headers": {"Content-MD5": content_md5} if content_md5 else {}}

@app.get("/objects/presign-get")
async def presign_get(key: str = Query(..., description="Object key inside bucket, e.g. raw/v_x.mp4")) -> dict:
    return {"url": storage.presign_get_object(key=key)}


@app.post("/videos/{video_id}/multipart/complete")
async def complete_multipart(video_id: str, req: CompleteMultipartRequest) -> dict[str, Any]:
    key = upload_uc.raw_key(video_id)
    video = repo.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="video_id not found")

    if not req.parts:
        raise HTTPException(status_code=400, detail="parts is required")

    # Ensure parts are sorted by PartNumber
    req.parts.sort(key=lambda p: int(p.get("PartNumber", 0)))

    storage.complete_multipart(key=key, upload_id=req.upload_id, parts=req.parts)
    repo.set_status(video_id, "UPLOADED")
    repo.set_checksum(video_id=video_id, checksum=req.checksum)
    await upload_uc.emit_uploaded(video_id=video_id, key=key, checksum=req.checksum)
    await bus.publish(
        topic="video.status",
        key=video_id,
        event={"video_id": video_id, "status": "UPLOADED", "progress": 5, "message": "Upload completed"},
    )
    return {"status": "UPLOADED", "video_id": video_id, "key": key}


@app.get("/videos/{video_id}")
async def get_video(video_id: str) -> dict[str, Any]:
    video = repo.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="not found")
    segments = repo.list_segments(video_id)
    tags = repo.list_tags(video_id)
    seg_out: list[dict[str, Any]] = []
    for s in segments:
        start_time = float(s.start_time)
        end_time = float(s.end_time)
        seg_out.append(
            {
                "segment_id": s.segment_id,
                "start_time": start_time,
                "end_time": end_time,
                "duration": max(0.0, end_time - start_time),
                "file_path": s.path,
            }
        )
    return {
        "video_id": video.video_id,
        "raw_path": video.raw_path,
        "status": video.status,
        "created_at": video.created_at,
        "updated_at": video.updated_at,
        "segments": seg_out,
        "tags": tags,
    }


@app.websocket("/ws/{video_id}")
async def ws_video(video_id: str, websocket: WebSocket) -> None:
    await ws_hub.connect(video_id=video_id, ws=websocket)
    try:
        # POC: keep connection, ignore client messages
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_hub.disconnect(video_id=video_id, ws=websocket)


async def _kafka_status_fanout() -> None:
    consumer = AIOKafkaConsumer(
        "video.status",
        "video.finalized",
        "video.failed",
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="api-ws-fanout",
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda v: orjson.loads(v),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )
    await consumer.start()
    try:
        async for msg in consumer:
            event = msg.value
            video_id = event.get("video_id") or (msg.key.decode("utf-8") if msg.key else None)
            if video_id:
                await ws_hub.broadcast(video_id=video_id, message=event)
    finally:
        await consumer.stop()

