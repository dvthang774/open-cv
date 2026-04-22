from __future__ import annotations

from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from app.domain.entities.segment import Segment
from app.domain.entities.video import Video
from app.domain.repositories.video_repo import VideoRepo


class PostgresVideoRepo(VideoRepo):
    def __init__(self, *, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def ensure_schema(self) -> None:
        from app.infrastructure.persistence.migrations_sql import MIGRATIONS

        # Prevent concurrent migrations across multiple containers.
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(424242);")
            try:
                cur.execute(MIGRATIONS)
            finally:
                cur.execute("SELECT pg_advisory_unlock(424242);")

    def create_video(self, video_id: str, raw_path: str) -> Video:
        now = datetime.now(timezone.utc)
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO videos(video_id, raw_path, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (video_id) DO NOTHING
                """,
                (video_id, raw_path, "UPLOADING", now, now),
            )
        v = self.get_video(video_id)
        assert v is not None
        return v

    def get_video(self, video_id: str) -> Video | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT video_id, raw_path, status, checksum, created_at, updated_at FROM videos WHERE video_id=%s",
                (video_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return Video(
                video_id=row[0],
                raw_path=row[1],
                status=row[2],
                checksum=row[3],
                created_at=row[4],
                updated_at=row[5],
            )

    def set_status(self, video_id: str, status: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE videos SET status=%s, updated_at=now() WHERE video_id=%s",
                (status, video_id),
            )

    def transition_status(self, *, video_id: str, from_status: str, to_status: str) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE videos
                SET status=%s, updated_at=now()
                WHERE video_id=%s AND status=%s
                """,
                (to_status, video_id, from_status),
            )
            return cur.rowcount == 1

    def set_user_id(self, *, video_id: str, user_id: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE videos SET user_id=%s, updated_at=now() WHERE video_id=%s",
                (user_id, video_id),
            )

    def set_checksum(self, *, video_id: str, checksum: str | None) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE videos SET checksum=%s, updated_at=now() WHERE video_id=%s",
                (checksum, video_id),
            )

    def upsert_segments(self, segments: list[Segment]) -> None:
        if not segments:
            return
        with self._conn() as conn, conn.cursor() as cur:
            for s in segments:
                cur.execute(
                    """
                    INSERT INTO segments(segment_id, video_id, start_time, end_time, path)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (segment_id, video_id)
                    DO UPDATE SET start_time=EXCLUDED.start_time, end_time=EXCLUDED.end_time, path=EXCLUDED.path
                    """,
                    (s.segment_id, s.video_id, s.start_time, s.end_time, s.path),
                )

    def list_segments(self, video_id: str) -> list[Segment]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT segment_id, video_id, start_time, end_time, path
                FROM segments
                WHERE video_id=%s
                ORDER BY start_time ASC
                """,
                (video_id,),
            )
            rows = cur.fetchall()
            return [
                Segment(
                    segment_id=r[0],
                    video_id=r[1],
                    start_time=float(r[2]),
                    end_time=float(r[3]),
                    path=r[4],
                )
                for r in rows
            ]

    def insert_tags(self, *, video_id: str, segment_id: str, tags: list[tuple[str, float]]) -> None:
        if not tags:
            return
        with self._conn() as conn, conn.cursor() as cur:
            for label, conf in tags:
                cur.execute(
                    "INSERT INTO tags(video_id, segment_id, label, confidence) VALUES (%s, %s, %s, %s)",
                    (video_id, segment_id, label, conf),
                )

    def list_tags(self, video_id: str) -> list[dict]:
        with self._conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT segment_id, label, confidence, created_at
                FROM tags
                WHERE video_id=%s
                ORDER BY created_at ASC
                """,
                (video_id,),
            )
            return list(cur.fetchall())

    def mark_event_processed(self, *, consumer: str, event_id: str) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processed_events(consumer, event_id)
                VALUES (%s, %s)
                ON CONFLICT (consumer, event_id) DO NOTHING
                """,
                (consumer, event_id),
            )
            return cur.rowcount == 1

