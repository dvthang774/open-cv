## Realtime (WebSocket)

### WS endpoint
`/ws/{video_id}`

Client subscribes by `video_id` and receives server-pushed JSON messages.

### Source of messages
FastAPI runs a Kafka consumer (background task) subscribing to:
- `video.status`
- `video.finalized`
- `video.failed`

Each Kafka message is broadcast to the WebSocket room keyed by `video_id`.

### Why this design (POC)
- Keeps API non-blocking: upload completion emits events, workers do heavy tasks.
- UI gets progress without polling.

