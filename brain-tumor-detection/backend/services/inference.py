"""Model lifecycle and inference for the web service.

The model is loaded once at start-up. If the checkpoint is missing or invalid
the server still starts, reports the problem through ``/api/health`` and
``/api/model``, and returns HTTP 503 for prediction requests.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from ml.checkpoint import CheckpointError
from ml.constants import CLASS_NAMES, NO_TUMOR_CLASS
from ml.inference import Prediction, Predictor

from ..errors import ApiError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InferenceResult:
    prediction: Prediction
    inference_ms: float
    low_confidence: bool


class ModelService:
    def __init__(self, model_path: Path, device: str, low_confidence_threshold: float) -> None:
        self.model_path = Path(model_path)
        self.device = device
        self.low_confidence_threshold = low_confidence_threshold
        self._predictor: Predictor | None = None
        self._load_error: str | None = None
        self._version: str | None = None
        # PyTorch modules are not guaranteed to be re-entrant with shared buffers, so serialise inference.
        self._lock = threading.Lock()

    def load(self) -> bool:
        try:
            predictor = Predictor.from_checkpoint(self.model_path, device=self.device)
        except CheckpointError as exc:
            self._load_error = str(exc)
            logger.warning("Model not loaded: %s", exc)
            return False
        digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:12]
        self._version = f"BrainTumorCNN-{predictor.img_size}px-{digest}"
        self._predictor = predictor
        self._load_error = None
        logger.info("Loaded model %s from %s", self._version, self.model_path)
        return True

    @property
    def is_ready(self) -> bool:
        return self._predictor is not None

    @property
    def version(self) -> str | None:
        return self._version

    def describe(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "loaded": self.is_ready,
            "model_file": self.model_path.name,
            "version": self._version,
            "classes": list(CLASS_NAMES),
            "no_tumor_class": NO_TUMOR_CLASS,
            "low_confidence_threshold": self.low_confidence_threshold,
            "error": self._load_error,
        }
        if self._predictor is not None:
            meta = self._predictor.metadata
            info.update({
                "architecture": meta.get("architecture"),
                "img_size": self._predictor.img_size,
                "saved_at": meta.get("saved_at"),
                "epochs_run": meta.get("epochs_run"),
                "best_val_accuracy": meta.get("best_val_accuracy"),
                "test_accuracy": meta.get("test_accuracy"),
                "test_macro_f1": meta.get("test_macro_f1"),
            })
        return info

    def predict(self, image: Image.Image) -> InferenceResult:
        predictor = self._predictor
        if predictor is None:
            raise ApiError(
                503,
                "MODEL_UNAVAILABLE",
                "The prediction model is not loaded. Train it with `python -m ml.train` and restart the server.",
                {"reason": self._load_error},
            )
        started = time.perf_counter()
        with self._lock:
            prediction = predictor.predict(image)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return InferenceResult(
            prediction=prediction,
            inference_ms=round(elapsed_ms, 2),
            low_confidence=prediction.confidence < self.low_confidence_threshold,
        )
