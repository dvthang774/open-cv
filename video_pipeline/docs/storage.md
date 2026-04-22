## Storage layout (MinIO)

- Raw video:
  - `raw/{video_id}.mp4`
- Segments:
  - `processed/{video_id}/segments/{segment_id}.mp4`
- Per-segment metadata:
  - `metadata/{video_id}/segments/{segment_id}.json`

Metadata JSON includes (POC):
- `timestamp` (segment start time, seconds)
- `duration` (seconds)
- `tags` (basic labels) + `confidence`
- `quality` (optional): dark/blur metrics and pass/fail

