"""Validation of uploaded MRI images.

Checks are layered from cheap to expensive: file extension, byte size, a
Pillow probe that verifies the real file format (the extension is not
trusted), pixel-count and dimension limits, and finally decoding into an
8-bit RGB image that the model can consume.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import PurePath

from PIL import Image, UnidentifiedImageError

from ml.preprocessing import to_rgb

from ..errors import ApiError

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".bmp"})
SUPPORTED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "BMP"})
MIN_DIMENSION = 32
MAX_DIMENSION = 4096
MAX_PIXELS = 40_000_000

# Pillow's own bomb warning is too permissive for a public upload endpoint; we enforce our limit explicitly.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2


@dataclass(frozen=True)
class ValidatedImage:
    """A safe, decoded image plus metadata about the original file."""

    image: Image.Image  # 8-bit RGB
    source_format: str
    original_width: int
    original_height: int
    size_bytes: int
    sha256: str


def sanitize_filename(filename: str | None) -> str:
    """Keep only the base name, strip control characters and bound the length."""
    name = PurePath((filename or "").replace("\\", "/")).name or "upload"
    name = "".join(ch for ch in name if ch.isprintable())
    return name[:120] or "upload"


def validate_upload(filename: str | None, data: bytes, max_bytes: int) -> ValidatedImage:
    """Validate raw upload bytes and return a decoded RGB image, or raise :class:`ApiError`."""
    safe_name = sanitize_filename(filename)
    extension = PurePath(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ApiError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type '{extension or 'none'}'. Upload a JPEG, PNG or BMP image.",
            {"allowed_extensions": sorted(ALLOWED_EXTENSIONS)},
        )
    if not data:
        raise ApiError(400, "EMPTY_FILE", "The uploaded file is empty.")
    if len(data) > max_bytes:
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            f"File is {len(data) / 1048576:.1f} MB; the limit is {max_bytes / 1048576:.0f} MB.",
            {"max_bytes": max_bytes},
        )

    try:
        with Image.open(io.BytesIO(data)) as probe:
            detected_format = probe.format or ""
            width, height = probe.size
            probe.verify()  # detects truncated / corrupt files without decoding every pixel
    except UnidentifiedImageError as exc:
        raise ApiError(415, "INVALID_IMAGE", "The file is not a readable JPEG, PNG or BMP image.") from exc
    except Image.DecompressionBombError as exc:
        raise ApiError(413, "IMAGE_TOO_LARGE", "The image has too many pixels to process.") from exc
    except (OSError, SyntaxError, ValueError) as exc:
        raise ApiError(422, "CORRUPT_IMAGE", "The image file is corrupt or truncated.") from exc

    if detected_format not in SUPPORTED_FORMATS:
        raise ApiError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            f"Detected format '{detected_format or 'unknown'}' is not supported. Use JPEG, PNG or BMP.",
        )
    if width * height > MAX_PIXELS:
        raise ApiError(413, "IMAGE_TOO_LARGE", "The image has too many pixels to process.")
    if min(width, height) < MIN_DIMENSION or max(width, height) > MAX_DIMENSION:
        raise ApiError(
            422,
            "IMAGE_DIMENSIONS_OUT_OF_RANGE",
            f"Image is {width}x{height}px. Allowed sides are {MIN_DIMENSION}-{MAX_DIMENSION}px.",
            {"width": width, "height": height},
        )

    try:
        with Image.open(io.BytesIO(data)) as image:
            rgb = to_rgb(image).copy()
    except (OSError, ValueError) as exc:
        raise ApiError(422, "CORRUPT_IMAGE", "The image could not be decoded.") from exc

    return ValidatedImage(
        image=rgb,
        source_format=detected_format,
        original_width=width,
        original_height=height,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
