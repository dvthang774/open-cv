## Streamlit UI

URL: `http://localhost:8501`

### Features (POC)
- Upload video using API-controlled presigned multipart upload (MinIO)
- Shows realtime progress via WebSocket (`/ws/{video_id}`)
- Shows DB snapshot (`GET /videos/{video_id}`)
- Lists segments and previews the first segment via `GET /objects/presign-get`

### Implementation
- `ui/app.py` (Streamlit page)
- `docker/streamlit.Dockerfile`
- `docker-compose.yml` service: `ui`

