from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import wait, FIRST_COMPLETED

import os

import requests
import streamlit as st
import websocket
import hashlib
import base64


# IMPORTANT:
# - Streamlit code runs *inside* the `ui` container, so it must call the API using the
#   Docker network DNS (service name), not localhost.
# - Browser access is separate; for POC we keep default public URLs for display only.
API_INTERNAL = os.environ.get("API_INTERNAL", "http://api:8000")
WS_INTERNAL = os.environ.get("WS_INTERNAL", "ws://api:8000")
API_PUBLIC = os.environ.get("API_PUBLIC", "http://localhost:8000")
WS_PUBLIC = os.environ.get("WS_PUBLIC", "ws://localhost:8000")


@dataclass
class StatusMsg:
    ts: float
    payload: dict


def api_post(path: str, **kwargs):
    return requests.post(f"{API_INTERNAL}{path}", timeout=60, **kwargs)


def api_get(path: str, **kwargs):
    return requests.get(f"{API_INTERNAL}{path}", timeout=60, **kwargs)


def ws_thread(video_id: str, stop_flag: threading.Event):
    def on_message(_ws, message: str):
        st.session_state.setdefault("status_log", [])
        try:
            import json

            payload = json.loads(message)
        except Exception:  # noqa: BLE001
            payload = {"raw": message}
        st.session_state["status_log"].append(StatusMsg(ts=time.time(), payload=payload))
        st.session_state["last_status"] = payload

    def on_error(_ws, error):
        st.session_state.setdefault("ws_errors", [])
        st.session_state["ws_errors"].append(str(error))

    url = f"{WS_INTERNAL}/ws/{video_id}"
    ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error)

    # run websocket in small loop so we can stop
    while not stop_flag.is_set():
        ws.run_forever(ping_interval=20, ping_timeout=10)
        time.sleep(1)


def start_ws(video_id: str):
    if st.session_state.get("ws_video_id") == video_id and st.session_state.get("ws_stop"):
        return
    stop = threading.Event()
    t = threading.Thread(target=ws_thread, args=(video_id, stop), daemon=True)
    st.session_state["ws_video_id"] = video_id
    st.session_state["ws_stop"] = stop
    st.session_state["ws_thread"] = t
    t.start()


def stop_ws():
    stop = st.session_state.get("ws_stop")
    if stop:
        stop.set()


st.set_page_config(page_title="Video Pipeline POC", layout="wide")
st.title("Video Pipeline POC (Upload → Segment → AI → Realtime)")

with st.sidebar:
    st.subheader("Settings")
    chunk_mb = st.number_input("Chunk size (MB)", min_value=5, max_value=200, value=25, step=5)
    parallel_upload = st.checkbox("Upload parts in parallel (async)", value=True)
    max_concurrency = st.number_input("Max parallel uploads", min_value=1, max_value=16, value=4, step=1)
    enable_md5 = st.checkbox("Enable per-part MD5 (Content-MD5)", value=True)
    compute_final_sha256 = st.checkbox("Compute final SHA256 (client-side)", value=True)
    auto_poll = st.checkbox("Poll status (fallback)", value=True)
    poll_seconds = st.number_input("Poll interval (s)", min_value=1, max_value=30, value=2, step=1)

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1) Upload")
    file = st.file_uploader("Choose a video file (mp4 recommended)", type=None)
    user_id = st.text_input("user_id (optional)", value="u1")

    if st.button("Start new upload", disabled=file is None):
        stop_ws()
        st.session_state.pop("status_log", None)
        st.session_state.pop("last_status", None)

        r = api_post(f"/videos?user_id={user_id}" if user_id else "/videos")
        r.raise_for_status()
        vid = r.json()["video_id"]
        st.session_state["video_id"] = vid

        init = api_post(
            f"/videos/{vid}/multipart/init",
            json={"content_type": "video/mp4", "file_size_bytes": len(file.getvalue())},
        )
        init.raise_for_status()
        up = init.json()["upload_id"]
        st.session_state["upload_id"] = up

        start_ws(vid)
        st.success(f"Created video_id={vid}")

    vid = st.session_state.get("video_id")
    upload_id = st.session_state.get("upload_id")
    if vid and upload_id and file is not None:
        st.caption(f"video_id: `{vid}`")
        st.caption(f"upload_id: `{upload_id}`")

        data = file.getvalue()
        chunk_size = int(chunk_mb * 1024 * 1024)
        total_parts = math.ceil(len(data) / chunk_size) or 1

        # Show chunk plan (how the file is split)
        st.markdown("**Chunk plan (multipart parts)**")
        chunk_rows = []
        for part_number in range(1, total_parts + 1):
            start = (part_number - 1) * chunk_size
            end = min(part_number * chunk_size, len(data))
            chunk_rows.append(
                {
                    "part_number": part_number,
                    "start_byte": start,
                    "end_byte_exclusive": end,
                    "size_bytes": end - start,
                    "size_mb": round((end - start) / (1024 * 1024), 2),
                }
            )
        st.dataframe(chunk_rows, use_container_width=True, hide_index=True)

        # Shared status map for UI updates during parallel upload
        upload_state: dict[int, dict] = {}
        upload_state_lock = threading.Lock()
        total_bytes = len(data)

        def _upload_one_part(part_number: int) -> dict:
            start = (part_number - 1) * chunk_size
            end = min(part_number * chunk_size, len(data))
            chunk = data[start:end]
            content_md5 = None
            if enable_md5:
                md5 = hashlib.md5(chunk).digest()  # noqa: S324 (POC integrity check)
                content_md5 = base64.b64encode(md5).decode("ascii")

            with upload_state_lock:
                upload_state[part_number] = {
                    "part_number": part_number,
                    "size_bytes": end - start,
                    "status": "UPLOADING",
                    "uploaded_pct": 0,
                }

            pr = api_post(
                f"/videos/{vid}/multipart/part-url",
                params={
                    "upload_id": upload_id,
                    "part_number": part_number,
                    **({"content_md5": content_md5} if content_md5 else {}),
                },
            )
            pr.raise_for_status()
            url = pr.json()["url"]
            headers = pr.json().get("headers") or {}

            put = requests.put(url, data=chunk, headers=headers, timeout=300)
            put.raise_for_status()
            etag = put.headers.get("ETag")
            if not etag:
                raise RuntimeError(f"Missing ETag for part {part_number}")
            with upload_state_lock:
                upload_state[part_number]["status"] = "DONE"
                upload_state[part_number]["uploaded_pct"] = 100
            return {"ETag": etag, "PartNumber": part_number}

        if st.button("Upload & Complete (multipart)"):
            parts: list[dict] = []
            progress = st.progress(0, text="Uploading parts…")
            status = st.empty()
            parts_table = st.empty()

            def render_table() -> None:
                with upload_state_lock:
                    rows = [
                        {
                            "part_number": pn,
                            "status": stt.get("status"),
                            "uploaded_pct": stt.get("uploaded_pct"),
                            "size_mb": round(stt.get("size_bytes", 0) / (1024 * 1024), 2),
                        }
                        for pn, stt in sorted(upload_state.items())
                    ]
                    done_bytes = sum(
                        stt.get("size_bytes", 0) for stt in upload_state.values() if stt.get("status") == "DONE"
                    )
                parts_table.dataframe(rows, use_container_width=True, hide_index=True)
                pct = int((done_bytes / max(total_bytes, 1)) * 100)
                progress.progress(pct, text=f"Uploaded {pct}% ({done_bytes}/{total_bytes} bytes)")

            # Initialize table as PENDING
            with upload_state_lock:
                for row in chunk_rows:
                    pn = int(row["part_number"])
                    upload_state[pn] = {
                        "part_number": pn,
                        "size_bytes": int(row["size_bytes"]),
                        "status": "PENDING",
                        "uploaded_pct": 0,
                    }
            render_table()

            if parallel_upload and total_parts > 1:
                status.info(f"Uploading {total_parts} parts in parallel (max {int(max_concurrency)} workers)…")
                with ThreadPoolExecutor(max_workers=int(max_concurrency)) as ex:
                    futures = [ex.submit(_upload_one_part, pn) for pn in range(1, total_parts + 1)]
                    pending = set(futures)
                    while pending:
                        done, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                        render_table()
                        for fut in done:
                            try:
                                part = fut.result()
                                parts.append(part)
                                status.write(f"Uploaded part {part['PartNumber']}/{total_parts}")
                            except Exception as e:  # noqa: BLE001
                                status.error(f"Part upload failed: {e}")
                                raise
            else:
                status.info(f"Uploading {total_parts} parts sequentially…")
                for part_number in range(1, total_parts + 1):
                    part = _upload_one_part(part_number)
                    parts.append(part)
                    render_table()
                    status.write(f"Uploaded part {part_number}/{total_parts}")

            # IMPORTANT: CompleteMultipartUpload expects parts sorted by PartNumber
            parts.sort(key=lambda p: int(p["PartNumber"]))

            comp = api_post(
                f"/videos/{vid}/multipart/complete",
                json={
                    "upload_id": upload_id,
                    "parts": parts,
                    "checksum": hashlib.sha256(data).hexdigest() if compute_final_sha256 else None,
                },
            )
            comp.raise_for_status()
            st.success("Upload completed and pipeline triggered.")

with col2:
    st.subheader("2) Status & Results")
    vid = st.session_state.get("video_id")
    if not vid:
        st.info("Upload a video to see status.")
    else:
        start_ws(vid)

        # Auto-refresh so websocket updates are reflected in UI without manual reload.
        with st.sidebar:
            auto_refresh = st.checkbox("Auto refresh UI (realtime)", value=True)
            refresh_seconds = st.number_input("UI refresh interval (s)", min_value=0.5, max_value=10.0, value=1.0, step=0.5)

        now = time.time()
        last_rerun = st.session_state.get("_last_rerun_ts", 0.0)
        if auto_refresh and (now - last_rerun) >= float(refresh_seconds):
            st.session_state["_last_rerun_ts"] = now
            # Trigger a rerun after rendering the page once.
            st.rerun()

        placeholder = st.empty()
        if auto_poll:
            # non-blocking-ish: only poll once per rerun
            try:
                v = api_get(f"/videos/{vid}")
                v.raise_for_status()
                st.session_state["video_snapshot"] = v.json()
            except Exception as e:  # noqa: BLE001
                st.warning(f"Polling failed: {e}")

            st.caption(f"Polling every {poll_seconds}s (Streamlit rerun required)")

        snap = st.session_state.get("video_snapshot")
        last = st.session_state.get("last_status")
        log = st.session_state.get("status_log", [])
        ws_errors = st.session_state.get("ws_errors", [])

        # Derive stage status from realtime messages
        stage_progress = {
            "UPLOAD": {"status": "PENDING", "progress": 0, "message": ""},
            "SEGMENT": {"status": "PENDING", "progress": 0, "message": ""},
            "AI": {"status": "PENDING", "progress": 0, "message": ""},
            "DONE": {"status": "PENDING", "progress": 0, "message": ""},
        }
        for item in log:
            payload = item.payload or {}
            stt = payload.get("status")
            prog = int(payload.get("progress", 0) or 0)
            msg = payload.get("message") or ""
            if stt in ("UPLOADED", "UPLOADING"):
                stage_progress["UPLOAD"] = {"status": stt, "progress": prog, "message": msg}
            elif stt in ("SEGMENTING", "SEGMENTED"):
                stage_progress["SEGMENT"] = {"status": stt, "progress": prog, "message": msg}
            elif stt in ("AI_PROCESSING",):
                stage_progress["AI"] = {"status": stt, "progress": prog, "message": msg}
            elif stt in ("DONE", "FAILED"):
                stage_progress["DONE"] = {"status": stt, "progress": prog, "message": msg}

        # Fallback: if websocket is not delivering (common in Streamlit threads),
        # derive stage from DB snapshot so the UI doesn't stay "PENDING".
        if snap and all(v["status"] == "PENDING" for v in stage_progress.values()):
            stt = (snap.get("status") or "").upper()
            if stt in ("UPLOADING", "UPLOADED"):
                stage_progress["UPLOAD"] = {"status": stt, "progress": 5 if stt == "UPLOADED" else 1, "message": ""}
            elif stt in ("SEGMENTING", "SEGMENTED"):
                stage_progress["UPLOAD"] = {"status": "UPLOADED", "progress": 5, "message": ""}
                stage_progress["SEGMENT"] = {"status": stt, "progress": 70 if stt == "SEGMENTED" else 30, "message": ""}
            elif stt in ("AI_PROCESSING",):
                stage_progress["UPLOAD"] = {"status": "UPLOADED", "progress": 5, "message": ""}
                stage_progress["SEGMENT"] = {"status": "SEGMENTED", "progress": 70, "message": ""}
                stage_progress["AI"] = {"status": stt, "progress": 85, "message": ""}
            elif stt in ("DONE", "FAILED"):
                stage_progress["UPLOAD"] = {"status": "UPLOADED", "progress": 5, "message": ""}
                stage_progress["SEGMENT"] = {"status": "SEGMENTED", "progress": 70, "message": ""}
                stage_progress["AI"] = {"status": "AI_PROCESSING", "progress": 95, "message": ""}
                stage_progress["DONE"] = {"status": stt, "progress": 100 if stt == "DONE" else 100, "message": ""}

        with placeholder.container():
            st.markdown("**Realtime stages (workers progress)**")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Upload", stage_progress["UPLOAD"]["status"])
            c1.progress(max(0, min(100, int(stage_progress["UPLOAD"]["progress"]))))
            if stage_progress["UPLOAD"]["message"]:
                c1.caption(stage_progress["UPLOAD"]["message"])

            c2.metric("Segment worker", stage_progress["SEGMENT"]["status"])
            c2.progress(max(0, min(100, int(stage_progress["SEGMENT"]["progress"]))))
            if stage_progress["SEGMENT"]["message"]:
                c2.caption(stage_progress["SEGMENT"]["message"])

            c3.metric("AI worker", stage_progress["AI"]["status"])
            c3.progress(max(0, min(100, int(stage_progress["AI"]["progress"]))))
            if stage_progress["AI"]["message"]:
                c3.caption(stage_progress["AI"]["message"])

            c4.metric("Final", stage_progress["DONE"]["status"])
            c4.progress(max(0, min(100, int(stage_progress["DONE"]["progress"]))))
            if stage_progress["DONE"]["message"]:
                c4.caption(stage_progress["DONE"]["message"])

            if ws_errors:
                st.warning(f"WebSocket errors (latest): {ws_errors[-1]}")

            if last:
                st.markdown("**Latest realtime status**")
                st.json(last)
                prog = int(last.get("progress", 0))
                st.progress(max(0, min(100, prog)))

            if snap:
                st.markdown("**DB snapshot**")
                st.write(f"Status: **{snap.get('status')}**")
                st.caption("DB shows persisted state; realtime stages show live progress events.")

                # Show original video (local upload) as fallback
                if file is not None:
                    st.markdown("**Original video (local preview)**")
                    st.video(file.getvalue())

                segments = snap.get("segments") or []
                st.markdown(f"**Segments** ({len(segments)})")
                if segments:
                    for s in segments[:10]:
                        st.write(f"- `{s['segment_id']}` [{s['start_time']:.1f}–{s['end_time']:.1f}]")

                    # Preview first segment via presigned GET
                    first = segments[0]
                    # path like s3://bucket/key
                    path = first["path"]
                    key = path.split("/", 3)[-1]
                    pg = api_get("/objects/presign-get", params={"key": key})
                    if pg.ok:
                        st.markdown("**Preview first segment (MinIO presigned GET)**")
                        st.video(pg.json()["url"])
                else:
                    st.caption("No segments yet.")

                tags = snap.get("tags") or []
                st.markdown(f"**Tags** ({len(tags)})")
                if tags:
                    st.dataframe(tags, use_container_width=True)

        st.markdown("**Realtime log (last 50)**")
        for item in log[-50:]:
            st.write(item.payload)

        st.button("Stop WebSocket", on_click=stop_ws)

