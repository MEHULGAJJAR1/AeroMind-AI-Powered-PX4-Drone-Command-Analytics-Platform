"""REST API. All routes live under ``/api``.

    GET    /api/health                      liveness and model status
    GET    /api/model                       model metadata
    POST   /api/uploads                     multipart upload -> validated upload_id
    POST   /api/predictions                 {"upload_id"} -> inference result (persisted)
    GET    /api/predictions                 paginated history
    GET    /api/predictions/<id>            one prediction
    GET    /api/predictions/<id>/thumbnail  JPEG thumbnail
    DELETE /api/predictions/<id>            delete one prediction
    DELETE /api/predictions                 clear the history
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from ml.constants import CLASS_DISPLAY_NAMES

from .errors import ApiError
from .services.history import make_thumbnail, utc_now_iso
from .services.validation import sanitize_filename, validate_upload

logger = logging.getLogger(__name__)
api = Blueprint("api", __name__, url_prefix="/api")

DISCLAIMER = (
    "For research and educational use only. This is not a medical device and does not replace "
    "diagnosis by a qualified radiologist or clinician."
)


def _services():
    return current_app.extensions["btd"]


def _format_prediction(row: dict[str, Any]) -> dict[str, Any]:
    """Public JSON representation of a stored prediction."""
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "original_filename": row["original_filename"],
        "source_format": row["source_format"],
        "width": row["width"],
        "height": row["height"],
        "size_bytes": row["size_bytes"],
        "predicted_class": row["predicted_class"],
        "predicted_label": CLASS_DISPLAY_NAMES.get(row["predicted_class"], row["predicted_class"]),
        "tumor_detected": row["tumor_detected"],
        "confidence": row["confidence"],
        "low_confidence": row["low_confidence"],
        "probabilities": row["probabilities"],
        "model_version": row["model_version"],
        "inference_ms": row["inference_ms"],
        "thumbnail_url": f"/api/predictions/{row['id']}/thumbnail",
    }


def _parse_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiError(400, "INVALID_QUERY", f"'{name}' must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise ApiError(400, "INVALID_QUERY", f"'{name}' must be between {minimum} and {maximum}.")
    return value


@api.get("/health")
def health() -> Response:
    services = _services()
    return jsonify({
        "status": "ok",
        "model_loaded": services.models.is_ready,
        "model_version": services.models.version,
    })


@api.get("/model")
def model_info() -> Response:
    return jsonify(_services().models.describe())


@api.post("/uploads")
def create_upload() -> tuple[Response, int]:
    services = _services()
    file = request.files.get("file")
    if file is None or not file.filename:
        raise ApiError(400, "MISSING_FILE", "Attach the MRI image in a multipart field named 'file'.")
    data = file.read(services.config.max_upload_bytes + 1)
    validated = validate_upload(file.filename, data, services.config.max_upload_bytes)
    record = services.uploads.save(validated, filename=sanitize_filename(file.filename))
    logger.info("Accepted upload %s (%dx%d %s)", record.upload_id, record.width, record.height,
                record.source_format)
    return jsonify({**record.public_view(), "disclaimer": DISCLAIMER}), 201


@api.post("/predictions")
def create_prediction() -> tuple[Response, int]:
    services = _services()
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("upload_id"), str):
        raise ApiError(400, "INVALID_REQUEST", "Request body must be JSON with an 'upload_id' string.")

    image, upload = services.uploads.load(body["upload_id"])
    result = services.models.predict(image)
    prediction = result.prediction
    record = {
        "created_at": utc_now_iso(),
        "original_filename": upload.filename,
        "source_format": upload.source_format,
        "width": upload.width,
        "height": upload.height,
        "size_bytes": upload.size_bytes,
        "image_sha256": upload.sha256,
        "predicted_class": prediction.predicted_class,
        "tumor_detected": prediction.tumor_detected,
        "confidence": round(prediction.confidence, 6),
        "low_confidence": result.low_confidence,
        "probabilities": {k: round(v, 6) for k, v in prediction.probabilities.items()},
        "model_version": services.models.version or "unknown",
        "inference_ms": result.inference_ms,
    }
    stored = services.history.add(record, make_thumbnail(image))
    services.uploads.delete(upload.upload_id)  # the derived thumbnail is all we keep
    logger.info("Prediction %s: %s (%.1f%%)", stored["id"], prediction.predicted_class,
                prediction.confidence * 100)
    return jsonify({**_format_prediction(stored), "disclaimer": DISCLAIMER}), 201


@api.get("/predictions")
def list_predictions() -> Response:
    services = _services()
    limit = _parse_int("limit", default=20, minimum=1, maximum=100)
    offset = _parse_int("offset", default=0, minimum=0, maximum=10_000_000)
    rows, total = services.history.list_page(limit, offset)
    return jsonify({
        "items": [_format_prediction(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@api.get("/predictions/<prediction_id>")
def get_prediction(prediction_id: str) -> Response:
    row = _find_or_404(prediction_id)
    return jsonify(_format_prediction(row))


@api.get("/predictions/<prediction_id>/thumbnail")
def prediction_thumbnail(prediction_id: str) -> Response:
    if not _is_valid_id(prediction_id):
        raise ApiError(404, "PREDICTION_NOT_FOUND", "Prediction not found.")
    path = _services().history.thumbnail_path(prediction_id)
    if path is None:
        raise ApiError(404, "PREDICTION_NOT_FOUND", "Prediction not found.")
    response = send_file(path, mimetype="image/jpeg", max_age=3600)
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@api.delete("/predictions/<prediction_id>")
def delete_prediction(prediction_id: str) -> tuple[str, int]:
    if not _is_valid_id(prediction_id) or not _services().history.delete(prediction_id):
        raise ApiError(404, "PREDICTION_NOT_FOUND", "Prediction not found.")
    return "", 204


@api.delete("/predictions")
def clear_predictions() -> Response:
    deleted = _services().history.clear()
    return jsonify({"deleted": deleted})


def _is_valid_id(value: str) -> bool:
    try:
        uuid.UUID(hex=value)
    except ValueError:
        return False
    return len(value) == 32


def _find_or_404(prediction_id: str) -> dict[str, Any]:
    row = _services().history.get(prediction_id) if _is_valid_id(prediction_id) else None
    if row is None:
        raise ApiError(404, "PREDICTION_NOT_FOUND", "Prediction not found.")
    return row
