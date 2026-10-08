"""Runtime configuration, read from ``BTD_*`` environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ml.constants import DEFAULT_MODEL_PATH, PROJECT_ROOT


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class Config:
    """All tunables of the web service in one immutable object."""

    model_path: Path = DEFAULT_MODEL_PATH
    data_dir: Path = PROJECT_ROOT / "instance"
    device: str = "cpu"
    max_upload_mb: float = 10.0
    low_confidence_threshold: float = 0.60
    upload_ttl_seconds: int = 3600
    log_level: str = "INFO"
    # Pixel-count guard against decompression bombs (about 6300 x 6300 pixels).
    max_image_pixels: int = 40_000_000

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "predictions.sqlite3"

    @classmethod
    def from_env(cls) -> "Config":
        defaults = cls()
        model_path = os.environ.get("BTD_MODEL_PATH")
        data_dir = os.environ.get("BTD_DATA_DIR")
        return cls(
            model_path=Path(model_path).expanduser() if model_path else defaults.model_path,
            data_dir=Path(data_dir).expanduser() if data_dir else defaults.data_dir,
            device=os.environ.get("BTD_DEVICE", defaults.device),
            max_upload_mb=_env_float("BTD_MAX_UPLOAD_MB", defaults.max_upload_mb),
            low_confidence_threshold=_env_float(
                "BTD_LOW_CONFIDENCE_THRESHOLD", defaults.low_confidence_threshold
            ),
            upload_ttl_seconds=_env_int("BTD_UPLOAD_TTL_SECONDS", defaults.upload_ttl_seconds),
            log_level=os.environ.get("BTD_LOG_LEVEL", defaults.log_level).upper(),
        )
