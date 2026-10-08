"""Image preprocessing shared by training, evaluation and the web backend.

Using one implementation guarantees the network sees identical pixels at
training time and at serving time (no train/serve skew).
"""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image, ImageOps
from torchvision import transforms as T


def to_rgb(image: Image.Image) -> Image.Image:
    """Return an 8-bit RGB image regardless of the input mode.

    * 16-bit / float greyscale data is min-max scaled to 8 bits.
    * Transparent pixels are composited onto black (MRI background).
    * EXIF orientation is applied so rotated scanner exports display correctly.
    """
    image = ImageOps.exif_transpose(image)

    if image.mode in ("I", "I;16", "I;16B", "F"):
        arr = np.asarray(image, dtype=np.float32)
        lo, hi = float(arr.min()), float(arr.max())
        scale = 255.0 / (hi - lo) if hi > lo else 0.0
        arr = np.clip((arr - lo) * scale, 0, 255).astype(np.uint8)
        image = Image.fromarray(arr, mode="L")

    if image.mode == "RGB":
        return image

    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")

    return image.convert("RGB")


class PerImageStandardize:
    """Z-score each image separately (zero mean, unit variance over all pixels).

    MRI intensities are not calibrated: scanner, gain and acquisition settings shift the
    whole histogram. Standardising per image removes that global shift, so the network
    has to learn anatomy rather than the brightness of a particular source.
    """

    def __call__(self, tensor: torch.Tensor) -> torch.Tensor:
        std = tensor.std().clamp_min(1e-5)
        return (tensor - tensor.mean()) / std

    def __repr__(self) -> str:
        return "PerImageStandardize()"


class RandomResolutionDrop:
    """With probability ``p``, down-sample to a random smaller size and back.

    Images in the wild come from scanners and exports with very different sharpness.
    Simulating lower resolution during training stops the model from using blur or
    pixelation (which correlate with the data source) as a shortcut.
    """

    def __init__(self, p: float = 0.5, min_scale: float = 0.35) -> None:
        self.p = p
        self.min_scale = min_scale

    def __call__(self, image: Image.Image) -> Image.Image:
        if torch.rand(1).item() >= self.p:
            return image
        width, height = image.size
        scale = self.min_scale + (1.0 - self.min_scale) * torch.rand(1).item()
        small = image.resize(
            (max(8, int(width * scale)), max(8, int(height * scale))), Image.Resampling.BILINEAR
        )
        return small.resize((width, height), Image.Resampling.BILINEAR)

    def __repr__(self) -> str:
        return f"RandomResolutionDrop(p={self.p}, min_scale={self.min_scale})"


def build_eval_transform(img_size: int) -> T.Compose:
    """Deterministic transform used for validation, testing and inference."""
    return T.Compose(
        [
            T.Resize((img_size, img_size), interpolation=T.InterpolationMode.BILINEAR, antialias=True),
            T.ToTensor(),
            PerImageStandardize(),
        ]
    )


def build_train_transform(img_size: int) -> T.Compose:
    """Stochastic augmentation for training.

    Geometry is kept mild (MRI slices share a standard orientation), while intensity,
    resolution and occlusion are varied strongly to cover acquisition differences.
    """
    return T.Compose(
        [
            T.Resize((img_size, img_size), interpolation=T.InterpolationMode.BILINEAR, antialias=True),
            RandomResolutionDrop(p=0.5, min_scale=0.35),
            T.RandomHorizontalFlip(p=0.5),
            T.RandomRotation(degrees=8, fill=0),
            T.RandomAffine(degrees=0, translate=(0.05, 0.05), scale=(0.9, 1.1)),
            T.ColorJitter(brightness=0.3, contrast=0.3),
            T.ToTensor(),
            PerImageStandardize(),
            T.RandomErasing(p=0.25, scale=(0.02, 0.08), value=0.0),
        ]
    )


def preprocess_image(image: Image.Image, img_size: int) -> torch.Tensor:
    """Convert a PIL image into a ``(1, 3, img_size, img_size)`` float tensor."""
    rgb = to_rgb(image)
    return build_eval_transform(img_size)(rgb).unsqueeze(0)
