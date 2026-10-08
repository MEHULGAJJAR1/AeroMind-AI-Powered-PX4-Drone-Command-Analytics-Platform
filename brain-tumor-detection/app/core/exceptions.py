"""Domain exceptions.

Every exception raised inside the API layer inherits from :class:`ApiError` so
the error handlers in :mod:`app.core.errors` can serialise a consistent JSON
payload (HTTP status + machine readable ``code`` + human ``message``).
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base class for all API errors."""

    status_code = 500
    code = "internal_error"
    message = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class ValidationError(ApiError):
    """The request was malformed (missing field, wrong type, ...)."""

    status_code = 400
    code = "validation_error"
    message = "The request could not be processed."


class ImageValidationError(ApiError):
    """The uploaded file is not a usable image."""

    status_code = 422
    code = "invalid_image"
    message = "The uploaded file is not a supported image."


class FileTooLargeError(ApiError):
    status_code = 413
    code = "file_too_large"
    message = "The uploaded file is too large."


class ModelUnavailableError(ApiError):
    """No trained model has been loaded."""

    status_code = 503
    code = "model_unavailable"
    message = (
        "No model is loaded. Train one with `python -m training.train --data-dir <dataset>` "
        "or run `scripts/train-demo-model.sh`, then restart the server."
    )


class PredictionError(ApiError):
    """Inference failed."""

    status_code = 500
    code = "prediction_error"
    message = "Prediction failed."


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"
    message = "Resource not found."


class RateLimitExceededError(ApiError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Please slow down and try again shortly."
