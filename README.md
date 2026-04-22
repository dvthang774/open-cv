# open-cv

On-prem **Video Processing Pipeline POC**:

Upload (multipart) → Kafka → Segment (FFmpeg) → AI (stub) → Metadata → Realtime UI

This repo contains a runnable mini-stack to demonstrate:
- **Non-blocking API** (upload control-plane only)
- **Backpressure + scaling** with Kafka/Redpanda + workers
- **Chunked multipart upload** with retry + validation
- **Realtime progress** via WebSocket
- **Hybrid metadata** (MinIO JSON + Postgres indexes)

---

## Tech stack
- **FastAPI** (API/control-plane + WebSocket fanout)
- **Streamlit** (POC UI)
- **MinIO** (S3-compatible object storage)
- **Redpanda** (Kafka-compatible broker)
- **Postgres** (state + indexes + idempotency)
- **Workers**
  - `segment-worker`: Python + FFmpeg (CPU)
  - `ai-worker`: Python (POC stub tags; replace with real models later)

---

## Quickstart (Docker Compose)

### Prerequisites
- Docker + Docker Compose

### Start the stack
```bash
cd video_pipeline
docker compose up --build
```

### URLs
- **Streamlit UI**: `http://localhost:8501`
- **FastAPI**: `http://localhost:8000`
- **MinIO Console**: `http://localhost:9001` (user/pass: `minioadmin` / `minioadmin`)

---

## Demo flow (what to click)
1) Open Streamlit UI at `http://localhost:8501`
2) Select a video file
3) Click **Start new upload**
4) Click **Upload & Complete (multipart)**
5) Watch **realtime stages** update (Upload → Segment worker → AI worker → Final)
6) After completion, you should see:
   - Segments list + preview
   - Tags table (POC stub)

---

## Where data goes
- **MinIO (object storage)**
  - Raw: `raw/{video_id}.mp4`
  - Segments: `processed/{video_id}/segments/*.mp4`
  - Metadata: `metadata/{video_id}/segments/*.json`
- **Postgres**
  - `videos`, `segments`, `tags`, `processed_events`

---

## Debugging (common checks)
- Worker logs:
```bash
cd video_pipeline
docker compose logs -f segment-worker
docker compose logs -f ai-worker
```

- API logs:
```bash
cd video_pipeline
docker compose logs -f api
```

- Postgres quick counts:
```bash
cd video_pipeline
docker compose exec -T postgres psql -U vp -d vp -c "select count(*) from videos;"
```

---

## Docs
See `video_pipeline/docs/`:
- `architecture.md`: current architecture diagram + flow
- `upload.md`: multipart retry + validation + checksums
- `database.md`: schema + field ownership
- `for-beginners.md`: beginner-friendly walkthrough
- `runbook.md`: operations notes (including cleanup tool)

For service-level details, also see `video_pipeline/README.md`.

