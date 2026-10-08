"""Application configuration.

Configuration is read from the environment. A local ``.env`` file in the
project root is loaded automatically (a tiny loader is used instead of adding
``python-dotenv`` as a dependency).

Environment variables are prefixed with ``BTD_`` — see ``.env.example``.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
)

# Accepted Content-Type values. Browsers occasionally report an empty type for
# local files, so an empty string is tolerated and sniffed instead.
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/bmp",
        "image/tiff",
        "image/x-tiff",
        "image/webp",
        "",
    }
)

CLASS_LABELS: tuple[str, ...] = ("no_tumor", "tumor")
CLASS_DISPLAY_NAMES: dict[str, str] = {
    "no_tumor": "No tumor detected",
    "tumor": "Tumor detected",
}


def _load_dotenv(path: Path) -> None:
    """Populate ``os.environ`` from a ``.env`` file without overriding existing values."""
    if not path.is_file():
        return
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _path(name: str, default: str) -> Path:
    raw = os.getenv(name, default).strip() or default
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration."""

    env: str = "development"
    secret_key: str = field(default_factory=lambda: secrets.token_hex(32))
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 5000
    cors_origins: tuple[str, ...] = ()

    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    model_dir: Path = PROJECT_ROOT / "data" / "models"
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"
    db_path: Path = PROJECT_ROOT / "data" / "history.db"

    max_upload_mb: int = 10
    min_image_dimension: int = 32
    max_image_pixels: int = 89_478_485  # Pillow default
    allowed_extensions: frozenset[str] = ALLOWED_EXTENSIONS
    allowed_mime_types: frozenset[str] = ALLOWED_MIME_TYPES

    device: str = "auto"
    require_model: bool = False
    keep_uploads: bool = True
    history_limit: int = 500

    rate_limit: int = 60
    rate_window_seconds: int = 60

    log_level: str = "INFO"
    log_file: str = ""

    json_sort_keys: bool = False
    max_content_length_mb: int = 12

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_content_length(self) -> int:
        return self.max_content_length_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.model_dir, self.upload_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def as_public_dict(self) -> dict[str, object]:
        """Non-sensitive view used by ``/api/health``."""
        return {
            "env": self.env,
            "debug": self.debug,
            "device": self.device,
            "max_upload_mb": self.max_upload_mb,
            "allowed_extensions": sorted(self.allowed_extensions),
            "rate_limit": self.rate_limit,
            "history_enabled": True,
        }

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv(PROJECT_ROOT / ".env")

        env = os.getenv("BTD_ENV", "development").strip().lower() or "development"
        debug = _bool("BTD_DEBUG", env == "development")
        secret = os.getenv("BTD_SECRET_KEY", "").strip()
        if not secret:
            # Development-only ephemeral key. Production deployments must set one.
            secret = secrets.token_hex(32)

        cors_raw = os.getenv("BTD_CORS_ORIGINS", "")
        origins = tuple(o.strip() for o in cors_raw.split(",") if o.strip())

        data_dir = _path("BTD_DATA_DIR", "data")
        log_file = os.getenv("BTD_LOG_FILE", "").strip()

        return cls(
            env=env,
            secret_key=secret,
            debug=debug,
            host=os.getenv("BTD_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_int("BTD_PORT", 5000),
            cors_origins=origins,
            data_dir=data_dir,
            model_dir=_path("BTD_MODEL_DIR", str(data_dir / "models")),
            upload_dir=data_dir / "uploads",
            db_path=_path("BTD_DB_PATH", str(data_dir / "history.db")),
            max_upload_mb=_int("BTD_MAX_UPLOAD_MB", 10),
            min_image_dimension=_int("BTD_MIN_IMAGE_DIMENSION", 32),
            max_image_pixels=_int("BTD_MAX_IMAGE_PIXELS", 89_478_485),
            device=os.getenv("BTD_DEVICE", "auto").strip().lower() or "auto",
            require_model=_bool("BTD_REQUIRE_MODEL", False),
            keep_uploads=_bool("BTD_KEEP_UPLOADS", True),
            history_limit=_int("BTD_HISTORY_LIMIT", 500),
            rate_limit=_int("BTD_RATE_LIMIT", 60),
            rate_window_seconds=_int("BTD_RATE_WINDOW_SECONDS", 60),
            log_level=os.getenv("BTD_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            log_file=log_file,
            json_sort_keys=False,
            max_content_length_mb=_int("BTD_MAX_CONTENT_LENGTH_MB", _int("BTD_MAX_UPLOAD_MB", 10) + 2),
        )

    @classmethod
    def for_testing(cls, tmp_path: Path | None = None) -> "Config":
        """Configuration used by the test-suite (isolated temp directories)."""
        base = tmp_path or PROJECT_ROOT / "data" / "test"
        base = Path(base)
        return cls(
            env="testing",
            debug=False,
            data_dir=base,
            model_dir=base / "models",
            upload_dir=base / "uploads",
            db_path=base / "history.db",
            keep_uploads=False,
            history_limit=50,
            rate_limit=0,
            log_level="WARNING",
        )
