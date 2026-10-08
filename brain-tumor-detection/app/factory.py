"""Flask application factory.

``create_app()`` wires configuration, logging, error handling, the model
registry, the history store, rate limiting, CORS and the blueprints. It is used
by ``run.py``, ``wsgi.py`` and the test-suite (``tests/conftest.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, render_template, request

from app.version import __version__
from app.api import api_bp
from app.config import Config
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger, register_request_hooks
from app.core.ratelimit import SlidingWindowRateLimiter
from app.ml.predictor import create_predictor
from app.services.history import HistoryStore

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def create_app(config: Config | None = None, *, load_model: bool = True) -> Flask:
    app = Flask(
        __name__,
        static_folder=str(STATIC_DIR),
        static_url_path="/static",
        template_folder=str(TEMPLATE_DIR),
    )

    cfg = config or Config.from_env()
    cfg.ensure_directories()

    app.config["BTD_CONFIG"] = cfg
    app.config["SECRET_KEY"] = cfg.secret_key
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_content_length
    app.config["MAX_CONTENT_LENGTH_MB"] = cfg.max_content_length_mb
    app.config["JSON_SORT_KEYS"] = cfg.json_sort_keys
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.config["ENV"] = cfg.env
    app.version = __version__  # type: ignore[attr-defined]

    configure_logging(app, level=cfg.log_level, log_file=cfg.log_file)
    register_request_hooks(app)
    register_error_handlers(app)

    # --- Services ---------------------------------------------------------
    if load_model:
        predictor = create_predictor(
            cfg.model_dir,
            device=cfg.device,
            require_model=cfg.require_model,
            load=True,
        )
        if not predictor.is_loaded:
            get_logger().warning(
                "Starting without a model: predictions will return 503 until a checkpoint exists in %s",
                cfg.model_dir,
            )
    else:
        predictor = None
    app.extensions["predictor"] = predictor
    app.extensions["history"] = HistoryStore(cfg.db_path, max_rows=cfg.history_limit)
    app.extensions["rate_limiter"] = SlidingWindowRateLimiter(cfg.rate_limit, cfg.rate_window_seconds)

    _register_cors(app, cfg)
    _register_rate_limiting(app)

    app.register_blueprint(api_bp)
    _register_pages(app)

    get_logger().info(
        "BrainScan AI %s ready (env=%s, model=%s, device=%s, history=%s)",
        __version__,
        cfg.env,
        "loaded" if predictor is not None and predictor.is_loaded else "not loaded",
        predictor.device_name if predictor is not None else "-",
        cfg.db_path,
    )
    return app


def _client_key() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _register_rate_limiting(app: Flask) -> None:
    limiter: SlidingWindowRateLimiter = app.extensions["rate_limiter"]
    if not limiter.enabled:
        return

    @app.before_request
    def _apply_rate_limit():
        if not request.path.startswith("/api/") or request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        result = limiter.consume(f"{_client_key()}:{request.path}")
        if not result.allowed:
            response = jsonify(
                {
                    "status": "error",
                    "error": {
                        "code": "rate_limited",
                        "message": f"Rate limit exceeded ({result.limit} requests / {result.window}s). Try again in {result.retry_after}s.",
                    },
                }
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(result.retry_after)
            response.headers["X-RateLimit-Limit"] = str(result.limit)
            response.headers["X-RateLimit-Remaining"] = "0"
            return response
        g.rate_limit = result
        return None

    @app.after_request
    def _expose_rate_limit(response):
        result = getattr(g, "rate_limit", None)
        if result is not None:
            response.headers.setdefault("X-RateLimit-Limit", str(result.limit))
            response.headers.setdefault("X-RateLimit-Remaining", str(result.remaining))
        return response


def _register_cors(app: Flask, cfg: Config) -> None:
    if not cfg.cors_origins:
        return

    allowed = set(cfg.cors_origins)

    @app.after_request
    def _cors(response):
        origin = request.headers.get("Origin")
        if origin and (origin in allowed or "*" in allowed):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Request-Id"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.route("/api/<path:_any>", methods=["OPTIONS"])  # pragma: no cover - preflight
    def _preflight(_any: str):
        return ("", 204)


def _register_pages(app: Flask) -> None:
    @app.get("/")
    def index():
        cfg: Config = app.config["BTD_CONFIG"]
        return render_template(
            "index.html",
            version=__version__,
            config={
                "max_upload_mb": cfg.max_upload_mb,
                "allowed_extensions": sorted(cfg.allowed_extensions),
                "history_limit": cfg.history_limit,
                "env": cfg.env,
            },
        )

    @app.get("/healthz")
    def healthz():  # pragma: no cover - trivial
        return jsonify({"status": "ok", "version": __version__})

    @app.errorhandler(404)
    def page_not_found(exc: Any):
        if request.path.startswith("/api/"):
            return jsonify(
                {
                    "status": "error",
                    "error": {"code": "not_found", "message": f"No API route for {request.path}"},
                }
            ), 404
        return render_template("404.html", version=__version__), 404
