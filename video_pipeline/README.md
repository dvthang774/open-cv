## video_pipeline (on-prem POC)

POC pipeline:

1) Client uploads video to MinIO via presigned multipart upload (through FastAPI control-plane).
2) FastAPI emits event to Kafka topic `video.raw.uploaded`.
3) Segment worker consumes, runs FFmpeg segmentation, uploads segments, writes DB, emits `video.segment.completed`.
4) AI worker consumes, creates per-segment JSON metadata + DB tags (stub), emits `video.finalized`.

### Quickstart

Requirements: Docker + Docker Compose.

```bash
cd video_pipeline
docker compose up --build
```

### Services

- FastAPI: `http://localhost:8000`
- MinIO: `http://localhost:9001` (console)
- Postgres: `localhost:5432`
- Kafka (Redpanda): `localhost:9092`

### API (POC)

- `POST /videos` → create `video_id`
- `POST /videos/{video_id}/multipart/init` → returns `upload_id`
- `POST /videos/{video_id}/multipart/part-url?upload_id=...&part_number=1` → presigned URL
- `POST /videos/{video_id}/multipart/complete` → completes multipart and emits Kafka event
- `GET /videos/{video_id}` → status + segments + tags

### Notes

- This is a POC scaffold focused on correctness and replayability:
  - idempotent consumers via `processed_events`
  - retry + DLQ topic `video.failed`
- For real production: add outbox pattern, schema registry, tracing, auth, rate limiting.

