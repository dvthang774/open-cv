## Chunk upload (multipart): retry + validation

This POC uses **presigned multipart upload** to MinIO (S3-compatible).

Key idea:
- The API is **control-plane only**: create `upload_id`, issue presigned URLs, complete the upload, publish Kafka events.
- The client/UI uploads bytes **directly** to MinIO via presigned URLs (data does not flow through the API).

---

### Happy path flow

1) Create `video_id`
- `POST /videos`

2) Init multipart
- `POST /videos/{video_id}/multipart/init`
- Returns `upload_id`

3) Upload each part (chunk)
- For each `part_number` (starting at 1):
  - `POST /videos/{video_id}/multipart/part-url?upload_id=...&part_number=N`
  - `PUT` the chunk bytes to the returned URL
  - Read `ETag` from the response headers

4) Complete multipart
- `POST /videos/{video_id}/multipart/complete`
- Body contains `upload_id` and a list `parts = [{ETag, PartNumber}, ...]`
- After a successful completion, the API publishes Kafka event `video.raw.uploaded`

---

### Retrying failed parts: the correct way

#### Principles
- Multipart upload is **idempotent by PartNumber**:
  - If part N fails → retry **only part N**
  - No need to re-upload the whole file

#### Practical 
- **Exponential backoff**: 1s → 2s → 4s → 8s (cap at e.g. 10–30s)
- **Limit concurrency** (parallel uploads):
  - Too high can saturate network or overload MinIO
  - The POC UI exposes `Max parallel uploads`

#### What changes when retrying?
- You only need to redo:
  - presign the part URL (safe; URLs expire)
  - re-upload the bytes for that part
- You may get a new `ETag` (it can differ); **replace it** in the `parts` list before completing

---

### Validation: data integrity and completion correctness

#### 1) Per-part validation (checksum)
Goal: detect corrupted chunks during transfer.

Depending on S3/MinIO capabilities:
- You can provide `Content-MD5` on `upload_part`
- If the checksum is wrong → server returns an error → client retries that part

In this POC:
- The presign endpoint supports `content_md5` (optional).
- The Streamlit UI enables `Content-MD5` by default and will:
  - compute MD5 per chunk
  - pass `content_md5` to the presign endpoint
  - `PUT` with the `Content-MD5` header

#### 2) Completion validation (ETag list)
Goal: ensure all parts exist and the merge order is correct.

When calling `complete_multipart_upload`:
- You must send `parts` with `PartNumber` + `ETag`
- You **must** sort by `PartNumber` ascending

POC UI:
- After parallel uploads, the UI **sorts parts by `PartNumber`** before completing.
- The API also sorts `parts` defensively.

#### 3) Final checksum (SHA256)
Goal: have a stable checksum for the **entire file** (multipart `ETag` is not the file MD5).

POC:
- The Streamlit UI can compute the file **SHA256** and send it to `complete` via the `checksum` field.
- The API stores it in `videos.checksum`.

#### 4) A “gate” to avoid triggering the pipeline too early
Principle:
- **Only publish Kafka events after the multipart completion succeeds**

Because:
- The segmentation worker reads `raw/{video_id}.mp4`; if the file is not complete, it may fail or read inconsistent data.

---

### Common pitfalls

- **Presigned URL points to `localhost` inside Docker**
  - If the uploader runs inside a container (Streamlit server-side), the URL must use `http://minio:9000/...`
  - If the uploader runs in the browser (client-side), the URL must use a public host like `http://localhost:9000/...`

- **Forgetting to sort `parts`**
  - Completion can fail or merge incorrectly → always sort by `PartNumber`

- **Missing or misformatted `ETag`**
  - Many S3 implementations return quoted ETags; keep the exact value you received.

