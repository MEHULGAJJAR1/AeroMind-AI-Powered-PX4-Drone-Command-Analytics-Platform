"""SQLite-backed prediction history.

The standard-library ``sqlite3`` module is used directly (no ORM) — the schema is
three columns of metadata plus a few reporting fields, and the store must work
with zero extra setup. A connection is opened per operation, which keeps the
store safe to use from Flask's worker threads.
"""

from __future__ import annotations

import base64
import io
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from PIL import Image

SCHEMA_VERSION = 1
THUMBNAIL_SIZE = (96, 96)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    created_ts     REAL NOT NULL,
    filename       TEXT NOT NULL,
    content_type   TEXT,
    size_bytes     INTEGER,
    width          INTEGER,
    height         INTEGER,
    prediction     TEXT NOT NULL,
    is_tumor       INTEGER NOT NULL,
    confidence     REAL NOT NULL,
    uncertain      INTEGER NOT NULL DEFAULT 0,
    probabilities  TEXT,
    latency_ms     REAL,
    model_name     TEXT,
    device         TEXT,
    image_hash     TEXT,
    notes          TEXT,
    thumbnail      TEXT,
    upload_path    TEXT
);

CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions (created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_label ON predictions (prediction);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


@dataclass
class PredictionRecord:
    """One row of prediction history."""

    id: str
    created_at: str
    created_ts: float
    filename: str
    content_type: str | None
    size_bytes: int | None
    width: int | None
    height: int | None
    prediction: str
    is_tumor: bool
    confidence: float
    uncertain: bool
    probabilities: dict[str, float]
    latency_ms: float | None
    model_name: str | None
    device: str | None
    image_hash: str | None
    notes: str | None
    thumbnail: str | None
    upload_path: str | None

    def to_dict(self, *, include_thumbnail: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "created_at": self.created_at,
            "created_ts": self.created_ts,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / (1024 * 1024), 3) if self.size_bytes else None,
            "width": self.width,
            "height": self.height,
            "prediction": {
                "label": self.prediction,
                "display_name": "Tumor detected" if self.is_tumor else "No tumor detected",
                "is_tumor": self.is_tumor,
                "confidence": self.confidence,
                "probabilities": self.probabilities,
                "uncertain": self.uncertain,
            },
            "latency_ms": self.latency_ms,
            "model": {"name": self.model_name, "device": self.device},
            "image_hash": self.image_hash,
            "notes": self.notes,
            "thumbnail": self.thumbnail if include_thumbnail else None,
        }
        return payload


def _row_to_record(row: sqlite3.Row, *, include_thumbnail: bool = True) -> PredictionRecord:
    probabilities: dict[str, float] = {}
    try:
        probabilities = json.loads(row["probabilities"] or "{}")
    except json.JSONDecodeError:  # pragma: no cover - defensive
        probabilities = {}
    return PredictionRecord(
        id=row["id"],
        created_at=row["created_at"],
        created_ts=row["created_ts"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        width=row["width"],
        height=row["height"],
        prediction=row["prediction"],
        is_tumor=bool(row["is_tumor"]),
        confidence=row["confidence"],
        uncertain=bool(row["uncertain"]),
        probabilities=probabilities,
        latency_ms=row["latency_ms"],
        model_name=row["model_name"],
        device=row["device"],
        image_hash=row["image_hash"],
        notes=row["notes"],
        thumbnail=row["thumbnail"] if include_thumbnail else None,
        upload_path=row["upload_path"],
    )


def make_thumbnail_data_uri(image: Image.Image, size: tuple[int, int] = THUMBNAIL_SIZE) -> str | None:
    """Small base64 JPEG data URI so the history list renders without extra requests."""
    try:
        thumb = image.convert("RGB").copy()
        thumb.thumbnail(size, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        thumb.save(buffer, format="JPEG", quality=72, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:  # pragma: no cover - thumbnails are best effort
        return None


class HistoryStore:
    """Thread-safe CRUD store for prediction history."""

    def __init__(self, db_path: str | Path, *, max_rows: int = 500) -> None:
        self.db_path = Path(db_path)
        self.max_rows = int(max_rows)
        self._write_lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    # ------------------------------------------------------------------ #
    # Plumbing
    # ------------------------------------------------------------------ #
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute("PRAGMA synchronous=NORMAL;")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._write_lock, self._connect() as connection:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def add(self, record: dict[str, Any]) -> PredictionRecord:
        """Insert one prediction. Returns the stored record."""
        now = time.time()
        record_id = record.get("id") or uuid.uuid4().hex
        created_at = record.get("created_at") or datetime.now(timezone.utc).isoformat()

        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO predictions (
                    id, created_at, created_ts, filename, content_type, size_bytes,
                    width, height, prediction, is_tumor, confidence, uncertain,
                    probabilities, latency_ms, model_name, device, image_hash, notes,
                    thumbnail, upload_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    created_at,
                    now,
                    record.get("filename") or "upload",
                    record.get("content_type"),
                    record.get("size_bytes"),
                    record.get("width"),
                    record.get("height"),
                    record.get("prediction") or "unknown",
                    1 if record.get("is_tumor") else 0,
                    float(record.get("confidence") or 0.0),
                    1 if record.get("uncertain") else 0,
                    json.dumps(record.get("probabilities") or {}),
                    record.get("latency_ms"),
                    (record.get("model") or {}).get("name"),
                    (record.get("model") or {}).get("device"),
                    record.get("image_hash"),
                    record.get("notes"),
                    record.get("thumbnail"),
                    record.get("upload_path"),
                ),
            )
            row = connection.execute("SELECT * FROM predictions WHERE id = ?", (record_id,)).fetchone()
            if self.max_rows > 0:
                self._prune(connection)
            return _row_to_record(row)

    def _prune(self, connection: sqlite3.Connection) -> None:
        overflow = connection.execute(
            "SELECT id, upload_path FROM predictions ORDER BY created_ts DESC LIMIT -1 OFFSET ?",
            (self.max_rows,),
        ).fetchall()
        for row in overflow:
            connection.execute("DELETE FROM predictions WHERE id = ?", (row["id"],))

    def delete(self, record_id: str, *, remove_upload: bool = True) -> bool:
        with self._write_lock, self._connect() as connection:
            row = connection.execute("SELECT upload_path FROM predictions WHERE id = ?", (record_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM predictions WHERE id = ?", (record_id,))
        if remove_upload and row["upload_path"]:
            self._delete_file(row["upload_path"])
        return True

    def clear(self, *, remove_uploads: bool = True) -> int:
        with self._write_lock, self._connect() as connection:
            rows = connection.execute("SELECT upload_path FROM predictions").fetchall()
            deleted = connection.execute("DELETE FROM predictions").rowcount
        if remove_uploads:
            for row in rows:
                if row["upload_path"]:
                    self._delete_file(row["upload_path"])
        return int(deleted or 0)

    @staticmethod
    def _delete_file(path: str) -> None:
        try:
            target = Path(path)
            if target.is_file():
                target.unlink()
        except OSError:  # pragma: no cover - best effort cleanup
            pass

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, record_id: str) -> PredictionRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM predictions WHERE id = ?", (record_id,)).fetchone()
        return _row_to_record(row) if row else None

    def list(self, *, limit: int = 20, offset: int = 0, include_thumbnails: bool = True) -> list[PredictionRecord]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM predictions ORDER BY created_ts DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_record(row, include_thumbnail=include_thumbnails) for row in rows]

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0])

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            tumor = connection.execute("SELECT COUNT(*) FROM predictions WHERE is_tumor = 1").fetchone()[0]
            averages = connection.execute(
                "SELECT AVG(confidence), AVG(latency_ms) FROM predictions"
            ).fetchone()
            by_label = connection.execute(
                "SELECT prediction, COUNT(*) AS n FROM predictions GROUP BY prediction ORDER BY n DESC"
            ).fetchall()
            last = connection.execute("SELECT created_at FROM predictions ORDER BY created_ts DESC LIMIT 1").fetchone()

        return {
            "total": int(total),
            "tumor_detected": int(tumor),
            "no_tumor": int(total) - int(tumor),
            "tumor_rate": round(int(tumor) / int(total), 4) if total else 0.0,
            "average_confidence": round(float(averages[0]), 4) if averages[0] is not None else None,
            "average_latency_ms": round(float(averages[1]), 2) if averages[1] is not None else None,
            "by_label": {row["prediction"]: int(row["n"]) for row in by_label},
            "last_prediction_at": last["created_at"] if last else None,
        }
