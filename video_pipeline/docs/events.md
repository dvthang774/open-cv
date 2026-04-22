## Kafka topics (POC)

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

Fields:
- `event_id`
- `video_id`
- `type`: `VIDEO_SEGMENTED`
- `segments`: list of `{id, path, start, end}`
- `created_at`

### `video.ai.completed`
Emitted by ai-worker per segment (POC stub).

Fields:
- `event_id`
- `video_id`
- `type`: `SEGMENT_AI_COMPLETED`
- `segment_id`
- `tags`
- `confidence`

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

