## Architecture (on-prem POC)

### Goal
Upload → Kafka → Segment → AI → Metadata → Realtime Notify

### Components
- **FastAPI**: control-plane (presigned upload + orchestration) + WebSocket notify
- **MinIO**: raw videos, segments, JSON metadata
- **Kafka (Redpanda)**: event backbone + buffering/backpressure
- **Postgres**: business state + indexes + idempotency (`processed_events`)
- **segment-worker**: FFmpeg segmentation (CPU)
- **ai-worker**: AI tagging (stub or YOLO). YOLO weights are pulled from MinIO/S3 on container startup (Model Registry pattern).

### End-to-end flow
1) Client creates video_id via API
2) Client uploads directly to MinIO with presigned multipart
3) Client completes multipart via API → API emits `video.raw.uploaded`
4) Segment worker consumes → writes segments + DB → emits `video.segment.completed`
5) AI worker consumes → writes tags + JSON → emits `video.finalized`
6) Workers publish progress to `video.status` → API consumes and pushes WebSocket updates

### Requirements coverage (current POC)
- **Split into 1-minute segments**: supported via config `VP_SEGMENT_SECONDS=60` (default may differ).
- **Per-segment metadata**: `metadata/{video_id}/segments/{segment_id}.json` contains `timestamp`, `duration`, and basic `tags`.
- **Per-segment metadata**: `metadata/{video_id}/{segment_id}.json` contains `start_time/end_time/duration`, cleaned `labels`, and `quality` flags.
- **Clear S3/MinIO structure**: `raw/`, `segments/`, `metadata/` prefixes (see `docs/storage.md`).
- **Optional quality filtering (blur/dark)**: implemented in AI stage (configurable via env; can tag `low_quality` and optionally skip YOLO).

### Diagram (matches current POC)

```mermaid
graph TD
  subgraph Client_Layer["Frontend / Client (POC)"]
    UI["Streamlit UI (server-side app)"]
    WS_C["WebSocket client (inside UI)"]
  end

  subgraph API_Gateway_Layer["API & Control Plane"]
    API["FastAPI"]
  end

  subgraph Message_Broker_Layer["Event Backbone"]
    K[(Redpanda / Kafka)]
  end

  subgraph Worker_Layer["Processing Workers"]
    SW["segment-worker: Python + FFmpeg (CPU)"]
    AW["ai-worker: Python (POC stub tags)"]
  end

  subgraph Storage_Layer["Persistence & Data"]
    S3[("Object Storage: MinIO (S3-compatible)")]
    DB[("Relational DB: PostgreSQL")]
  end

  %% Upload control-plane
  UI -->|"POST /videos, /multipart/init, /multipart/part-url"| API

  %% Upload data-plane (multipart parts go directly to MinIO)
  UI -->|"PUT upload_part (chunks) via presigned URL"| S3
  UI -->|"POST /multipart/complete"| API
  API -->|"CompleteMultipartUpload"| S3

  %% Trigger processing
  API -->|"publish: video.raw.uploaded"| K
  API -->|"publish: video.status (UPLOADED)"| K

  %% Segment stage
  K -->|"consume: video.raw.uploaded"| SW
  SW -->|"GET raw/{video_id}.mp4"| S3
  SW -->|"PUT segments/{video_id}/*.mp4"| S3
  SW -->|"INSERT segments + UPDATE videos.status"| DB
  SW -->|"publish: video.segment.completed"| K
  SW -->|"publish: video.status (SEGMENTING/SEGMENTED)"| K

  %% AI stage
  K -->|"consume: video.segment.completed"| AW
  AW -->|"PUT metadata/{video_id}/*.json"| S3
  AW -->|"INSERT tags + UPDATE videos.status"| DB
  AW -->|"publish: video.ai.completed"| K
  AW -->|"publish: video.finalized + video.status (DONE)"| K

  %% Realtime status fanout
  K -->|"consume: video.status/video.finalized/video.failed"| API
  API -->|"WS /ws/{video_id}"| WS_C
  WS_C --> UI

  %% Query results
  UI -->|"GET /videos/{video_id}"| API
  API -->|"SELECT videos/segments/tags"| DB
```

Notes:
- The uploader is the Streamlit app process (inside Docker), so presigned URLs must point to `minio:9000`.
- For YOLO mode, the model artifact is stored in MinIO/S3 (e.g. `s3://models/yolov8_v1.pt`) and cached inside the `ai-worker` container at startup.
- Auth/JWT/CORS are not implemented in the current POC.

