"""Logging setup and request correlation ids."""

from __future__ import annotations

import logging
import sys
import time
import uuid

from flask import Flask, g, request

LOGGER_NAME = "brainscan"

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(app: Flask, level: str = "INFO", log_file: str = "") -> logging.Logger:
    """Attach handlers to the application logger (idempotent)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(stream)

        if log_file:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(_FORMAT))
            logger.addHandler(file_handler)

    # Quiet down noisy third-party loggers while keeping Werkzeug's access log.
    logging.getLogger("werkzeug").setLevel(logging.WARNING if level.upper() == "WARNING" else logging.INFO)
    app.logger.handlers = logger.handlers
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def register_request_hooks(app: Flask) -> None:
    """Add a request id + timing to every request/response."""

    @app.before_request
    def _start_timer() -> None:  # pragma: no cover - trivial
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        g.started_at = time.perf_counter()

    @app.after_request
    def _finish(response):  # pragma: no cover - trivial
        started = getattr(g, "started_at", None)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2) if started else None
        response.headers.setdefault("X-Request-Id", getattr(g, "request_id", "-"))
        if elapsed_ms is not None:
            response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if elapsed_ms is not None and request.path.startswith("/api/"):
            get_logger().info(
                "%s %s -> %s (%.1f ms) req=%s",
                request.method,
                request.path,
                response.status_code,
                elapsed_ms,
                getattr(g, "request_id", "-"),
            )
        return response
