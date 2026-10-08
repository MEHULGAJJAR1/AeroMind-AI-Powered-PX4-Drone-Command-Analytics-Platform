"""Shared pytest fixtures.

Tests run against a real Flask app created by the application factory, pointed
at a temporary directory, with a tiny randomly-initialised checkpoint so the
full request path (validation → preprocessing → inference → history) executes.
"""

from __future__ import annotations

import dataclasses
import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config  # noqa: E402
from app.factory import create_app  # noqa: E402
from app.ml.cnn import BrainTumorCNN  # noqa: E402
from app.ml.predictor import CHECKPOINT_NAME, METADATA_NAME  # noqa: E402
from app.ml.preprocess import PreprocessSpec  # noqa: E402
from training.synthetic import make_phantom  # noqa: E402

IMG_SIZE = 64
CLASS_LABELS = ("no_tumor", "tumor")


def write_checkpoint(model_dir: Path, *, img_size: int = IMG_SIZE, channels: int = 3) -> Path:
    """Write a small, randomly-initialised but valid checkpoint bundle."""
    model_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)
    model = BrainTumorCNN(in_channels=channels, num_classes=2, base_channels=8)
    spec = PreprocessSpec(img_size=img_size, channels=channels, brain_extraction=True)
    metadata = {
        "name": "Test CNN",
        "version": "test",
        "class_labels": list(CLASS_LABELS),
        "channels": channels,
        "img_size": img_size,
        "preprocess": spec.to_metadata(),
        "architecture": {
            "architecture": "cnn",
            "in_channels": channels,
            "num_classes": 2,
            "base_channels": 8,
            "dropout": 0.15,
            "classifier_dropout": 0.4,
        },
        "metrics": {"val_accuracy": 0.9325, "val_f1": 0.93},
        "trained_at": "2026-01-01T00:00:00+00:00",
        "notes": "unit-test fixture",
    }
    path = model_dir / CHECKPOINT_NAME
    torch.save(
        {
            "format_version": 1,
            "architecture": metadata["architecture"],
            "state_dict": model.state_dict(),
            "class_labels": list(CLASS_LABELS),
            "metadata": metadata,
        },
        path,
    )
    (model_dir / METADATA_NAME).write_text(json.dumps(metadata), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def checkpoint_dir(tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp("models")
    write_checkpoint(directory)
    return directory


@pytest.fixture()
def app(tmp_path, checkpoint_dir):
    config = dataclasses.replace(Config.for_testing(tmp_path), model_dir=checkpoint_dir)
    application = create_app(config)
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def small_client(tmp_path, checkpoint_dir):
    """App with a 1 MB upload limit, used for size-limit tests."""
    config = dataclasses.replace(
        Config.for_testing(tmp_path),
        model_dir=checkpoint_dir,
        max_upload_mb=1,
        max_content_length_mb=3,
    )
    return create_app(config).test_client()


@pytest.fixture()
def no_model_client(tmp_path):
    """App whose model directory contains no checkpoint (degraded mode)."""
    config = dataclasses.replace(Config.for_testing(tmp_path), model_dir=tmp_path / "no-model-here")
    return create_app(config).test_client()


@pytest.fixture()
def png_bytes() -> bytes:
    buffer = io.BytesIO()
    make_phantom(96, tumor=True, seed=3).convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    make_phantom(96, tumor=False, seed=9).convert("RGB").save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def noise_png(size: int = 80, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    array = (rng.random((size, size, 3)) * 255).astype("uint8")
    buffer = io.BytesIO()
    Image.fromarray(array, mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()
