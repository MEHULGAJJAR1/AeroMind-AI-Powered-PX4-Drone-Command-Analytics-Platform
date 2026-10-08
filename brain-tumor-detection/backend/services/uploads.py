"""Temporary storage for validated uploads.

An upload is stored as a lossless PNG plus a JSON sidecar. The client receives
an opaque ``upload_id`` and later references it when requesting a prediction.
Uploads expire after ``upload_ttl_seconds`` and are removed once used.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from ..errors import ApiError
from .validation import ValidatedImage

logger = logging.getLogger(__name__)
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    filename: str
    width: int
    height: int
    source_format: str
    size_bytes: int
    sha256: str
    created_at: float
    expires_at: float

    def public_view(self) -> dict:
        return {
            "upload_id": self.upload_id,
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "source_format": self.source_format,
            "size_bytes": self.size_bytes,
            "expires_in_seconds": max(0, int(self.expires_at - time.time())),
        }


class UploadStore:
    def __init__(self, directory: Path, ttl_seconds: int) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _paths(self, upload_id: str) -> tuple[Path, Path]:
        return self.directory / f"{upload_id}.png", self.directory / f"{upload_id}.json"

    def save(self, validated: ValidatedImage, filename: str) -> UploadRecord:
        self.cleanup_expired()
        upload_id = uuid.uuid4().hex
        now = time.time()
        record = UploadRecord(
            upload_id=upload_id,
            filename=filename,
            width=validated.original_width,
            height=validated.original_height,
            source_format=validated.source_format,
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        image_path, meta_path = self._paths(upload_id)
        validated.image.save(image_path, format="PNG")
        meta_path.write_text(json.dumps(asdict(record)), encoding="utf-8")
        return record

    def load(self, upload_id: str) -> tuple[Image.Image, UploadRecord]:
        if not _UPLOAD_ID_RE.match(upload_id or ""):
            raise ApiError(404, "UPLOAD_NOT_FOUND", "Upload not found.")
        image_path, meta_path = self._paths(upload_id)
        if not (image_path.is_file() and meta_path.is_file()):
            raise ApiError(404, "UPLOAD_NOT_FOUND", "Upload not found. Please upload the image again.")
        record = UploadRecord(**json.loads(meta_path.read_text(encoding="utf-8")))
        if record.expires_at < time.time():
            self.delete(upload_id)
            raise ApiError(410, "UPLOAD_EXPIRED", "The upload has expired. Please upload the image again.")
        with Image.open(image_path) as image:
            return image.convert("RGB"), record

    def delete(self, upload_id: str) -> None:
        if not _UPLOAD_ID_RE.match(upload_id or ""):
            return
        for path in self._paths(upload_id):
            path.unlink(missing_ok=True)

    def cleanup_expired(self) -> int:
        removed = 0
        now = time.time()
        for meta_path in self.directory.glob("*.json"):
            try:
                expires_at = json.loads(meta_path.read_text(encoding="utf-8"))["expires_at"]
            except (OSError, ValueError, KeyError):
                expires_at = 0.0  # corrupt sidecar: remove it
            if expires_at < now:
                self.delete(meta_path.stem)
                removed += 1
        if removed:
            logger.debug("Removed %d expired uploads", removed)
        return removed

