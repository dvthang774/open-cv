## Runbook (POC)

### Start stack
```bash
cd video_pipeline
docker compose up --build
```

### Useful URLs
- API: `http://localhost:8000`
- Streamlit UI: `http://localhost:8501`
- MinIO console: `http://localhost:9001` (user/pass: `minioadmin` / `minioadmin`)

### Smoke test (high-level)
1) `POST /videos` → get `video_id`
2) Init multipart + upload at least 1 part to MinIO using presigned URL
3) Complete multipart → workers should process
4) `GET /videos/{video_id}` → expect `DONE`, see segments + tags
5) Connect WS `/ws/{video_id}` to see progress from `video.status`

Tip:
- See `docs/upload.md` for retry + validation details (ETag list, PartNumber ordering, checksum).

### Cleanup incomplete uploads + retention
Run cleanup tool (manual, POC):
```bash
cd video_pipeline
docker compose exec -T api python -m app.tools.cleanup_storage
```

