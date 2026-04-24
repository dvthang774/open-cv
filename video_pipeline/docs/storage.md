## Storage layout (MinIO)

This project uses **canonical prefixes** so you can browse data predictably and apply lifecycle rules (retention/cleanup) per prefix.

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

Notes:
- **Binary vs JSON separation**: videos/segments are stored as MP4 objects; metadata is stored as JSON for cheap reads and easy evolution.
- **Deterministic keys**: re-processing overwrites the same object key instead of creating duplicates.

