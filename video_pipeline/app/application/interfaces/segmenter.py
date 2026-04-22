from __future__ import annotations

from abc import ABC, abstractmethod


class Segmenter(ABC):
    @abstractmethod
    def segment(
        self, *, input_path: str, output_dir: str, segment_seconds: int
    ) -> list[dict]:
        """
        Returns list of dicts: {segment_id, start_time, end_time, local_path}
        """

