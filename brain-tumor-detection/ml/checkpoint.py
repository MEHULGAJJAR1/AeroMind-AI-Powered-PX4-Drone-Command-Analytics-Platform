"""Save and load model checkpoints together with their metadata.

A checkpoint is a single ``.pt`` file containing the weights plus everything
needed to serve it correctly (class order, input size, training metrics), so
the web app never has to guess preprocessing parameters.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch

from .constants import CLASS_NAMES, PREPROCESSING_VERSION
from .model import BrainTumorCNN

CHECKPOINT_FORMAT_VERSION = 2
ARCHITECTURE_NAME = "BrainTumorCNN"


class CheckpointError(RuntimeError):
    """Raised when a checkpoint is missing, corrupt or incompatible."""


@dataclass(frozen=True)
class LoadedCheckpoint:
    model: BrainTumorCNN
    class_names: tuple[str, ...]
    img_size: int
    metadata: dict[str, Any] = field(default_factory=dict)


def save_checkpoint(
    path: Path,
    model: torch.nn.Module,
    *,
    img_size: int,
    metadata: dict[str, Any] | None = None,
    class_names: tuple[str, ...] = CLASS_NAMES,
) -> Path:
    """Write weights and metadata to ``path`` (parent directories are created)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": CHECKPOINT_FORMAT_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "architecture": ARCHITECTURE_NAME,
        "class_names": list(class_names),
        "img_size": int(img_size),
        "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "metadata": dict(metadata or {}),
        "model_state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, tmp_path)
    tmp_path.replace(path)  # atomic on POSIX: never leaves a half-written model behind
    return path


def load_checkpoint(path: Path, device: str | torch.device = "cpu") -> LoadedCheckpoint:
    """Load a checkpoint produced by :func:`save_checkpoint` and return an eval-mode model."""
    path = Path(path)
    if not path.is_file():
        raise CheckpointError(f"Model checkpoint not found at '{path}'. Train a model first (see README).")
    try:
        # weights_only=True refuses arbitrary pickled objects: safe to load untrusted-origin files.
        payload = torch.load(path, map_location=device, weights_only=True)
    except Exception as exc:  # noqa: BLE001 - surface any torch load failure uniformly
        raise CheckpointError(f"Could not read checkpoint '{path}': {exc}") from exc

    if not isinstance(payload, dict) or "model_state_dict" not in payload:
        raise CheckpointError(f"'{path}' is not a valid brain tumor checkpoint.")
    if payload.get("format_version") != CHECKPOINT_FORMAT_VERSION:
        raise CheckpointError(
            f"Unsupported checkpoint format {payload.get('format_version')!r}; "
            f"expected {CHECKPOINT_FORMAT_VERSION}. Re-train the model."
        )

    if payload.get("preprocessing_version") != PREPROCESSING_VERSION:
        raise CheckpointError(
            f"Checkpoint was trained with preprocessing v{payload.get('preprocessing_version')}, "
            f"but this application expects v{PREPROCESSING_VERSION}. Re-train the model."
        )

    class_names = tuple(payload.get("class_names", ()))
    if class_names != CLASS_NAMES:
        raise CheckpointError(
            f"Checkpoint classes {class_names} do not match the application classes {CLASS_NAMES}."
        )

    img_size = int(payload["img_size"])
    model = BrainTumorCNN(num_classes=len(class_names))
    try:
        model.load_state_dict(payload["model_state_dict"])
    except RuntimeError as exc:
        raise CheckpointError(f"Checkpoint weights do not fit the model architecture: {exc}") from exc
    model.to(device)
    model.eval()
    return LoadedCheckpoint(
        model=model,
        class_names=class_names,
        img_size=img_size,
        metadata={
            "architecture": payload.get("architecture", ARCHITECTURE_NAME),
            "saved_at": payload.get("saved_at"),
            **payload.get("metadata", {}),
        },
    )
