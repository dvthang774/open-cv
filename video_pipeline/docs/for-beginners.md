## For beginners: Video → Segments → AI tags (POC flow)

Trang này dành cho người mới học AI / mới làm hệ thống xử lý video, giúp hiểu rõ pipeline đang chạy “từ upload đến ra kết quả” theo cách dễ hình dung.

---

### Mục tiêu hệ thống (1 câu)
Bạn upload 1 video, hệ thống tự **cắt video thành nhiều đoạn nhỏ (segments)**, chạy AI trên từng đoạn, lưu kết quả và **hiển thị tiến độ realtime**.

Pipeline:

Upload → Kafka → Segment (FFmpeg) → AI → Metadata → Realtime Notify

---

### Vì sao phải “cắt video” trước khi chạy AI?
Video dài (10–20 phút) nếu chạy AI một phát sẽ:
- Chậm, khó scale
- Dễ lỗi (mất điện, crash model, hết tài nguyên) → phải chạy lại từ đầu

Cắt thành segments giúp:
- **Song song**: nhiều worker xử lý nhiều đoạn cùng lúc
- **Retry nhỏ**: hỏng đoạn nào chạy lại đoạn đó
- **Progress rõ ràng**: biết đang làm tới đâu

---

### Các thành phần trong POC này làm gì?

- **Streamlit UI** (`http://localhost:8501`)
  - Chọn file video
  - Upload theo multipart (chia chunk)
  - Xem progress và kết quả (segments, tags)

- **FastAPI** (`http://localhost:8000`)
  - “Control plane”: tạo `video_id`, phát presigned URL upload, complete upload
  - Publish event vào Kafka để kích hoạt workers
  - Nhận progress từ Kafka và push ra WebSocket

- **MinIO** (S3-compatible) (`http://localhost:9001`)
  - Lưu video gốc, segments, JSON metadata

- **Kafka (Redpanda)**
  - “Backbone”: giữ event, buffer khi worker bận, giúp scale ngang

- **Postgres**
  - Lưu trạng thái video và index (segments, tags) để query nhanh

- **segment-worker (FFmpeg)**
  - Cắt video thành segments (CPU-bound)

- **ai-worker**
  - Chạy AI trên từng segment (POC hiện là stub/random tags; sau này thay model thật)

---

### Cấu trúc dữ liệu lưu ở đâu?

#### 1) Object storage (MinIO)
- Video gốc:
  - `raw/{video_id}.mp4`
- Segments:
  - `processed/{video_id}/segments/s0001.mp4`
  - `processed/{video_id}/segments/s0002.mp4`
  - ...
- Metadata theo segment (JSON):
  - `metadata/{video_id}/segments/s0001.json`
  - ...

#### 2) Database (Postgres)
- `videos`: trạng thái chung của video (`UPLOADING`, `UPLOADED`, `SEGMENTING`, `SEGMENTED`, `AI_PROCESSING`, `DONE`)
- `segments`: danh sách segments + thời gian start/end + path
- `tags`: tags AI cho từng segment
- `processed_events`: idempotency (tránh xử lý trùng khi retry/replay)

---

### Luồng hoạt động chi tiết (từng bước)

#### Bước A — Upload (chưa có AI)
1) UI tạo `video_id` qua API
2) UI upload file lên MinIO theo multipart (chia thành nhiều part)
3) UI gọi `complete` để “chốt” file thành `raw/{video_id}.mp4`

Khi complete xong, video mới thực sự “sẵn sàng để xử lý”.

#### Bước B — API phát event vào Kafka (kích hoạt pipeline)
API publish event vào topic:
- `video.raw.uploaded`

Event kiểu “job ticket”: video đã upload xong, mời worker xử lý.

#### Bước C — Segment worker cắt video
Worker:
- Download `raw/{video_id}.mp4`
- Dùng FFmpeg cắt (ví dụ mỗi 10 giây) → tạo files segments
- Upload segments lên MinIO
- Ghi rows vào table `segments`
- Publish:
  - `video.segment.completed` (có list segments)
  - `video.status` (progress)

#### Bước D — AI worker chạy AI trên segments
Worker:
- Nhận danh sách segments
- Với mỗi segment: chạy AI (POC: random tags)
- Lưu JSON metadata vào MinIO
- Ghi tags vào table `tags`
- Publish:
  - `video.ai.completed` (per segment)
  - `video.status` (progress)
  - `video.finalized` (DONE)

#### Bước E — Realtime notify (WebSocket)
FastAPI subscribe:
- `video.status`, `video.finalized`, `video.failed`

Và push ra:
- `WS /ws/{video_id}`

UI sẽ thấy progress chạy theo giai đoạn.

---

### Ví dụ minh hoạ: 1 video → 6 segments → tags từng segment

Giả sử:
- Video dài ~60 giây
- Segment time = 10 giây

Ta có 6 segments:

| Segment | Time range | Output file (MinIO) | Ví dụ tags (POC) |
|---|---:|---|---|
| s0001 | 0–10s | `processed/{video_id}/segments/s0001.mp4` | `["person", "car"]` |
| s0002 | 10–20s | `processed/{video_id}/segments/s0002.mp4` | `["text", "logo"]` |
| s0003 | 20–30s | `processed/{video_id}/segments/s0003.mp4` | `["bicycle", "person"]` |
| s0004 | 30–40s | `processed/{video_id}/segments/s0004.mp4` | `["animal", "person"]` |
| s0005 | 40–50s | `processed/{video_id}/segments/s0005.mp4` | `["car", "logo"]` |
| s0006 | 50–60s | `processed/{video_id}/segments/s0006.mp4` | `["text", "person"]` |

Kết quả metadata JSON cho mỗi segment (ví dụ `s0001`):
- Key: `metadata/{video_id}/segments/s0001.json`
- Nội dung (ví dụ):

```json
{
  "video_id": "v_xxx",
  "segment_id": "s0001",
  "tags": ["person", "car"],
  "confidence": [0.92, 0.81],
  "created_at": "2026-04-22T03:00:00Z"
}
```

Trong DB, table `segments` sẽ có 6 dòng; table `tags` sẽ có nhiều dòng (mỗi tag là 1 row).

---

### “Upload complete rồi sao chưa thấy segments/tags?”
Vì upload complete chỉ:
- chốt file trên MinIO
- publish event để worker chạy

Segment/AI chạy **async** nên cần thời gian. Bạn sẽ thấy progress qua:
- WebSocket (`video.status`)
- hoặc polling `GET /videos/{video_id}`

---

### Nâng cấp sau POC (khi bạn học sâu hơn)
- Thay stub tags bằng model thật (YOLO/OCR/ASR)
- “1 segment = 1 task” (Kafka message per segment) để tăng parallelism và retry granular hơn
- Outbox pattern để đảm bảo DB + Kafka nhất quán khi failure
- Observability: metrics/tracing (Prometheus + OpenTelemetry)

