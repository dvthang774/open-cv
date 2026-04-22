## Database (Postgres)

### Tables (POC)
- `videos`: business state per video (`status`, `raw_path`, optional `user_id`)
- `segments`: index of produced segments
- `tags`: index of AI tags (POC)
- `processed_events`: idempotency per consumer (`event_id`)

### Field ownership (who writes what, and when?)

#### `videos`
- **`video_id`**: written by the API when `POST /videos` is called
- **`user_id`**: written by the API when `POST /videos?user_id=...` is used (POC), used to attach ownership
- **`raw_path`**: written by the API when creating the video record (points to `s3://{bucket}/raw/{video_id}.mp4`)
- **`status`**:
  - API sets `UPLOADING` when the video record is created
  - API sets `UPLOADED` after a successful `multipart/complete`
  - segment-worker sets `SEGMENTING` when FFmpeg starts and `SEGMENTED` when it finishes
  - ai-worker sets `AI_PROCESSING` when it starts and `DONE` when it finishes
  - (on failure) a worker/consumer may set `FAILED` (POC mostly reports via `video.failed`)
- **`checksum`**: written by the API after `multipart/complete` (provided by the client/UI; POC uses full-file SHA256)
- **`created_at`**: set automatically by the DB on insert
- **`updated_at`**: updated by API/workers whenever fields change (e.g., status transitions)

#### `segments`
- **`segment_id`**: created by segment-worker (e.g., `s0001`, `s0002`, ...)
- **`video_id`**: written by segment-worker for the current video
- **`start_time`, `end_time`**: computed by segment-worker based on segmenting strategy (POC: time-based)
- **`path`**: written by segment-worker after uploading to MinIO (`processed/{video_id}/segments/{segment_id}.mp4`)
- **`created_at`**: set automatically by the DB on insert

#### `tags`
- **`video_id`, `segment_id`**: written by ai-worker for the processed segment
- **`label`, `confidence`**: written by ai-worker from model output (POC: stub/random)
- **`created_at`**: set automatically by the DB on insert

#### `processed_events`
- **`consumer`**: worker name (e.g., `segment_worker`, `ai_worker`)
- **`event_id`**: taken from the Kafka message
- **`processed_at`**: set automatically by the DB on insert

### Idempotency
Workers insert into `processed_events(consumer,event_id)` before processing:
- if insert succeeds → process
- if already exists → skip

### Migrations
Created automatically on startup by API/workers (advisory lock prevents concurrent migration).

