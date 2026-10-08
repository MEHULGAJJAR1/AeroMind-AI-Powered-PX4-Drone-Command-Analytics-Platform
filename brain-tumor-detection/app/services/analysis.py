"""Orchestration: upload → validate → preprocess → inference → history."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from flask import Request

from app.config import Config
from app.core.logging import get_logger
from app.ml.predictor import Predictor
from app.services.history import HistoryStore, make_thumbnail_data_uri
from app.services.validation import ValidatedUpload, decode_image, unique_upload_path, validate_upload


def file_hash(data: bytes, algorithm: str = "sha256") -> str:
    return hashlib.new(algorithm, data).hexdigest()


def analyze_request(
    request: Request,
    *,
    config: Config,
    predictor: Predictor,
    history: HistoryStore | None,
    notes: str | None = None,
    include_preprocessed: bool = False,
    save_history: bool = True,
) -> dict[str, Any]:
    """Run the full analysis pipeline for one uploaded image."""
    started = time.perf_counter()

    upload: ValidatedUpload = validate_upload(request, config)
    image = decode_image(upload, config)
    digest = file_hash(upload.raw)

    if not predictor.is_loaded:
        # Checked before inference so the client gets 503 (not a 500) with a fix hint.
        predictor.load()

    result = predictor.predict(image, include_preprocessed=include_preprocessed)
    payload = result.to_dict()

    payload["image"] = {
        "filename": upload.filename,
        "safe_name": upload.safe_name,
        "content_type": upload.content_type,
        "size_bytes": upload.size,
        "size_mb": upload.size_mb,
        "width": image.size[0],
        "height": image.size[1],
        "sha256": digest,
    }
    payload["request"] = {
        "total_ms": round((time.perf_counter() - started) * 1000, 2),
        "notes": notes or None,
    }

    if save_history and history is not None:
        upload_path = _store_upload(upload, config, digest[:12]) if config.keep_uploads else None
        thumbnail = make_thumbnail_data_uri(image)
        record = history.add(
            {
                "filename": upload.filename,
                "content_type": upload.content_type,
                "size_bytes": upload.size,
                "width": image.size[0],
                "height": image.size[1],
                "prediction": result.label,
                "is_tumor": result.is_tumor,
                "confidence": result.confidence,
                "uncertain": result.uncertain,
                "probabilities": result.probabilities,
                "latency_ms": result.timing["total_ms"],
                "model": {"name": payload["model"]["name"], "device": payload["model"]["device"]},
                "image_hash": digest,
                "notes": notes,
                "thumbnail": thumbnail,
                "upload_path": str(upload_path) if upload_path else None,
            }
        )
        payload["history_id"] = record.id
        payload["history"] = record.to_dict(include_thumbnail=False)
        get_logger().info(
            "Prediction %s: %s (confidence=%.3f) for %s",
            record.id[:8],
            result.label,
            result.confidence,
            upload.filename,
        )

    return payload


def _store_upload(upload: ValidatedUpload, config: Config, identifier: str):
    try:
        path = unique_upload_path(config.upload_dir, upload.safe_name, identifier)
        path.write_bytes(upload.raw)
        return path
    except OSError as exc:  # pragma: no cover - disk issues must not fail the prediction
        get_logger().warning("Could not persist upload %s: %s", upload.safe_name, exc)
        return None
