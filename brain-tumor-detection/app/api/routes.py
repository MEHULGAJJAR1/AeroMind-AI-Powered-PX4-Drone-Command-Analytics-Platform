"""REST API.

| Method | Path                        | Purpose                                  |
| ------ | --------------------------- | ---------------------------------------- |
| GET    | ``/api/health``             | Liveness + model readiness               |
| GET    | ``/api/model``              | Loaded model metadata & metrics          |
| POST   | ``/api/predict``            | Upload an MRI scan and get a prediction  |
| GET    | ``/api/predictions``        | Prediction history (paginated)           |
| GET    | ``/api/predictions/<id>``   | Single history entry                     |
| DELETE | ``/api/predictions/<id>``   | Delete one entry                         |
| DELETE | ``/api/predictions``        | Clear history                            |
| GET    | ``/api/stats``              | Aggregate statistics                     |
| POST   | ``/api/model/reload``       | Hot-reload the checkpoint                |
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, request

from app.version import __version__
from app.core.exceptions import ModelUnavailableError, NotFoundError, ValidationError
from app.core.responses import created, ok
from app.services.analysis import analyze_request

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _predictor():
    predictor = current_app.extensions.get("predictor")
    if predictor is None:  # pragma: no cover - misconfiguration
        raise ModelUnavailableError()
    return predictor


def _history():
    return current_app.extensions.get("history")


def _bool_arg(name: str, default: bool = False) -> bool:
    raw = request.args.get(name)
    if raw is None:
        if request.form:
            raw = request.form.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _int_arg(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"'{name}' must be an integer.", details={"value": raw}) from exc
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


# --------------------------------------------------------------------------- #
# Health / model
# --------------------------------------------------------------------------- #
@api_bp.get("/health")
def health():
    predictor = _predictor()
    return ok(
        {
            "service": "brainscan-ai",
            "version": __version__,
            "status": "healthy" if predictor.is_loaded else "degraded",
            "model_available": predictor.is_loaded,
            "model": predictor.health(),
            "history": {"enabled": _history() is not None, "entries": _history().count() if _history() else 0},
            "config": current_app.config["BTD_CONFIG"].as_public_dict(),
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
    )


@api_bp.get("/model")
def model_info():
    predictor = _predictor()
    if not predictor.is_loaded:
        raise ModelUnavailableError(predictor._load_error or None)  # noqa: SLF001 - intentional
    return ok(predictor.public_metadata())


@api_bp.post("/model/reload")
def model_reload():
    predictor = _predictor()
    predictor.reload()
    if not predictor.is_loaded:
        raise ModelUnavailableError(predictor._load_error or None)  # noqa: SLF001
    return ok({"reloaded": True, "model": predictor.public_metadata()})


# --------------------------------------------------------------------------- #
# Prediction
# --------------------------------------------------------------------------- #
@api_bp.post("/predict")
def predict():
    config = current_app.config["BTD_CONFIG"]
    notes = (request.form.get("notes") or "").strip()[:500] or None
    include_preprocessed = _bool_arg("include_preprocessed", default=True)
    save_history = _bool_arg("save_history", default=True)

    payload = analyze_request(
        request,
        config=config,
        predictor=_predictor(),
        history=_history() if save_history else None,
        notes=notes,
        include_preprocessed=include_preprocessed,
        save_history=save_history,
    )
    return created(payload)


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
@api_bp.get("/predictions")
def list_predictions():
    history = _history()
    if history is None:
        return ok({"items": [], "total": 0, "limit": 0, "offset": 0})

    limit = _int_arg("limit", 20, minimum=1, maximum=200)
    offset = _int_arg("offset", 0, minimum=0)
    include_thumbnails = _bool_arg("thumbnails", default=True)

    items = history.list(limit=limit, offset=offset, include_thumbnails=include_thumbnails)
    return ok(
        {
            "items": [item.to_dict(include_thumbnail=include_thumbnails) for item in items],
            "total": history.count(),
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < history.count(),
        }
    )


@api_bp.get("/predictions/<record_id>")
def get_prediction(record_id: str):
    history = _history()
    if history is None:
        raise NotFoundError("Prediction history is disabled.")
    record = history.get(record_id)
    if record is None:
        raise NotFoundError(f"No prediction with id '{record_id}'.")
    return ok(record.to_dict())


@api_bp.delete("/predictions/<record_id>")
def delete_prediction(record_id: str):
    history = _history()
    if history is None:
        raise NotFoundError("Prediction history is disabled.")
    if not history.delete(record_id):
        raise NotFoundError(f"No prediction with id '{record_id}'.")
    return ok({"deleted": record_id})


@api_bp.delete("/predictions")
def clear_predictions():
    history = _history()
    if history is None:
        raise NotFoundError("Prediction history is disabled.")
    deleted = history.clear()
    return ok({"deleted": deleted})


@api_bp.get("/stats")
def stats():
    history = _history()
    data = history.stats() if history is not None else {}
    data["model"] = _predictor().health()
    return ok(data)
