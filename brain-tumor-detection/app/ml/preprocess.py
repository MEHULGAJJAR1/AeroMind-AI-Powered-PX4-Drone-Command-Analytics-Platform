"""Image loading, validation helpers and the inference preprocessing pipeline.

The pipeline mirrors what the training code does:

1. decode + integrity check (``PIL.Image.verify``)
2. apply EXIF orientation
3. convert to the channel layout the model expects
4. optional **brain extraction** — Otsu threshold, morphological cleanup,
   largest connected component, padded bounding box (MRI scans usually contain
   a lot of black padding and annotation text; cropping to the head makes the
   classifier's job much easier and more stable across datasets)
5. resize to the model input size
6. scale to ``[0, 1]`` and normalise per channel
7. ``HWC`` → ``CHW`` and add the batch dimension

Every step is pure (numpy / Pillow / scipy) so it can be unit tested without a
trained checkpoint.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

import numpy as np
import torch
from PIL import Image, ImageOps, UnidentifiedImageError

# Pillow raises for absurdly large images; we set our own (configurable) guard.
DEFAULT_MAX_IMAGE_PIXELS = 89_478_485

_MODE_BY_CHANNELS = {1: "L", 3: "RGB"}


class ImageLoadError(ValueError):
    """Raised when a byte stream cannot be decoded into a usable image."""


@dataclass(frozen=True)
class PreprocessSpec:
    """Everything needed to turn a PIL image into a model input tensor.

    ``mean`` / ``std`` default to 0.5 per channel and are expanded to match
    ``channels`` automatically.
    """

    img_size: int = 224
    channels: int = 3
    mean: tuple[float, ...] | float | None = None
    std: tuple[float, ...] | float | None = None
    brain_extraction: bool = True
    brain_margin: float = 0.08
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.channels not in _MODE_BY_CHANNELS:
            raise ValueError(f"Unsupported channel count: {self.channels} (use 1 or 3)")
        if self.img_size < 16:
            raise ValueError("img_size must be at least 16")
        object.__setattr__(self, "mean", _as_channel_tuple(0.5 if self.mean is None else self.mean, self.channels))
        object.__setattr__(self, "std", _as_channel_tuple(0.5 if self.std is None else self.std, self.channels))

    # ------------------------------------------------------------------ (de)serialisation
    @classmethod
    def from_metadata(cls, metadata: dict[str, Any] | None) -> "PreprocessSpec":
        metadata = metadata or {}
        pre = metadata.get("preprocess") or metadata
        mean = pre.get("mean")
        std = pre.get("std")
        channels = int(pre.get("channels", metadata.get("channels", 3)))
        return cls(
            img_size=int(pre.get("img_size", metadata.get("img_size", 224))),
            channels=channels,
            mean=tuple(float(v) for v in _as_iterable(mean)) if mean is not None else None,
            std=tuple(float(v) for v in _as_iterable(std)) if std is not None else None,
            brain_extraction=bool(pre.get("brain_extraction", True)),
            brain_margin=float(pre.get("brain_margin", 0.08)),
        )

    def to_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("extras", None)
        data["mean"] = list(self.mean)
        data["std"] = list(self.std)
        return data


def _as_iterable(value: Any) -> Iterable[float]:
    if isinstance(value, (int, float)):
        return [float(value)]
    return value


def _as_channel_tuple(value: Any, channels: int) -> tuple[float, ...]:
    values = tuple(float(v) for v in _as_iterable(value))
    if len(values) == 1:
        values = values * channels
    if len(values) != channels:
        raise ValueError(f"Expected {channels} normalisation values, got {len(values)}")
    if any(v <= 0 for v in values):
        raise ValueError("std values must be strictly positive")
    return values


# --------------------------------------------------------------------------- #
# Decoding
# --------------------------------------------------------------------------- #
def open_image(
    raw: bytes,
    *,
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    min_dimension: int = 1,
) -> Image.Image:
    """Decode ``raw`` into a PIL image, verifying integrity and constraints.

    Raises :class:`ImageLoadError` with a human readable reason on failure.
    """
    if not raw:
        raise ImageLoadError("The uploaded file is empty.")

    # 1. Integrity check: verify() catches truncated / corrupt payloads.
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:  # SyntaxError: legacy Pillow
        raise ImageLoadError("The file could not be decoded as an image (it may be corrupt or truncated).") from exc

    # verify() consumes the file pointer — reopen for real use.
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError("The image data could not be read.") from exc

    width, height = image.size
    if width <= 0 or height <= 0:
        raise ImageLoadError("The image has invalid dimensions.")

    if max_pixels and width * height > max_pixels:
        raise ImageLoadError(
            f"The image is too large ({width}x{height} = {width * height:,} pixels, limit {max_pixels:,})."
        )

    if min_dimension and min(width, height) < min_dimension:
        raise ImageLoadError(
            f"The image is too small ({width}x{height}); the shortest side must be at least {min_dimension}px."
        )

    # 2. Honour EXIF orientation so phone/scan rotations behave.
    try:
        image = ImageOps.exif_transpose(image)
    except Exception:  # pragma: no cover - defensive, Pillow version differences
        pass

    # 3. Flatten to a standard mode (drops alpha/palette/16-bit oddities).
    return normalize_mode(image, channels=3)


def normalize_mode(image: Image.Image, channels: int = 3) -> Image.Image:
    """Convert to the Pillow mode matching ``channels`` (1 → L, 3 → RGB)."""
    target = _MODE_BY_CHANNELS[channels]
    if image.mode == target:
        return image.copy()
    if image.mode in {"RGBA", "LA", "PA", "P"}:
        # Composite transparency onto black (MRI background is black by convention).
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        return Image.alpha_composite(background, rgba).convert(target)
    return image.convert(target)


# --------------------------------------------------------------------------- #
# Brain extraction
# --------------------------------------------------------------------------- #
def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    """Classic Otsu threshold for a uint8-ish intensity array."""
    values = np.asarray(values, dtype=np.float64).ravel()
    if values.size == 0:
        return 0.0
    hist, edges = np.histogram(values, bins=bins, range=(0.0, 255.0))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return float(edges[0])

    centers = (edges[:-1] + edges[1:]) / 2.0
    weight_bg = np.cumsum(hist)
    weight_fg = total - weight_bg
    mean_bg_sum = np.cumsum(hist * centers)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_bg = mean_bg_sum / weight_bg
        mean_fg = (mean_bg_sum[-1] - mean_bg_sum) / weight_fg
    between = weight_bg * weight_fg * np.nan_to_num(mean_bg - mean_fg) ** 2
    if not np.isfinite(between).any():
        return float(centers[0])

    # With a bimodal histogram every threshold between the modes is optimal, so
    # the argmax plateaus. Take the middle of that plateau instead of its first
    # index (which would otherwise return a near-zero threshold).
    peak = float(np.nanmax(between))
    tolerance = max(peak * 1e-9, 1e-12)
    best_indices = np.flatnonzero(np.nan_to_num(between, nan=-1.0) >= peak - tolerance)
    best = int(best_indices[len(best_indices) // 2])
    return float(centers[best])


def _try_ndimage():
    """Import scipy.ndimage lazily so environments without scipy still work."""
    try:
        from scipy import ndimage  # type: ignore
    except ImportError:  # pragma: no cover - scipy is a declared dependency
        return None
    return ndimage


def extract_brain_bbox(
    gray: np.ndarray,
    *,
    margin_ratio: float = 0.08,
    min_area_ratio: float = 0.001,
) -> tuple[int, int, int, int] | None:
    """Return ``(x0, y0, x1, y1)`` of the head/tissue region or ``None``.

    ``None`` means "no confident foreground found" — callers should fall back to
    the full frame rather than failing the request.
    """
    ndimage = _try_ndimage()
    if ndimage is None or gray.size == 0:
        return None

    height, width = gray.shape
    mask = gray > otsu_threshold(gray)
    if mask.sum() < max(16, int(min_area_ratio * gray.size)):
        return None

    try:
        mask = ndimage.binary_closing(mask, iterations=2)
        mask = ndimage.binary_fill_holes(mask)
        labels, count = ndimage.label(mask)
        if count == 0:
            return None
        # Ignore the background label (0) and keep the biggest component.
        sizes = ndimage.sum(mask, labels, index=range(1, count + 1))
        biggest = int(np.argmax(sizes)) + 1
        if sizes[biggest - 1] < max(64, int(min_area_ratio * gray.size)):
            return None
        component = labels == biggest
        rows = np.where(component.any(axis=1))[0]
        cols = np.where(component.any(axis=0))[0]
    except Exception:  # pragma: no cover - defensive against exotic scipy builds
        return None

    if rows.size == 0 or cols.size == 0:
        return None

    y0, y1 = int(rows[0]), int(rows[-1])
    x0, x1 = int(cols[0]), int(cols[-1])

    # Padded, square-ish, clamped to the frame.
    pad = int(round(margin_ratio * max(x1 - x0, y1 - y0)))
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(width - 1, x1 + pad)
    y1 = min(height - 1, y1 + pad)

    if (x1 - x0) < 8 or (y1 - y0) < 8:
        return None
    return x0, y0, x1 + 1, y1 + 1


def crop_to_brain(image: Image.Image, *, margin_ratio: float = 0.08) -> tuple[Image.Image, tuple | None]:
    """Crop ``image`` to the detected head region; returns ``(image, bbox)``."""
    gray = np.asarray(image.convert("L"), dtype=np.float64)
    bbox = extract_brain_bbox(gray, margin_ratio=margin_ratio)
    if bbox is None:
        return image.copy(), None
    return image.crop(bbox), bbox


# --------------------------------------------------------------------------- #
# Tensor pipeline
# --------------------------------------------------------------------------- #
def image_to_array(image: Image.Image, spec: PreprocessSpec) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """Decode + crop + resize → ``(float32 HWC array in [0, 1], brain bbox)``."""
    image = normalize_mode(image, spec.channels)
    bbox: tuple | None = None
    if spec.brain_extraction:
        image, bbox = crop_to_brain(image, margin_ratio=spec.brain_margin)

    image = image.resize((spec.img_size, spec.img_size), Image.Resampling.LANCZOS)
    array = np.asarray(image, dtype=np.float32) / 255.0
    if array.ndim == 2:
        array = array[:, :, None]
    return array, bbox


def array_to_tensor(array: np.ndarray, spec: PreprocessSpec) -> torch.Tensor:
    """Normalise an ``HWC`` float array and reshape to ``1CHW``."""
    mean = np.asarray(spec.mean, dtype=np.float32).reshape(1, 1, -1)
    std = np.asarray(spec.std, dtype=np.float32).reshape(1, 1, -1)
    tensor = torch.from_numpy((array - mean) / std)
    return tensor.permute(2, 0, 1).unsqueeze(0).contiguous()


def preprocess_image(image: Image.Image, spec: PreprocessSpec) -> tuple[torch.Tensor, dict[str, Any]]:
    """Full pipeline → ``(tensor, metadata)``."""
    original_size = image.size
    array, bbox = image_to_array(image, spec)
    tensor = array_to_tensor(array, spec)
    metadata = {
        "original_size": {"width": original_size[0], "height": original_size[1]},
        "input_size": {"width": spec.img_size, "height": spec.img_size},
        "brain_bbox": list(bbox) if bbox else None,
        "brain_extraction": bool(spec.brain_extraction and bbox is not None),
        "channels": spec.channels,
        "mean": list(spec.mean),
        "std": list(spec.std),
    }
    return tensor, metadata


def preprocess_to_pil(image: Image.Image, spec: PreprocessSpec) -> tuple[Image.Image, dict[str, Any]]:
    """What the model actually sees, as a displayable PIL image (no normalisation)."""
    array, bbox = image_to_array(image, spec)
    mode = _MODE_BY_CHANNELS[spec.channels]
    preview = Image.fromarray((np.clip(array, 0.0, 1.0) * 255.0).astype(np.uint8), mode=mode)
    return preview, {
        "brain_bbox": list(bbox) if bbox else None,
        "brain_extraction": bool(spec.brain_extraction and bbox is not None),
    }


def tensor_to_preview(tensor: torch.Tensor, spec: PreprocessSpec) -> Image.Image:
    """Inverse of :func:`array_to_tensor` — handy for debugging/visual QA."""
    array = tensor.squeeze(0).permute(1, 2, 0).numpy()
    mean = np.asarray(spec.mean, dtype=np.float32).reshape(1, 1, -1)
    std = np.asarray(spec.std, dtype=np.float32).reshape(1, 1, -1)
    array = np.clip(array * std + mean, 0.0, 1.0)
    mode = _MODE_BY_CHANNELS[spec.channels]
    return Image.fromarray((array * 255.0).astype(np.uint8), mode=mode)
