"""Shared fixtures. Tests use a tiny, randomly initialised model so they run in seconds."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from backend import create_app
from backend.config import Config
from ml.checkpoint import save_checkpoint
from ml.constants import CLASS_NAMES
from ml.model import BrainTumorCNN

TEST_IMG_SIZE = 64


def make_png_bytes(size=(96, 96), mode="L", seed=0) -> bytes:
    rng = np.random.default_rng(seed)
    array = rng.integers(0, 255, size=(size[1], size[0]), dtype=np.uint8)
    image = Image.fromarray(array, mode="L").convert(mode)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def tiny_checkpoint(tmp_path: Path) -> Path:
    torch.manual_seed(0)
    model = BrainTumorCNN()
    return save_checkpoint(
        tmp_path / "models" / "tiny.pt",
        model,
        img_size=TEST_IMG_SIZE,
        metadata={"architecture": "BrainTumorCNN", "test_accuracy": 0.9, "epochs_run": 1},
    )


@pytest.fixture()
def app(tmp_path: Path, tiny_checkpoint: Path):
    config = Config(
        model_path=tiny_checkpoint,
        data_dir=tmp_path / "instance",
        max_upload_mb=2,
        low_confidence_threshold=0.6,
        upload_ttl_seconds=3600,
        log_level="WARNING",
    )
    return create_app(config)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def unloaded_app(tmp_path: Path):
    config = Config(
        model_path=tmp_path / "missing.pt",
        data_dir=tmp_path / "instance",
        log_level="WARNING",
    )
    return create_app(config)


@pytest.fixture()
def png_bytes() -> bytes:
    return make_png_bytes()


@pytest.fixture()
def class_names() -> tuple[str, ...]:
    return CLASS_NAMES
