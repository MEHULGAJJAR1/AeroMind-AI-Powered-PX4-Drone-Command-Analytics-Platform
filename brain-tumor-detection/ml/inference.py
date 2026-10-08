"""Single-image inference used by both the CLI and the Flask service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image

from .checkpoint import LoadedCheckpoint, load_checkpoint
from .constants import NO_TUMOR_CLASS
from .preprocessing import preprocess_image


@dataclass(frozen=True)
class Prediction:
    """Result of classifying one MRI slice."""

    predicted_class: str
    confidence: float
    probabilities: dict[str, float]

    @property
    def tumor_detected(self) -> bool:
        return self.predicted_class != NO_TUMOR_CLASS


class Predictor:
    """Wraps a loaded model and turns PIL images into :class:`Prediction` objects."""

    def __init__(self, loaded: LoadedCheckpoint, device: str | torch.device = "cpu") -> None:
        self.device = torch.device(device)
        self.model = loaded.model.to(self.device).eval()
        self.class_names = loaded.class_names
        self.img_size = loaded.img_size
        self.metadata = loaded.metadata

    @classmethod
    def from_checkpoint(cls, path: Path, device: str | torch.device = "cpu") -> "Predictor":
        return cls(load_checkpoint(path, device=device), device=device)

    @torch.inference_mode()
    def predict(self, image: Image.Image) -> Prediction:
        tensor = preprocess_image(image, self.img_size).to(self.device)
        logits = self.model(tensor)
        probs = torch.softmax(logits, dim=1)[0].cpu().tolist()
        best = max(range(len(probs)), key=probs.__getitem__)
        return Prediction(
            predicted_class=self.class_names[best],
            confidence=float(probs[best]),
            probabilities={name: float(p) for name, p in zip(self.class_names, probs)},
        )
