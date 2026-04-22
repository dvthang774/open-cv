from __future__ import annotations

import os
import random
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

from app.application.interfaces.event_bus import EventBus
from app.application.interfaces.storage import Storage
from app.config import Settings
from app.domain.repositories.video_repo import VideoRepo


class ProcessAI:
    """
    AI stage.

    Modes:
    - stub (default): random tags
    - yolo: run Ultralytics YOLO segmentation on each segment video
    """

    TAG_POOL = ["person", "car", "text", "logo", "animal", "bicycle"]

    def __init__(self, *, repo: VideoRepo, storage: Storage, bus: EventBus, settings: Settings):
        self.repo = repo
        self.storage = storage
        self.bus = bus
        self.settings = settings

    def _ai_mode(self) -> str:
        return os.getenv("VP_AI_MODE", "stub").lower()

    def _qf_enabled(self) -> bool:
        return os.getenv("VP_QF_ENABLE", "1").strip() not in ("0", "false", "False", "no", "NO")

    def _qf_sample_frames(self) -> int:
        try:
            return max(1, int(os.getenv("VP_QF_SAMPLE_FRAMES", "3")))
        except Exception:
            return 3

    def _qf_dark_threshold(self) -> float:
        # 0..255 (mean luma). Lower means darker.
        try:
            return float(os.getenv("VP_QF_DARK_THRESHOLD", "35"))
        except Exception:
            return 35.0

    def _qf_blur_threshold(self) -> float:
        # Higher means sharper (variance of Laplacian on grayscale).
        try:
            return float(os.getenv("VP_QF_BLUR_THRESHOLD", "60"))
        except Exception:
            return 60.0

    def _qf_skip_on_fail(self) -> bool:
        return os.getenv("VP_QF_SKIP_ON_FAIL", "1").strip() not in ("0", "false", "False", "no", "NO")

    def _extract_frames(self, *, video_path: str, out_dir: str, num_frames: int) -> list[str]:
        """
        Extract ~num_frames evenly from the video using ffmpeg.
        Returns list of local jpg paths.
        """
        os.makedirs(out_dir, exist_ok=True)
        pattern = os.path.join(out_dir, "frame_%03d.jpg")
        # This uses fps filter to sample frames; it's approximate but good for POC.
        # We sample at most `num_frames` by limiting with -vframes.
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-vf",
            "fps=1",  # 1 frame per second; we'll cap with -vframes
            "-vframes",
            str(num_frames),
            pattern,
        ]
        subprocess.run(cmd, check=True)
        files = sorted(
            os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.lower().endswith(".jpg")
        )
        return files

    def _quality_metrics_from_image(self, img_path: str) -> tuple[float, float]:
        """
        Returns (brightness_mean_0_255, blur_score_laplacian_var).
        Uses PIL + numpy-style operations without requiring OpenCV.
        """
        from PIL import Image
        import numpy as np

        img = Image.open(img_path).convert("L")  # grayscale
        a = np.asarray(img, dtype=np.float32)
        brightness = float(a.mean())
        # Laplacian variance (simple 3x3 kernel)
        k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        ap = np.pad(a, 1, mode="edge")
        lap = (
            k[0, 0] * ap[:-2, :-2]
            + k[0, 1] * ap[:-2, 1:-1]
            + k[0, 2] * ap[:-2, 2:]
            + k[1, 0] * ap[1:-1, :-2]
            + k[1, 1] * ap[1:-1, 1:-1]
            + k[1, 2] * ap[1:-1, 2:]
            + k[2, 0] * ap[2:, :-2]
            + k[2, 1] * ap[2:, 1:-1]
            + k[2, 2] * ap[2:, 2:]
        )
        blur_score = float(lap.var())
        return brightness, blur_score

    def _quality_filter(self, *, local_video_path: str, duration: float) -> dict:
        """
        Returns a dict with quality metrics and pass/fail.
        """
        num = self._qf_sample_frames()
        with tempfile.TemporaryDirectory(prefix="vp_qf_") as td:
            frames = self._extract_frames(video_path=local_video_path, out_dir=td, num_frames=num)
            brightness_vals: list[float] = []
            blur_vals: list[float] = []
            for fp in frames:
                b, s = self._quality_metrics_from_image(fp)
                brightness_vals.append(b)
                blur_vals.append(s)

        brightness_mean = sum(brightness_vals) / max(len(brightness_vals), 1)
        blur_mean = sum(blur_vals) / max(len(blur_vals), 1)

        is_dark = brightness_mean < self._qf_dark_threshold()
        is_blurry = blur_mean < self._qf_blur_threshold()
        passed = (not is_dark) and (not is_blurry)
        return {
            "enabled": True,
            "sample_frames": num,
            "brightness_mean": round(brightness_mean, 3),
            "blur_score_mean": round(blur_mean, 3),
            "dark_threshold": self._qf_dark_threshold(),
            "blur_threshold": self._qf_blur_threshold(),
            "is_dark": is_dark,
            "is_blurry": is_blurry,
            "passed": passed,
            "duration": round(duration, 3),
        }

    def _run_yolo_on_segment(self, *, local_video_path: str) -> tuple[list[str], list[float], dict]:
        """
        Returns (tags, confidences, debug_payload).
        """
        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "Ultralytics is not installed. Add `ultralytics` (and torch) to dependencies "
                "or use VP_AI_MODE=stub."
            ) from e

        model_path = os.getenv("VP_YOLO_MODEL", "yolo26x-seg.pt")
        classes_env = os.getenv("VP_YOLO_CLASSES", "")
        classes = [int(x) for x in classes_env.split(",") if x.strip().isdigit()] or None
        device = os.getenv("VP_YOLO_DEVICE", "0")

        model = YOLO(model_path)
        results = model.predict(
            source=local_video_path,
            save=False,
            show=False,
            classes=classes,
            device=device,
        )

        # Aggregate detections across frames
        best_conf: dict[str, float] = {}
        total_frames = len(results)
        for r in results:
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue
            cls_ids = getattr(boxes, "cls", None)
            confs = getattr(boxes, "conf", None)
            if cls_ids is None or confs is None:
                continue
            for cls_id, conf in zip(cls_ids.tolist(), confs.tolist(), strict=False):
                name = model.names.get(int(cls_id), str(int(cls_id)))
                prev = best_conf.get(name, 0.0)
                if float(conf) > prev:
                    best_conf[name] = float(conf)

        # Sort by confidence desc
        items = sorted(best_conf.items(), key=lambda kv: kv[1], reverse=True)
        tags = [k for k, _ in items]
        confidences = [round(v, 4) for _, v in items]
        debug = {
            "model": model_path,
            "classes_filter": classes,
            "device": device,
            "frames_processed": total_frames,
            "detections_unique_classes": len(items),
        }
        return tags, confidences, debug

    async def run(self, *, event: dict) -> dict:
        video_id = event["video_id"]
        segments = event.get("segments", [])

        self.repo.set_status(video_id, "AI_PROCESSING")
        await self.bus.publish(
            topic="video.status",
            key=video_id,
            event={"video_id": video_id, "status": "AI_PROCESSING", "progress": 75, "message": "Starting AI"},
        )

        completed: list[dict] = []
        total = max(len(segments), 1)
        for seg in segments:
            segment_id = seg["id"]
            start_time = float(seg.get("start", 0.0))
            end_time = float(seg.get("end", 0.0))
            duration = max(0.0, end_time - start_time)
            mode = self._ai_mode()
            # seg["path"] is s3://bucket/key
            s3_path = seg.get("path") or ""
            key = s3_path.split("/", 3)[-1] if s3_path.startswith("s3://") else s3_path
            with tempfile.TemporaryDirectory(prefix="vp_ai_") as td:
                local_path = os.path.join(td, f"{segment_id}.mp4")
                self.storage.download_to_file(key=key, local_path=local_path)

                quality = {"enabled": False}
                if self._qf_enabled():
                    try:
                        quality = self._quality_filter(local_video_path=local_path, duration=duration)
                    except Exception as e:  # noqa: BLE001
                        quality = {"enabled": True, "error": repr(e), "passed": True}

                qf_failed = bool(quality.get("enabled")) and (quality.get("passed") is False)
                if qf_failed and self._qf_skip_on_fail():
                    tags = ["low_quality"]
                    scores = [1.0]
                    debug = {"mode": mode, "skipped": "quality_filter_failed"}
                else:
                    if mode == "yolo":
                        tags, scores, debug = self._run_yolo_on_segment(local_video_path=local_path)
                    else:
                        tags = random.sample(self.TAG_POOL, k=min(2, len(self.TAG_POOL)))
                        scores = [round(random.uniform(0.7, 0.99), 2) for _ in tags]
                        debug = {"mode": "stub"}

                    if qf_failed and "low_quality" not in tags:
                        tags = ["low_quality", *tags]
                        scores = [1.0, *scores]

            meta = {
                "video_id": video_id,
                "segment_id": segment_id,
                "timestamp": start_time,
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "tags": tags,
                "confidence": scores,
                "quality": quality,
                "debug": debug,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            meta_key = f"metadata/{video_id}/segments/{segment_id}.json"
            self.storage.put_json(key=meta_key, data=meta)

            self.repo.insert_tags(
                video_id=video_id,
                segment_id=segment_id,
                tags=list(zip(tags, scores, strict=False)),
            )

            out = {
                "event_id": str(uuid.uuid4()),
                "video_id": video_id,
                "type": "SEGMENT_AI_COMPLETED",
                "segment_id": segment_id,
                "timestamp": start_time,
                "duration": duration,
                "tags": tags,
                "confidence": scores,
                "created_at": meta["created_at"],
            }
            await self.bus.publish(topic="video.ai.completed", key=video_id, event=out)
            completed.append(out)
            await self.bus.publish(
                topic="video.status",
                key=video_id,
                event={
                    "video_id": video_id,
                    "status": "AI_PROCESSING",
                    "progress": 75 + int((len(completed) / total) * 20),
                    "message": f"AI processed {len(completed)}/{total}",
                },
            )

        self.repo.set_status(video_id, "DONE")
        final = {
            "event_id": str(uuid.uuid4()),
            "video_id": video_id,
            "status": "DONE",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "segments_processed": len(segments),
        }
        await self.bus.publish(
            topic="video.status",
            key=video_id,
            event={"video_id": video_id, "status": "DONE", "progress": 100, "message": "Completed"},
        )
        await self.bus.publish(topic="video.finalized", key=video_id, event=final)
        return {"final": final, "ai_events": completed}

