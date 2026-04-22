## Database (Postgres)

### Tables (POC)
- `videos`: business state per video (`status`, `raw_path`, optional `user_id`)
- `segments`: index of produced segments
- `tags`: index of AI tags (POC)
- `processed_events`: idempotency per consumer (`event_id`)

### Field ownership (ai ghi gì, ghi lúc nào?)

#### `videos`
- **`video_id`**: API tạo ngay khi `POST /videos`
- **`user_id`**: API ghi khi `POST /videos?user_id=...` (POC), dùng để gắn owner
- **`raw_path`**: API ghi khi tạo video (trỏ tới `s3://{bucket}/raw/{video_id}.mp4`)
- **`status`**:
  - API ghi `UPLOADING` khi tạo record video
  - API ghi `UPLOADED` sau `multipart/complete` thành công
  - segment-worker ghi `SEGMENTING` khi bắt đầu FFmpeg và `SEGMENTED` khi xong
  - ai-worker ghi `AI_PROCESSING` khi bắt đầu và `DONE` khi hoàn tất
  - (khi lỗi) worker/consumer có thể đẩy `FAILED` (POC hiện chủ yếu báo qua `video.failed`)
- **`checksum`**: API ghi sau `multipart/complete` (nhận từ client/UI; POC dùng SHA256 toàn file)
- **`created_at`**: DB set tự động khi insert
- **`updated_at`**: API/worker update mỗi lần đổi trạng thái hoặc cập nhật trường

#### `segments`
- **`segment_id`**: segment-worker tạo (ví dụ `s0001`, `s0002`, ...)
- **`video_id`**: segment-worker ghi theo video đang xử lý
- **`start_time`, `end_time`**: segment-worker tính theo segment length (POC: time-based)
- **`path`**: segment-worker ghi sau khi upload segment lên MinIO (`processed/{video_id}/segments/{segment_id}.mp4`)
- **`created_at`**: DB set tự động khi insert

#### `tags`
- **`video_id`, `segment_id`**: ai-worker ghi theo segment đang xử lý
- **`label`, `confidence`**: ai-worker ghi từ output model (POC: stub/random)
- **`created_at`**: DB set tự động khi insert

#### `processed_events`
- **`consumer`**: worker name (ví dụ `segment_worker`, `ai_worker`)
- **`event_id`**: lấy từ Kafka message
- **`processed_at`**: DB set tự động khi insert

### Idempotency
Workers insert into `processed_events(consumer,event_id)` before processing:
- if insert succeeds → process
- if already exists → skip

### Migrations
Created automatically on startup by API/workers (advisory lock prevents concurrent migration).

