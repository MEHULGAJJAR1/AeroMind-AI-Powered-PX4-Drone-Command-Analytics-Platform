"""Flask application factory for the brain tumor detection service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .config import Config
from .errors import ApiError
from .routes import api
from .services.history import PredictionHistory
from .services.inference import ModelService
from .services.uploads import UploadStore

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
logger = logging.getLogger(__name__)

_CSP = (
    "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


@dataclass
class Services:
    config: Config
    models: ModelService
    uploads: UploadStore
    history: PredictionHistory


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    logging.basicConfig(level=config.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="/static")
    # Allow a little multipart overhead on top of the file limit; the handler enforces the exact limit.
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_bytes + 64 * 1024

    services = Services(
        config=config,
        models=ModelService(config.model_path, config.device, config.low_confidence_threshold),
        uploads=UploadStore(config.uploads_dir, config.upload_ttl_seconds),
        history=PredictionHistory(config.database_path, config.thumbnails_dir),
    )
    services.models.load()
    app.extensions["btd"] = services

    app.register_blueprint(api)
    _register_error_handlers(app)

    @app.get("/")
    def index() -> Response:
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers.setdefault("Content-Security-Policy", _CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError) -> tuple[Response, int]:
        return jsonify({"error": err.to_dict()}), err.status

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(err: RequestEntityTooLarge) -> tuple[Response, int]:
        limit_mb = app.extensions["btd"].config.max_upload_mb
        return jsonify({"error": {
            "code": "FILE_TOO_LARGE",
            "message": f"Upload exceeds the {limit_mb:g} MB limit.",
        }}), 413

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException) -> Response | tuple[Response, int]:
        if request.path.startswith("/api/"):
            code = (err.name or "HTTP_ERROR").upper().replace(" ", "_")
            return jsonify({"error": {"code": code, "message": err.description}}), err.code or 500
        return err

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception) -> tuple[Response, int] | Response:
        logger.exception("Unhandled error while processing %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify({"error": {
                "code": "INTERNAL_ERROR",
                "message": "Something went wrong while processing the request.",
            }}), 500
        return Response("Internal server error", status=500, mimetype="text/plain")
