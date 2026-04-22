## API (POC)

Base URL: `http://localhost:8000`

### 1) Create video
`POST /videos?user_id=optional`

Returns `video_id` and `raw_key`.

### 2) Init multipart
`POST /videos/{video_id}/multipart/init`

Body:
```json
{"content_type":"video/mp4"}
```

Returns `upload_id`.

### 3) Presign part upload
`POST /videos/{video_id}/multipart/part-url?upload_id=...&part_number=1`

Returns presigned `url` to `PUT` the chunk directly to MinIO.

Notes:
- Retry failed upload by retrying the same `part_number`.
- Keep the returned `ETag` from each successful part upload.

### 4) Complete multipart (publish Kafka)
`POST /videos/{video_id}/multipart/complete`

Body:
```json
{
  "upload_id": "...",
  "parts": [{"ETag":"...","PartNumber":1}],
  "checksum": null
}
```

Notes:
- `parts` must be sorted by `PartNumber` ascending.
- After successful completion, API publishes `video.raw.uploaded` to Kafka to trigger workers.

### 5) Query status/results
`GET /videos/{video_id}`

### 6) WebSocket realtime updates
`WS /ws/{video_id}`

Server pushes messages from Kafka topics:
- `video.status`
- `video.finalized`
- `video.failed`

### 7) Presigned GET (preview objects)
`GET /objects/presign-get?key=...`

Use this to preview objects stored in MinIO (raw video or segments) in the UI.

