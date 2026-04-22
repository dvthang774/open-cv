from __future__ import annotations

import os
import subprocess

from app.application.interfaces.segmenter import Segmenter


class FfmpegSegmenter(Segmenter):
    def segment(
        self, *, input_path: str, output_dir: str, segment_seconds: int
    ) -> list[dict]:
        os.makedirs(output_dir, exist_ok=True)
        pattern = os.path.join(output_dir, "seg_%04d.mp4")

        # POC: simple time-based segmentation
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-c",
            "copy",
            "-map",
            "0",
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            pattern,
        ]
        subprocess.run(cmd, check=True)

        files = sorted(f for f in os.listdir(output_dir) if f.endswith(".mp4"))
        out: list[dict] = []
        for idx, fname in enumerate(files, start=1):
            start = (idx - 1) * float(segment_seconds)
            end = idx * float(segment_seconds)
            out.append(
                {
                    "segment_id": f"s{idx:04d}",
                    "start_time": start,
                    "end_time": end,
                    "local_path": os.path.join(output_dir, fname),
                }
            )
        return out

