"""Upload validation.

Two layers of defence:

1. cheap request-level checks (field present, filename, extension, MIME type,
   declared size) — reject before the bytes are even decoded;
2. content checks — magic bytes / full decode via
   :func:`app.ml.preprocess.open_image`, which catches renamed executables,
   truncated uploads and decompression bombs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Request, current_app
from werkzeug.datastructures import FileStorage

from app.config import Config
from app.core.exceptions import FileTooLargeError, ImageValidationError, ValidationError
from app.ml.preprocess import ImageLoadError, open_image

MAX_FILENAME_LENGTH = 255
IMAGE_FIELD_NAMES: tuple[str, ...] = ("image", "file", "mri", "scan", "upload")


@dataclass
class ValidatedUpload:
    """Result of a successful validation."""

    filename: str
    safe_name: str
    extension: str
    content_type: str
    size: int
    raw: bytes
    source_field: str

    @property
    def size_mb(self) -> float:
        return round(self.size / (1024 * 1024), 3)


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_upload(request: Request, config: Config | None = None) -> ValidatedUpload:
    """Extract and validate the image from a multipart request."""
    config = config or _config_from_app()

    if not request.files:
        raise ValidationError(
            "No file was uploaded. Send a multipart/form-data request with an 'image' field.",
            details={"expected_field": IMAGE_FIELD_NAMES[0]},
        )

    file_storage: FileStorage | None = None
    source_field = ""
    for field in IMAGE_FIELD_NAMES:
        candidate = request.files.get(field)
        if candidate is not None and (candidate.filename or "").strip():
            file_storage = candidate
            source_field = field
            break

    if file_storage is None:
        # A field exists but is empty — a common client-side bug worth explaining.
        present = [name for name, fs in request.files.items() if fs is not None]
        raise ValidationError(
            "The 'image' field is missing or empty.",
            details={"fields_received": present, "expected_field": IMAGE_FIELD_NAMES[0]},
        )

    filename = (file_storage.filename or "").strip()
    if not filename:
        raise ValidationError("The uploaded file has no filename.")
    if len(filename) > MAX_FILENAME_LENGTH:
        raise ValidationError(f"Filename is too long (max {MAX_FILENAME_LENGTH} characters).")

    extension = _extension(filename)
    if extension not in config.allowed_extensions:
        raise ImageValidationError(
            f"Unsupported file type '{extension or 'unknown'}'.",
            code="unsupported_file_type",
            details={
                "extension": extension,
                "allowed_extensions": sorted(config.allowed_extensions),
            },
        )

    content_type = (file_storage.mimetype or "").split(";")[0].strip().lower()
    if content_type and content_type not in config.allowed_mime_types:
        raise ImageValidationError(
            f"Unsupported content type '{content_type}'.",
            code="unsupported_content_type",
            details={"content_type": content_type, "allowed": sorted(t for t in config.allowed_mime_types if t)},
        )

    raw = file_storage.read()
    if not raw:
        raise ValidationError("The uploaded file is empty (0 bytes).")

    max_bytes = config.max_upload_bytes
    if len(raw) > max_bytes:
        raise FileTooLargeError(
            f"The file is {len(raw) / (1024 * 1024):.1f} MB, the limit is {config.max_upload_mb} MB.",
            details={"size_bytes": len(raw), "max_bytes": max_bytes, "max_upload_mb": config.max_upload_mb},
        )

    return ValidatedUpload(
        filename=filename,
        safe_name=_safe_name(filename),
        extension=extension,
        content_type=content_type or _guess_mime(extension),
        size=len(raw),
        raw=raw,
        source_field=source_field,
    )


def decode_image(upload: ValidatedUpload, config: Config | None = None):
    """Decode validated bytes into a PIL image (integrity + dimension checks)."""
    config = config or _config_from_app()
    try:
        return open_image(
            upload.raw,
            max_pixels=config.max_image_pixels,
            min_dimension=config.min_image_dimension,
        )
    except ImageLoadError as exc:
        raise ImageValidationError(str(exc)) from exc


def _safe_name(filename: str) -> str:
    """Filesystem-safe basename that keeps a sane extension (no path traversal).

    Only the final path component is kept, non-ASCII/punctuation is stripped and
    the extension is limited to a short alphanumeric suffix.
    """
    from werkzeug.utils import secure_filename

    suffix = Path(filename).suffix.lower()
    extension = "".join(ch for ch in suffix if ch.isalnum())[:9]
    extension = f".{extension}" if extension else ""

    stem = secure_filename(Path(filename).stem) or "upload"
    return f"{stem}{extension}"[:MAX_FILENAME_LENGTH]


def _guess_mime(extension: str) -> str:
    import mimetypes

    return mimetypes.guess_type(f"file{extension}")[0] or "application/octet-stream"


def _config_from_app() -> Config:
    config: Any = current_app.config.get("BTD_CONFIG")
    if isinstance(config, Config):
        return config
    raise ValidationError("Server configuration is not available.")


def unique_upload_path(directory: Path, safe_name: str, identifier: str) -> Path:
    """Collision-free storage path ``<directory>/<identifier>-<safe_name>``."""
    directory.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(safe_name)
    candidate = directory / f"{identifier}-{stem}{ext}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{identifier}-{stem}-{counter}{ext}"
        counter += 1
    return candidate
