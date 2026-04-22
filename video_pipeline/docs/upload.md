## Chunk upload (multipart): retry + validation

POC này dùng **presigned multipart upload** lên MinIO (S3-compatible).

Ý tưởng chính:
- API chỉ làm **control-plane**: tạo `upload_id`, cấp presigned URL, complete upload, publish Kafka event.
- Client/UI upload data **trực tiếp** lên MinIO qua presigned URL (không đi qua API).

---

### Luồng chuẩn (happy path)

1) Tạo `video_id`
- `POST /videos`

2) Init multipart
- `POST /videos/{video_id}/multipart/init`
- Trả về `upload_id`

3) Upload từng part (chunk)
- Với mỗi `part_number` (bắt đầu từ 1):
  - `POST /videos/{video_id}/multipart/part-url?upload_id=...&part_number=N`
  - `PUT` bytes của chunk lên URL trả về
  - Nhận `ETag` từ response header

4) Complete multipart
- `POST /videos/{video_id}/multipart/complete`
- Body gồm `upload_id` và list `parts = [{ETag, PartNumber}, ...]`
- Sau khi complete thành công, API publish Kafka event `video.raw.uploaded`

---

### Retry part fail: làm thế nào cho đúng?

#### Nguyên tắc
- Multipart upload là **idempotent theo PartNumber**:
  - Nếu part N upload fail → retry **chỉ part N**
  - Không cần upload lại toàn bộ file

#### Khuyến nghị thực tế
- **Exponential backoff**: 1s → 2s → 4s → 8s (giới hạn max, ví dụ 10–30s)
- **Giới hạn concurrency** (upload song song):
  - Quá cao dễ nghẽn network hoặc overload MinIO
  - POC UI đang cho chỉnh `Max parallel uploads`

#### Khi retry, thay gì?
- Chỉ gọi lại:
  - presign part URL (an toàn, URL có expiry)
  - upload lại bytes của part đó
- Nhận `ETag` mới (có thể khác) và **thay vào list parts** trước khi complete

---

### Validation: đảm bảo dữ liệu đúng và file complete

#### 1) Per-part validation (checksum)
Mục tiêu: phát hiện corrupted chunk trong quá trình truyền.

Tuỳ hệ S3/MinIO:
- Có thể gửi `Content-MD5` khi `upload_part`
- Nếu checksum sai → server trả lỗi → client retry part

POC hiện tại:
- Endpoint presign hỗ trợ truyền `content_md5` (optional).
- Streamlit UI mặc định **bật** `Content-MD5` và sẽ:
  - tính MD5 cho từng chunk
  - gửi `content_md5` lên endpoint presign
  - `PUT` kèm header `Content-MD5`

#### 2) Completion validation (ETag list)
Mục tiêu: đảm bảo đủ part và đúng thứ tự khi merge.

Khi gọi `complete_multipart_upload`:
- Bạn phải gửi list `parts` với `PartNumber` + `ETag`
- **Bắt buộc sort theo `PartNumber` tăng dần**

POC UI:
- Sau khi upload song song, UI **sort parts theo `PartNumber`** trước khi gọi complete.
- API cũng sort `parts` để “defensive”.

#### 3) Final checksum (SHA256)
Mục tiêu: có một checksum “ổn định” cho **toàn bộ file** (vì ETag của multipart không phải MD5 của file).

POC:
- Streamlit UI có tuỳ chọn tính **SHA256** của toàn bộ file và gửi lên `complete` qua field `checksum`.
- API lưu checksum này vào cột `videos.checksum`.

#### 3) “Gate” để không trigger pipeline sớm
Nguyên tắc:
- **Chỉ publish Kafka event sau khi complete thành công**

Vì:
- Worker segmentation đọc `raw/{video_id}.mp4`; nếu file chưa complete thì worker sẽ fail hoặc đọc sai.

---

### Lỗi thường gặp

- **Presigned URL trỏ `localhost` trong Docker**
  - Nếu uploader chạy trong container (Streamlit server-side), URL phải là `http://minio:9000/...`
  - Nếu uploader chạy ở browser (client-side), URL cần host public như `http://localhost:9000/...`

- **Quên sort `parts`**
  - Complete có thể fail hoặc merge sai → luôn sort theo `PartNumber`

- **ETag thiếu hoặc sai format**
  - Nhiều S3 trả `ETag` có dấu ngoặc kép; giữ nguyên đúng value nhận được.

