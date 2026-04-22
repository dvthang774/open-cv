## Runbook (POC)

### Start stack
```bash
cd video_pipeline
docker compose up --build
```

### Configure 1-minute segmentation
Set in `.env`:
- `VP_SEGMENT_SECONDS=60`

### Configure quality filtering (dark/blur) in AI stage (optional)
Environment variables (defaults shown):
- `VP_QF_ENABLE=1`
- `VP_QF_SAMPLE_FRAMES=3`
- `VP_QF_DARK_THRESHOLD=35` (mean luma 0–255; lower = darker)
- `VP_QF_BLUR_THRESHOLD=60` (Laplacian variance; higher = sharper)
- `VP_QF_SKIP_ON_FAIL=1` (if 1, tag `low_quality` and skip YOLO)

### Use YOLO model via Model Registry on MinIO/S3 
This project treats the YOLO weights file as an artifact stored in MinIO/S3 (like a “model registry”).

1) Upload your model file to MinIO/S3:
   - Bucket: `models`
   - Object key: `yolov8_v1.pt`
   - Example URI: `s3://models/yolov8_v1.pt`

2) Configure `ai-worker` (in `.env` or `docker-compose.yml`):
   - `VP_AI_MODE=yolo`
   - `VP_MODEL_S3_BUCKET=models`
   - `VP_MODEL_S3_KEY=yolov8_v1.pt`
   - `VP_MODEL_CACHE_DIR=/var/cache/vp-models`
   - Optional:
     - `VP_YOLO_DEVICE=cpu` (or `0` for GPU)
     - `VP_YOLO_CLASSES=0,1,2` (comma-separated)

3) On container startup, the `ai-worker` entrypoint will:
   - Check the cached model in `VP_MODEL_CACHE_DIR`
   - Call `HeadObject` to compare ETag/LastModified
   - Download only if missing or newer
   - Set `VP_YOLO_MODEL` to the cached path (so `ProcessAI` can load it)

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

