## For beginners: Video → Segments → AI tags (POC flow)

---

### System goal (one sentence)
You upload a video; the system automatically **splits it into small segments**, runs AI on each segment, stores the outputs, and **streams realtime progress** back to the UI.

Pipeline:

Upload → Kafka → Segment (FFmpeg) → AI → Metadata → Realtime Notify

### DFD (Data Flow Diagram) — Mermaid

```mermaid
flowchart LR
  %% External actors
  U[User/Client] -->|Upload via UI| UI[Streamlit UI]

  %% Control plane
  UI -->|POST /videos| API[FastAPI API]
  UI -->|POST /multipart/init| API
  UI -->|POST /multipart/part-url| API

  %% Data plane (bytes)
  UI -->|PUT upload_part (chunks)| S3[(MinIO / S3 bucket)]
  API -->|CompleteMultipartUpload| S3

  %% Raw video stored
  S3 -->|Object raw/{video_id}.mp4| S3

  %% Events backbone
  API -->|publish video.raw.uploaded| K[(Kafka/Redpanda)]
  API -->|publish video.status (UPLOADED)| K

  %% Segment processing
  K -->|consume video.raw.uploaded| SW[segment-worker (FFmpeg)]
  SW -->|GET raw/{video_id}.mp4| S3
  SW -->|PUT processed/{video_id}/segments/*.mp4| S3
  SW -->|INSERT segments + UPDATE videos.status| DB[(Postgres)]
  SW -->|publish video.segment.completed| K
  SW -->|publish video.status (SEGMENTING/SEGMENTED)| K

  %% AI processing
  K -->|consume video.segment.completed| AW[ai-worker (AI)]
  AW -->|PUT metadata/{video_id}/segments/*.json| S3
  AW -->|INSERT tags + UPDATE videos.status| DB
  AW -->|publish video.ai.completed| K
  AW -->|publish video.finalized + video.status (DONE)| K

  %% Realtime notify
  K -->|consume video.status/finalized/failed| API
  API -->|WS /ws/{video_id}| UI

  %% Query results
  UI -->|GET /videos/{video_id}| API
  API -->|SELECT videos/segments/tags| DB
```

---

### Why segment the video before running AI?
If you run AI on a long continuous recording (10–20 minutes) as a single job, it tends to be:
- Slow and hard to scale
- Fragile (power loss, crashes, resource limits) → you may need to restart from the beginning

Splitting into segments enables:
- **Parallelism**: multiple workers can process different segments at the same time
- **Small retries**: if one segment fails, you retry only that segment
- **Clear progress**: you can track how far the pipeline has progressed

---

### What does each component do in this POC?

- **Streamlit UI** (`http://localhost:8501`)
  - Select a video file
  - Upload via multipart (chunked)
  - View progress and results (segments, tags)

- **FastAPI** (`http://localhost:8000`)
  - Control-plane: create `video_id`, issue presigned upload URLs, complete uploads
  - Publish Kafka events to trigger workers
  - Consume progress events and push them to WebSocket clients

- **MinIO** (S3-compatible) (`http://localhost:9001`)
  - Stores raw videos, segments, and JSON metadata

- **Kafka (Redpanda)**
  - Backbone: event log + buffer/backpressure, enables horizontal scaling

- **Postgres**
  - Stores video state and indexes (segments, tags) for fast querying

- **segment-worker (FFmpeg)**
  - Splits the raw video into segments (CPU-bound)

- **ai-worker**
  - Runs AI per segment (POC uses stub/random tags; replace with real models later)

---

### Tech stack workflow (how you run and iterate)

This POC is designed to be run locally/on-prem using Docker Compose. Think of it as a small “mini production” stack.

#### 1) What runs as containers
- **`api`**: FastAPI service (control-plane + WebSocket fanout)
- **`ui`**: Streamlit web UI
- **`segment-worker`**: FFmpeg segmentation worker
- **`ai-worker`**: AI/tagging worker (stub in POC)
- **`minio`**: S3-compatible object storage
- **`redpanda`**: Kafka-compatible broker (Redpanda)
- **`postgres`**: relational DB for state + indexes

#### 2) Day-to-day workflow (developer loop)
1) Start everything:
   - `docker compose up --build`
2) Open the UI:
   - `http://localhost:8501`
3) Upload a video in the UI:
   - UI uploads chunks → MinIO
   - API completes multipart → publishes Kafka event
4) Observe processing:
   - UI shows realtime progress via WebSocket (`video.status`)
   - Segment/AI workers write outputs to MinIO and indexes to Postgres
5) Debug when something looks wrong:
   - Check worker logs (`docker compose logs -f segment-worker`, `ai-worker`)
   - Check MinIO console (`http://localhost:9001`) for objects under `raw/`, `processed/`, `metadata/`
   - Query Postgres tables (`videos`, `segments`, `tags`)

#### 3) Where to change code
- **API behavior**: `app/interface/api.py` + `app/application/use_cases/*`
- **Segmentation logic**: `app/infrastructure/processing/ffmpeg_segmenter.py`
- **AI logic**: `app/application/use_cases/process_ai.py` (replace stub with a real model)
- **UI**: `ui/app.py`

---

### Pros / Cons and why this architecture

#### 1) Presigned multipart upload (chunking) vs uploading through the API
- **Pros**
  - The API does not become a bandwidth/CPU/RAM bottleneck because it does not proxy video bytes
  - Large uploads are more reliable; you **retry by part** (re-upload only the failed part)
  - Parallel uploads can reduce total upload time
- **Cons**
  - More moving parts: `upload_id`, presigned URLs, `ETag` list, completion call
  - Presigned URL host must match where the uploader runs (`minio:9000` inside Docker vs `localhost:9000` from your machine)
- **Why**
  - This is a common production pattern to keep the API stable under heavy uploads.

#### 2) Kafka (queue/event backbone) vs only S3/MinIO triggers
- **Pros**
  - Kafka stores backlog (buffer/backpressure): if workers are slow, messages aren’t lost
  - Easy horizontal scaling: add worker instances to the same consumer group
  - Replayable: useful for debugging or recomputing outputs
- **Cons**
  - Additional infrastructure to operate (Kafka/Redpanda)
  - You must design for idempotency + DLQ (because delivery is at-least-once)
- **Why**
  - Video processing is heavy; downstream will eventually slow down. A queue/log keeps the system stable.

#### 3) Separate workers: segmentation (CPU) and AI (GPU/compute)
- **Pros**
  - Scale by resource type: segmentation scales with CPU, AI scales with GPU/compute
  - AI failures don’t break segmentation logic
  - Easier to swap models or extend the pipeline without touching upload/API
- **Cons**
  - More services → more orchestration/monitoring
- **Why**
  - Avoid the “one worker does everything” bottleneck and make resource usage tunable.

#### 4) Hybrid metadata: detailed JSON in MinIO + indexes in Postgres
- **Pros**
  - Per-segment JSON writes in parallel with low contention
  - Postgres enables fast UI/API queries (status, segment list, tags)
  - Scales well: store large raw outputs in object storage; keep only indexes in DB
- **Cons**
  - Data lives in two places → you need strict path conventions and consistency rules
- **Why**
  - A common approach to stay flexible and cost-efficient while keeping queries fast.

#### 5) Realtime status via WebSocket
- **Pros**
  - Users see progress immediately (segmenting/AI processing) without heavy polling
  - Easier to debug: you can see which stage is stuck
- **Cons**
  - With multiple API replicas, you need a shared hub (Redis/pubsub) instead of in-memory state
- **Why**
  - Better UX and much easier operations for a distributed pipeline.

---

### Where is data stored?

#### 1) Object storage (MinIO)
- Raw video:
  - `raw/{video_id}.mp4`
- Segments:
  - `processed/{video_id}/segments/s0001.mp4`
  - `processed/{video_id}/segments/s0002.mp4`
  - ...
- Per-segment metadata (JSON):
  - `metadata/{video_id}/segments/s0001.json`
  - ...

#### 2) Database (Postgres)
- `videos`: overall video state (`UPLOADING`, `UPLOADED`, `SEGMENTING`, `SEGMENTED`, `AI_PROCESSING`, `DONE`)
- `segments`: segment index (start/end time + path)
- `tags`: AI tags per segment
- `processed_events`: idempotency (avoid duplicates on retry/replay)

---

### Step-by-step flow

#### Step A — Upload (no AI yet)
1) The UI creates a `video_id` via the API
2) The UI uploads the file to MinIO via multipart (split into multiple parts)
3) The UI calls `complete` to finalize the object as `raw/{video_id}.mp4`

Only after completion is the video truly “ready to process”.

#### Step B — API publishes a Kafka event (triggers the pipeline)
The API publishes to topic:
- `video.raw.uploaded`

This event is the “job ticket”: the video is uploaded and ready for workers.

#### Step C — Segmentation worker splits the video
The worker:
- Download `raw/{video_id}.mp4`
- Uses FFmpeg to split (e.g., every 10 seconds) → produces segment files
- Upload segments lên MinIO
- Writes rows to the `segments` table
- Publishes:
  - `video.segment.completed` (includes the segment list)
  - `video.status` (progress)

#### Step D — AI worker runs AI on segments
The worker:
- Receives the segment list
- Runs AI per segment (POC: random tags)
- Writes JSON metadata to MinIO
- Writes tags to the `tags` table
- Publishes:
  - `video.ai.completed` (per segment)
  - `video.status` (progress)
  - `video.finalized` (DONE)

#### Step E — Realtime notify (WebSocket)
FastAPI subscribes to:
- `video.status`, `video.finalized`, `video.failed`

And pushes to:
- `WS /ws/{video_id}`

The UI shows stage-by-stage progress.

---

### Example: 1 video → 6 segments → tags per segment

Assume:
- The video is ~60 seconds
- Segment time = 10 seconds

You get 6 segments:

| Segment | Time range | Output file (MinIO) | Example tags (POC) |
|---|---:|---|---|
| s0001 | 0–10s | `processed/{video_id}/segments/s0001.mp4` | `["person", "car"]` |
| s0002 | 10–20s | `processed/{video_id}/segments/s0002.mp4` | `["text", "logo"]` |
| s0003 | 20–30s | `processed/{video_id}/segments/s0003.mp4` | `["bicycle", "person"]` |
| s0004 | 30–40s | `processed/{video_id}/segments/s0004.mp4` | `["animal", "person"]` |
| s0005 | 40–50s | `processed/{video_id}/segments/s0005.mp4` | `["car", "logo"]` |
| s0006 | 50–60s | `processed/{video_id}/segments/s0006.mp4` | `["text", "person"]` |

Per-segment JSON metadata output (example `s0001`):
- Key: `metadata/{video_id}/segments/s0001.json`
- Example content:

```json
{
  "video_id": "v_xxx",
  "segment_id": "s0001",
  "tags": ["person", "car"],
  "confidence": [0.92, 0.81],
  "created_at": "2026-04-22T03:00:00Z"
}
```

In the DB, `segments` will have 6 rows; `tags` will have multiple rows (one per tag).

---

### “Why don’t I see segments/tags right after upload completes?”
Because upload completion only:
- finalizes the object in MinIO
- publishes an event so workers can start

Segmentation/AI are **async**, so they take time. You can track progress via:
- WebSocket (`video.status`)
- or polling `GET /videos/{video_id}`

---

### After the POC (next upgrades)
- Replace stub tags with real models (YOLO/OCR/ASR)
- “1 segment = 1 task” (Kafka message per segment) for more parallelism and granular retries
- Outbox pattern to keep DB + Kafka consistent during failures
- Observability: metrics/tracing (Prometheus + OpenTelemetry)

