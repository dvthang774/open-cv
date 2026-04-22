## Architecture (on-prem POC)

### Goal
Upload → Kafka → Segment → AI → Metadata → Realtime Notify

### Components
- **FastAPI**: control-plane (presigned upload + orchestration) + WebSocket notify
- **MinIO**: raw videos, segments, JSON metadata
- **Kafka (Redpanda)**: event backbone + buffering/backpressure
- **Postgres**: business state + indexes + idempotency (`processed_events`)
- **segment-worker**: FFmpeg segmentation (CPU)
- **ai-worker**: tagging stub (replace with GPU inference later)

### End-to-end flow
1) Client creates video_id via API
2) Client uploads directly to MinIO with presigned multipart
3) Client completes multipart via API → API emits `video.raw.uploaded`
4) Segment worker consumes → writes segments + DB → emits `video.segment.completed`
5) AI worker consumes → writes tags + JSON → emits `video.finalized`
6) Workers publish progress to `video.status` → API consumes and pushes WebSocket updates

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
  SW -->|"PUT processed/{video_id}/segments/*.mp4"| S3
  SW -->|"INSERT segments + UPDATE videos.status"| DB
  SW -->|"publish: video.segment.completed"| K
  SW -->|"publish: video.status (SEGMENTING/SEGMENTED)"| K

  %% AI stage
  K -->|"consume: video.segment.completed"| AW
  AW -->|"PUT metadata/{video_id}/segments/*.json"| S3
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
- Auth/JWT/CORS are not implemented in the current POC.

