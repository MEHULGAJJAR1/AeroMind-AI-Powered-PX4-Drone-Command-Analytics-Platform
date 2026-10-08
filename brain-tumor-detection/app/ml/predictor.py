"""Model registry and inference service.

``Predictor`` owns exactly one loaded model per process:

* resolves the checkpoint inside ``model_dir`` (``model.pt`` checkpoint bundle or
  ``model_scripted.pt`` TorchScript archive, plus an optional ``metadata.json``),
* selects the device (cuda → mps → cpu, overridable),
* runs preprocessing + inference behind a lock (Flask serves requests from
  several threads; PyTorch modules are not required to be re-entrant here),
* returns a plain, JSON-serialisable result dict.

The server keeps working when no checkpoint exists — it reports
``model_available: false`` through ``/api/health`` and ``POST /api/predict``
answers with HTTP 503 + a helpful message instead of crashing at boot.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from app.core.exceptions import ModelUnavailableError, PredictionError
from app.core.logging import get_logger
from app.ml.cnn import model_from_config
from app.ml.preprocess import PreprocessSpec, preprocess_image, preprocess_to_pil

CHECKPOINT_NAME = "model.pt"
SCRIPTED_NAME = "model_scripted.pt"
METADATA_NAME = "metadata.json"
FORMAT_VERSION = 1

DECISION_LABELS = {
    "tumor": "Possible tumor — radiologist review recommended",
    "no_tumor": "No tumor detected",
}


def resolve_device(requested: str = "auto") -> str:
    requested = (requested or "auto").lower()
    if requested not in {"auto", "cpu", "cuda", "mps"}:
        get_logger().warning("Unknown device '%s' requested — falling back to auto", requested)
        requested = "auto"
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class PredictionResult:
    """Structured prediction output."""

    label: str
    display_name: str
    is_tumor: bool
    confidence: float
    probabilities: dict[str, float]
    uncertain: bool
    timing: dict[str, float]
    model: dict[str, Any]
    preprocess: dict[str, Any]
    preprocessed_image: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prediction": {
                "label": self.label,
                "display_name": self.display_name,
                "is_tumor": self.is_tumor,
                "confidence": self.confidence,
                "probabilities": self.probabilities,
                "uncertain": self.uncertain,
                "recommendation": DECISION_LABELS.get(self.label, ""),
            },
            "model": self.model,
            "timing": self.timing,
            "preprocess": self.preprocess,
        }
        if self.preprocessed_image:
            payload["preprocessed_image"] = self.preprocessed_image
        return payload


class Predictor:
    """Loads a checkpoint once and serves thread-safe inference."""

    def __init__(
        self,
        model_dir: str | Path,
        *,
        device: str = "auto",
        class_labels: tuple[str, ...] | list[str] = ("no_tumor", "tumor"),
        uncertainty_threshold: float = 0.6,
        prefer_scripted: bool = True,
        warmup: bool = True,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.requested_device = device
        self.device_name = resolve_device(device)
        self.class_labels: list[str] = list(class_labels)
        self.uncertainty_threshold = float(uncertainty_threshold)
        self.prefer_scripted = prefer_scripted

        self._lock = threading.RLock()
        self._model: torch.nn.Module | torch.jit.ScriptModule | None = None
        self._spec: PreprocessSpec = PreprocessSpec()
        self._metadata: dict[str, Any] = {}
        self._loaded_at: float | None = None
        self._source_file: Path | None = None
        self._warmup = warmup
        self._load_error: str | None = None

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def spec(self) -> PreprocessSpec:
        """The preprocessing spec this model was trained with.

        Always use this (never rebuild a spec from ``public_metadata()``) when you
        need to feed the model yourself, e.g. in ``training/evaluate.py``.
        """
        return self._spec

    def load(self) -> "Predictor":
        """Load the checkpoint from ``model_dir`` (no-op if already loaded)."""
        with self._lock:
            if self._model is not None:
                return self
            self._load_error = None

            metadata = self._read_sidecar_metadata()
            scripted_path = self.model_dir / SCRIPTED_NAME
            checkpoint_path = self.model_dir / CHECKPOINT_NAME

            try:
                if self.prefer_scripted and scripted_path.is_file():
                    self._load_scripted(scripted_path, metadata)
                elif checkpoint_path.is_file():
                    self._load_checkpoint(checkpoint_path, metadata)
                elif scripted_path.is_file():
                    self._load_scripted(scripted_path, metadata)
                else:
                    self._load_error = (
                        f"No model checkpoint found in {self.model_dir} (expected {CHECKPOINT_NAME}). "
                        f"{ModelUnavailableError.message}"
                    )
                    get_logger().warning("%s", self._load_error)
                    return self
            except ModelUnavailableError as exc:
                # A broken checkpoint must degrade the service, not crash the boot.
                self._load_error = str(exc)
                get_logger().error("Model load failed: %s", exc)
                return self

            self._spec = PreprocessSpec.from_metadata(self._metadata)
            self.class_labels = list(self._metadata.get("class_labels") or self.class_labels)
            self._loaded_at = time.time()
            get_logger().info(
                "Model loaded from %s (device=%s, classes=%s, input=%dpx x %dch)",
                self._source_file.name if self._source_file else "?",
                self.device_name,
                self.class_labels,
                self._spec.img_size,
                self._spec.channels,
            )
            if self._warmup:
                self._warm_up()
            return self

    def reload(self) -> "Predictor":
        with self._lock:
            self._model = None
        return self.load()

    def _read_sidecar_metadata(self) -> dict[str, Any]:
        path = self.model_dir / METADATA_NAME
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            get_logger().warning("Could not read %s: %s", path, exc)
            return {}

    def _load_scripted(self, path: Path, sidecar: dict[str, Any]) -> None:
        device = torch.device(self.device_name)
        try:
            model = torch.jit.load(str(path), map_location=device)
        except Exception as exc:  # pragma: no cover - corrupt archive
            raise ModelUnavailableError(f"Could not load TorchScript model {path.name}: {exc}") from exc
        model.eval()
        self._model = model
        self._source_file = path
        self._metadata = sidecar or {"architecture": {"architecture": "torchscript"}}

    def _load_checkpoint(self, path: Path, sidecar: dict[str, Any]) -> None:
        device = torch.device(self.device_name)
        try:
            bundle = torch.load(str(path), map_location=device, weights_only=False)
        except Exception as exc:
            raise ModelUnavailableError(f"Could not read checkpoint {path.name}: {exc}") from exc

        if not isinstance(bundle, dict) or "state_dict" not in bundle:
            raise ModelUnavailableError(
                f"{path.name} is not a BrainScan checkpoint bundle "
                "(expected a dict with a 'state_dict' key). Re-export it with training/train.py."
            )

        arch_config = bundle.get("architecture") or {"architecture": "cnn"}
        try:
            model = model_from_config(arch_config)
        except Exception as exc:
            raise ModelUnavailableError(f"Could not rebuild the model architecture: {exc}") from exc

        try:
            model.load_state_dict(bundle["state_dict"], strict=True)
        except Exception as exc:
            raise ModelUnavailableError(f"Checkpoint weights do not match the architecture: {exc}") from exc

        model.to(device)
        model.eval()
        self._model = model
        self._source_file = path
        self._metadata = {**(bundle.get("metadata") or {}), **sidecar}
        if bundle.get("class_labels"):
            self._metadata.setdefault("class_labels", bundle["class_labels"])

    def _warm_up(self) -> None:
        """Run one dummy inference so the first real request is fast."""
        try:
            dummy = torch.zeros(
                (1, self._spec.channels, self._spec.img_size, self._spec.img_size),
                device=torch.device(self.device_name),
            )
            with torch.no_grad():
                self._model(dummy)  # type: ignore[misc]
        except Exception as exc:  # pragma: no cover - defensive
            get_logger().warning("Model warm-up skipped: %s", exc)

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def predict(
        self,
        image: Image.Image,
        *,
        include_preprocessed: bool = False,
    ) -> PredictionResult:
        if not self.is_loaded:
            raise ModelUnavailableError(self._load_error or "No model is loaded.")

        started = time.perf_counter()
        try:
            tensor, preprocess_meta = preprocess_image(image, self._spec)
        except Exception as exc:
            raise PredictionError(f"Image preprocessing failed: {exc}") from exc
        preprocess_done = time.perf_counter()

        preprocessed_b64: str | None = None
        if include_preprocessed:
            try:
                preview, _ = preprocess_to_pil(image, self._spec)
                buffer = io.BytesIO()
                preview.save(buffer, format="PNG")
                preprocessed_b64 = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
            except Exception as exc:  # pragma: no cover - preview is best effort
                get_logger().warning("Could not render preprocessed preview: %s", exc)

        device = torch.device(self.device_name)
        tensor = tensor.to(device, non_blocking=True)

        with self._lock:
            try:
                with torch.no_grad():
                    logits = self._model(tensor)  # type: ignore[misc]
                    probs = torch.softmax(logits.float(), dim=1)[0]
            except Exception as exc:
                raise PredictionError(f"Inference failed: {exc}") from exc

        values = probs.detach().cpu().numpy()
        probabilities = {
            label: round(float(value), 6)
            for label, value in zip(self.class_labels, values)
        }
        index = int(values.argmax())
        label = self.class_labels[index] if index < len(self.class_labels) else f"class_{index}"
        confidence = round(float(values[index]), 6)
        inference_done = time.perf_counter()

        return PredictionResult(
            label=label,
            display_name=_display_name(label),
            is_tumor="tumor" in label and "no_" not in label,
            confidence=confidence,
            probabilities=probabilities,
            uncertain=confidence < self.uncertainty_threshold,
            timing={
                "preprocess_ms": round((preprocess_done - started) * 1000, 2),
                "inference_ms": round((inference_done - preprocess_done) * 1000, 2),
                "total_ms": round((inference_done - started) * 1000, 2),
            },
            model=self.public_metadata(),
            preprocess=preprocess_meta,
            preprocessed_image=preprocessed_b64,
        )

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def public_metadata(self) -> dict[str, Any]:
        metadata = dict(self._metadata or {})
        architecture = metadata.get("architecture") or {}
        metrics = metadata.get("metrics") or {}
        # Parameter count lives in the architecture block for checkpoints and in
        # metrics for TorchScript + sidecar metadata — accept either.
        parameters = architecture.get("parameters") if isinstance(architecture, dict) else None
        if parameters is None:
            parameters = metrics.get("parameters")
        return {
            "name": metadata.get("name", "BrainScan CNN"),
            "version": metadata.get("version", "1.0.0"),
            "architecture": architecture.get("architecture", "cnn") if isinstance(architecture, dict) else architecture,
            "parameters": parameters,
            "framework": f"PyTorch {torch.__version__}",
            "device": self.device_name,
            "class_labels": list(self.class_labels),
            "input": {
                "size": self._spec.img_size,
                "channels": self._spec.channels,
                "mean": list(self._spec.mean),
                "std": list(self._spec.std),
                "brain_extraction": self._spec.brain_extraction,
            },
            "checkpoint": self._source_file.name if self._source_file else None,
            "loaded": self.is_loaded,
            "loaded_at": self._loaded_at,
            "metrics": metadata.get("metrics"),
            "trained_at": metadata.get("trained_at"),
            "dataset": metadata.get("dataset"),
            "notes": metadata.get("notes"),
        }

    def health(self) -> dict[str, Any]:
        return {
            "available": self.is_loaded,
            "device": self.device_name,
            "model": self.public_metadata() if self.is_loaded else None,
            "error": None if self.is_loaded else self._load_error,
            "uncertainty_threshold": self.uncertainty_threshold,
        }


def _display_name(label: str) -> str:
    return {
        "no_tumor": "No tumor detected",
        "tumor": "Tumor detected",
    }.get(label, label.replace("_", " ").title())


def create_predictor(
    model_dir: str | Path,
    *,
    device: str = "auto",
    require_model: bool = False,
    uncertainty_threshold: float = 0.6,
    load: bool = True,
) -> Predictor:
    """Factory used by the Flask app factory and the CLI scripts."""
    predictor = Predictor(model_dir, device=device, uncertainty_threshold=uncertainty_threshold)
    if load:
        predictor.load()
        if require_model and not predictor.is_loaded:
            raise ModelUnavailableError()
    return predictor
