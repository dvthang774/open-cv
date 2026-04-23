## Storage layout (MinIO)

- Raw video:
  - `raw/{video_id}.mp4`
- Segments:
  - `segments/{video_id}/{segment_id}.mp4`
- Per-segment metadata:
  - `metadata/{video_id}/{segment_id}.json`

Metadata JSON schema (standardized):
- `video_id`, `segment_id`
- `start_time`, `end_time`, `duration` (seconds)
- `labels` (list of strings)
- `quality.is_dark`, `quality.is_blurry` (booleans)

