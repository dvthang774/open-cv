## Action Plan: Standardization & data cleaning (production-ready)

### Why this exists
This plan standardizes data contracts and cleans/normalizes outputs so the pipeline is predictable and safe to scale for continuous 10–20 min videos.

Non-negotiables:
- **Deterministic outputs**: same `video_id` → same `segment_id` sequence and the same storage keys
- **Stable contract**: explicit field names, explicit units (seconds), no ambiguous aliases
- **Clean metadata**: minimal schema with normalized booleans and normalized label strings
- **Idempotent by design**: re-processing does not create duplicates (DB or storage)

---

### Target contracts (the standard)

#### Segment object (produced by segment-worker)
- `segment_id`
- `start_time` (float seconds)
- `end_time` (float seconds)
- `duration` (float seconds) = `max(0.0, end_time - start_time)`
- `file_path` (S3/MinIO URI): `s3://{bucket}/segments/{video_id}/{segment_id}.mp4`

#### Per-segment metadata JSON (written by ai-worker)

```json
{
  "video_id": "...",
  "segment_id": "...",
  "start_time": 0,
  "end_time": 60,
  "duration": 60,
  "labels": [],
  "quality": {
    "is_blurry": false,
    "is_dark": false
  }
}
```

Cleaning rules:
- **Time fields** are always float seconds; `duration` must be non-negative.
- **labels** are cleaned: trim, lowercase, de-dup (stable ordering recommended).
- **quality flags** are always booleans (never missing).

---

### Canonical storage layout (single source of truth)
- `raw/{video_id}.mp4`
- `segments/{video_id}/{segment_id}.mp4`
- `metadata/{video_id}/{segment_id}.json`

Migration rule (to avoid breaking existing consumers/UI):
- During rollout, optionally **write both legacy + canonical keys**, then remove legacy writes after everything reads canonical.

---

### Deterministic quality check (fast heuristic)
Goal: output stable booleans `is_dark` / `is_blurry` per segment.

Implementation (simple, acceptable):
- sample **N frames** (e.g. 3) via ffmpeg
- compute:
  - **dark**: mean luma < threshold → `is_dark=true`
  - **blurry**: Laplacian variance < threshold → `is_blurry=true`

Failure handling (production hygiene):
- If quality computation fails, **do not crash the pipeline**.
- Default `is_dark/is_blurry` to `false/false` (and optionally record error in logs only).

---

### Idempotency (absolute no-duplicates)
`processed_events(consumer,event_id)` prevents duplicates of the same Kafka message, but is not sufficient for “re-run the same video”.

Add **entity-level idempotency** with deterministic keys:

#### Segment-worker
- Before running ffmpeg, check if segmentation is already complete for `video_id`.
  - Minimum: check DB rows exist for this `video_id`.
  - Better: check completeness (expected count/coverage) to avoid skipping partial runs.
- Strategy:
  - **Skip-if-complete**: emit segments list again without re-segmenting
  - **Repair-missing**: only generate/upload missing segments if partial state exists

Guardrail:
- If `duration <= 0` for a segment, **skip it and emit a warning/status**, don’t silently “cancel the video”.

#### AI-worker
- For each segment, check if `metadata/{video_id}/{segment_id}.json` exists and matches schema:
  - if valid → skip
  - else → regenerate and overwrite the deterministic key

---

### Implementation roadmap (concrete steps)

#### Step 1 — Segment worker (producer)
- Write segments to `segments/{video_id}/{segment_id}.mp4`
- Emit segment object fields: `segment_id,start_time,end_time,duration,file_path`
- Add entity-level idempotency: skip/repair based on DB/S3 state
- Temporary compatibility: keep legacy `path` / `id` fields during migration window

#### Step 2 — AI worker (consumer + metadata writer)
- Prefer `file_path` (fallback to legacy `path` during migration)
- Run quality heuristic and output booleans
- Write cleaned metadata JSON to `metadata/{video_id}/{segment_id}.json`
- Add entity-level idempotency: skip if metadata exists + valid

#### Step 3 — Cleanup & documentation
- Remove legacy fields/writes after consumers/UI are fully migrated
- Update docs: `storage.md`, `events.md`, and examples in `for-beginners.md`

