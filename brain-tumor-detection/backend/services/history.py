"""SQLite-backed prediction history with JPEG thumbnails on disk.

Only derived data is stored: a small thumbnail, the result, and a SHA-256 of the
original file. The full-resolution upload is deleted after inference.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from PIL import Image

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    source_format     TEXT NOT NULL,
    width             INTEGER NOT NULL,
    height            INTEGER NOT NULL,
    size_bytes        INTEGER NOT NULL,
    image_sha256      TEXT NOT NULL,
    predicted_class   TEXT NOT NULL,
    tumor_detected    INTEGER NOT NULL,
    confidence        REAL NOT NULL,
    low_confidence    INTEGER NOT NULL,
    probabilities     TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    inference_ms      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions (created_at DESC);
"""


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def make_thumbnail(image: Image.Image, max_side: int = 384) -> bytes:
    """Return a JPEG thumbnail of ``image`` (RGB) whose longest side is at most ``max_side``."""
    thumb = image.copy()
    thumb.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    thumb.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


class PredictionHistory:
    def __init__(self, database_path: Path, thumbnails_dir: Path) -> None:
        self.database_path = Path(database_path)
        self.thumbnails_dir = Path(thumbnails_dir)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:  # commit or roll back
                yield conn
        finally:
            conn.close()

    def _thumbnail_path(self, prediction_id: str) -> Path:
        return self.thumbnails_dir / f"{prediction_id}.jpg"

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["tumor_detected"] = bool(data["tumor_detected"])
        data["low_confidence"] = bool(data["low_confidence"])
        data["probabilities"] = json.loads(data["probabilities"])
        return data

    def add(self, record: dict[str, Any], thumbnail_jpeg: bytes) -> dict[str, Any]:
        prediction_id = uuid.uuid4().hex
        row = {
            "id": prediction_id,
            **record,
            "probabilities": json.dumps(record["probabilities"]),
            "tumor_detected": int(record["tumor_detected"]),
            "low_confidence": int(record["low_confidence"]),
        }
        columns = ", ".join(row)
        placeholders = ", ".join(f":{k}" for k in row)
        with self._connect() as conn:
            conn.execute(f"INSERT INTO predictions ({columns}) VALUES ({placeholders})", row)
        self._thumbnail_path(prediction_id).write_bytes(thumbnail_jpeg)
        return self.get(prediction_id) or {}

    def get(self, prediction_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_page(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM predictions ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows], int(total)

    def thumbnail_path(self, prediction_id: str) -> Path | None:
        path = self._thumbnail_path(prediction_id)
        return path if path.is_file() else None

    def delete(self, prediction_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM predictions WHERE id = ?", (prediction_id,))
            deleted = cursor.rowcount > 0
        self._thumbnail_path(prediction_id).unlink(missing_ok=True)
        return deleted

    def clear(self) -> int:
        with self._connect() as conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM predictions").fetchall()]
            conn.execute("DELETE FROM predictions")
        for prediction_id in ids:
            self._thumbnail_path(prediction_id).unlink(missing_ok=True)
        return len(ids)
