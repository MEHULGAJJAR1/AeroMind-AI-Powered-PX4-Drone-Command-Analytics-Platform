"""Global error handlers — every failure leaves the API as JSON."""

from __future__ import annotations

import logging

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException
from werkzeug.exceptions import RequestEntityTooLarge as WerkzeugTooLarge

from app.core.exceptions import ApiError
from app.core.logging import get_logger


def _error_payload(code: str, message: str, details: dict | None = None) -> dict:
    payload: dict = {"status": "error", "error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return payload


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        if exc.status_code >= 500:
            get_logger().exception("API error %s: %s", exc.code, exc.message, exc_info=False)
        else:
            get_logger().warning("API error %s: %s", exc.code, exc.message)
        response = jsonify(_error_payload(exc.code, exc.message, exc.details or None))
        response.status_code = exc.status_code
        return response

    @app.errorhandler(WerkzeugTooLarge)
    def handle_too_large(exc: WerkzeugTooLarge):
        max_mb = app.config["MAX_CONTENT_LENGTH_MB"]
        payload = _error_payload(
            "file_too_large",
            f"The upload exceeds the {max_mb} MB request limit.",
            {"max_upload_mb": max_mb},
        )
        return jsonify(payload), 413

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):
        code_map = {
            400: "bad_request",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
            413: "file_too_large",
            415: "unsupported_media_type",
            422: "unprocessable_entity",
            429: "rate_limited",
        }
        code = code_map.get(exc.code or 500, "http_error")
        return jsonify(_error_payload(code, exc.description or exc.name)), exc.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):  # pragma: no cover - defensive
        logger = get_logger()
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        app = _get_current_app()
        if app is not None and app.debug:
            raise exc
        return jsonify(_error_payload("internal_error", "An unexpected error occurred. Please try again.")), 500


def _get_current_app():
    from flask import current_app

    try:
        return current_app._get_current_object()
    except RuntimeError:  # pragma: no cover
        return None


def log_unhandled(logger: logging.Logger, exc: Exception) -> None:  # pragma: no cover - helper
    logger.error("Unhandled exception: %s", exc, exc_info=True)
