## Streamlit UI (POC)

### What it does
- Upload video via API-controlled presigned multipart upload (MinIO)
- Shows realtime status (WebSocket) and DB snapshot
- Lists segments and previews first segment via presigned GET

### Run
Use docker compose service `ui` (see `docker-compose.yml`).

