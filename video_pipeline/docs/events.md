## Kafka topics (POC)

This file is the **data contract** between services. For production scaling, prefer adding fields (backward compatible) over renaming/removing fields.

### `video.raw.uploaded`
Emitted by API after multipart complete.

Fields:
- `event_id`
- `video_id`
- `type`: `VIDEO_UPLOADED`
- `path`
- `status`: `UPLOADED`
- `created_at`

### `video.segment.completed`
Emitted by segment-worker after segmentation.

Why these fields exist:
- `segment_id`: stable identifier for idempotency and deterministic storage keys
- `start_time/end_time/duration`: normalize time units (seconds) and support downstream logic
- `file_path`: canonical location of the segment object in MinIO/S3

Fields:
- `event_id`
- `video_id`
- `type`: `VIDEO_SEGMENTED`
- `segments`: list of segment objects:
  - `segment_id`
  - `start_time`
  - `end_time`
  - `duration`
  - `file_path` (S3/MinIO URI)
  - (migration window) legacy aliases: `{id, path, start, end}`
- `created_at`

### `video.ai.completed`
Emitted by ai-worker per segment (POC stub).

Why the payload is “clean”:
- Downstream consumers (UI, analytics, search indexing) should not depend on model-specific debug fields.
- `labels` and quality flags are normalized, stable, and easy to query.

Fields:
- `event_id`
- `video_id`
- `type`: `SEGMENT_AI_COMPLETED`
- `segment_id`
- `start_time`, `end_time`, `duration`
- `labels`
- `quality`: `{is_blurry, is_dark}`

### `video.status`
Progress/status updates for realtime UI.

Fields:
- `video_id`
- `status`
- `progress` (0-100)
- `message`

### `video.finalized`
Video completed.

Fields:
- `event_id`
- `video_id`
- `status`: `DONE`

### `video.failed`
DLQ for events that exceed retry attempts.

