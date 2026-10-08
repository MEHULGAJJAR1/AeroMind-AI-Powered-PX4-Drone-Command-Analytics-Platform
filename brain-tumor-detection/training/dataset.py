"""Dataset discovery, splitting and augmentation.

Supported directory layouts (the two most common for public brain-MRI sets):

    data/brain-tumor/            data/brain-tumor/
    ├── no/    *.jpg             ├── Train/
    └── yes/   *.jpg             │   ├── no/   *.jpg
                                 │   └── yes/  *.jpg
                                 └── Test/
                                     ├── no/   *.jpg
                                     └── yes/  *.jpg

Folder names are normalised to the canonical labels ``no_tumor`` / ``tumor`` —
``no``, ``notumor``, ``negative``, ``healthy`` and ``0`` all map to
``no_tumor``; ``yes``, ``tumor``, ``tumour``, ``positive``, ``1``, ``glioma``,
``meningioma`` and ``pituitary`` map to ``tumor`` (the multi-class Kaggle set is
therefore usable for this binary task).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import torch
from PIL import Image, ImageEnhance, ImageOps

from app.ml.preprocess import PreprocessSpec, crop_to_brain, normalize_mode

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

NO_TUMOR_ALIASES = {"no", "notumor", "no_tumor", "no-tumor", "negative", "healthy", "normal", "0", "false"}
TUMOR_ALIASES = {
    "yes",
    "tumor",
    "tumour",
    "tumor_",
    "positive",
    "1",
    "true",
    "glioma",
    "glioma_tumor",
    "meningioma",
    "meningioma_tumor",
    "pituitary",
    "pituitary_tumor",
}
CLASS_LABELS: tuple[str, ...] = ("no_tumor", "tumor")
SPLIT_FOLDER_NAMES = {"train", "val", "valid", "validation", "test", "testing"}


class DatasetError(RuntimeError):
    """The provided directory is not a usable dataset."""


def normalize_class_name(raw: str) -> str | None:
    """Map a folder name onto ``no_tumor`` / ``tumor`` (``None`` when unknown)."""
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in NO_TUMOR_ALIASES:
        return "no_tumor"
    if cleaned in TUMOR_ALIASES:
        return "tumor"
    if "no" in cleaned and "tumor" in cleaned and not cleaned.startswith("tumor"):
        return "no_tumor"
    if "tumor" in cleaned or "tumour" in cleaned:
        return "tumor"
    return None


@dataclass
class DatasetIndex:
    """Every image found in a dataset root, grouped by split."""

    root: Path
    paths: dict[str, list[Path]]
    labels: dict[str, list[int]]
    class_names: tuple[str, ...] = CLASS_LABELS

    def __len__(self) -> int:
        return sum(len(v) for v in self.paths.values())

    @property
    def splits(self) -> list[str]:
        return list(self.paths)

    def summary(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for split in self.paths:
            tally = {name: 0 for name in self.class_names}
            for label in self.labels[split]:
                tally[self.class_names[label]] += 1
            out[split] = tally
        return out


def _iter_images(folder: Path) -> Iterable[Path]:
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def discover_dataset(root: str | Path) -> DatasetIndex:
    """Walk ``root`` and index every image into canonical binary classes."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise DatasetError(f"Dataset directory not found: {root}")

    paths: dict[str, list[Path]] = {"train": []}
    labels: dict[str, list[int]] = {"train": []}
    skipped: list[str] = []

    def add(split: str, class_dir: Path, label: int) -> None:
        files = list(_iter_images(class_dir))
        if not files:
            skipped.append(str(class_dir))
        paths.setdefault(split, []).extend(files)
        labels.setdefault(split, []).extend([label] * len(files))

    # Layout A: <root>/<split>/<class>/images   Layout B: <root>/<class>/images
    child_dirs = [d for d in sorted(root.iterdir()) if d.is_dir()]
    has_split_layout = any(d.name.lower() in SPLIT_FOLDER_NAMES for d in child_dirs)

    if has_split_layout:
        for split_dir in child_dirs:
            split_name = split_dir.name.lower()
            split_key = {"valid": "val", "validation": "val", "testing": "test"}.get(split_name, split_name)
            if split_key == "val":
                split_key = "train"  # merged into train below unless a test split exists
            for class_dir in [d for d in sorted(split_dir.iterdir()) if d.is_dir()]:
                label = normalize_class_name(class_dir.name)
                if label is None:
                    skipped.append(str(class_dir))
                    continue
                add(split_key, class_dir, CLASS_LABELS.index(label))
    else:
        for class_dir in child_dirs:
            label = normalize_class_name(class_dir.name)
            if label is None:
                skipped.append(str(class_dir))
                continue
            add("train", class_dir, CLASS_LABELS.index(label))

    total = sum(len(v) for v in paths.values())
    if total == 0:
        raise DatasetError(
            f"No labelled images found under {root}. Expected sub-folders such as 'no'/'yes' or "
            f"'Train/no'/'Train/yes'. Skipped: {skipped[:5] or 'n/a'}"
        )

    # Drop empty splits, but always keep 'train'.
    for split in list(paths):
        if not paths[split]:
            paths.pop(split)
            labels.pop(split)

    return DatasetIndex(root=root, paths=paths, labels=labels)


def split_index(
    index: DatasetIndex,
    *,
    val_fraction: float = 0.15,
    seed: int = 42,
) -> tuple[list[Path], list[int], list[Path], list[int]]:
    """Return ``(train_paths, train_labels, val_paths, val_labels)``.

    If the dataset ships an explicit ``test``/``val`` split it is used as-is,
    otherwise a stratified random split is drawn from the ``train`` pool.
    """
    all_paths = index.paths.get("train", [])
    all_labels = index.labels.get("train", [])

    extra_paths = index.paths.get("test", []) + index.paths.get("val", [])
    extra_labels = index.labels.get("test", []) + index.labels.get("val", [])

    if extra_paths and val_fraction > 0:
        return list(all_paths), list(all_labels), list(extra_paths), list(extra_labels)

    if val_fraction <= 0:
        return list(all_paths), list(all_labels), [], []

    rng = random.Random(seed)
    by_class: dict[int, list[int]] = {}
    for position, label in enumerate(all_labels):
        by_class.setdefault(label, []).append(position)

    train_pos: list[int] = []
    val_pos: list[int] = []
    for positions in by_class.values():
        shuffled = positions[:]
        rng.shuffle(shuffled)
        cut = max(1, int(round(len(shuffled) * val_fraction))) if len(shuffled) > 1 else 0
        val_pos.extend(shuffled[:cut])
        train_pos.extend(shuffled[cut:])

    train_pos.sort()
    val_pos.sort()
    return (
        [all_paths[i] for i in train_pos],
        [all_labels[i] for i in train_pos],
        [all_paths[i] for i in val_pos],
        [all_labels[i] for i in val_pos],
    )


def compute_class_weights(labels: Sequence[int], num_classes: int = 2) -> list[float]:
    """Inverse-frequency weights, rescaled so their mean is 1.

    The rescaling keeps the gradient magnitude comparable to an unweighted loss
    while still up-weighting the minority class.
    """
    counts = np.bincount(np.asarray(labels, dtype=int), minlength=num_classes).astype(np.float64)
    counts = np.where(counts == 0, 1.0, counts)  # avoid division by zero for absent classes
    weights = counts.sum() / (num_classes * counts)
    mean = float(weights.mean())
    if mean > 0:
        weights = weights / mean
    return [round(float(w), 4) for w in weights]


# --------------------------------------------------------------------------- #
# Augmentation (PIL based — matches the serving pipeline exactly)
# --------------------------------------------------------------------------- #
@dataclass
class AugmentationConfig:
    rotation: float = 15.0
    horizontal_flip: float = 0.5
    vertical_flip: float = 0.1
    translation: float = 0.08
    scale: tuple[float, float] = (0.9, 1.1)
    brightness: tuple[float, float] = (0.85, 1.15)
    contrast: tuple[float, float] = (0.85, 1.15)
    sharpen: float = 0.2
    noise_std: float = 0.015


def augment_image(image: Image.Image, config: AugmentationConfig, rng: random.Random) -> Image.Image:
    """Apply a random subset of augmentations to a PIL image."""
    if rng.random() < config.horizontal_flip:
        image = ImageOps.mirror(image)
    if rng.random() < config.vertical_flip:
        image = ImageOps.flip(image)
    if config.rotation:
        image = image.rotate(rng.uniform(-config.rotation, config.rotation), resample=Image.Resampling.BILINEAR)

    if config.translation or config.scale != (1.0, 1.0):
        width, height = image.size
        dx = rng.uniform(-config.translation, config.translation) * width
        dy = rng.uniform(-config.translation, config.translation) * height
        zoom = rng.uniform(*config.scale)
        # PIL affine maps output→input, so invert the transform.
        matrix = (1 / zoom, 0, -dx / zoom, 0, 1 / zoom, -dy / zoom)
        image = image.transform(image.size, Image.Transform.AFFINE, matrix, resample=Image.Resampling.BILINEAR)

    if rng.random() < 0.6:
        image = ImageEnhance.Brightness(image).enhance(rng.uniform(*config.brightness))
    if rng.random() < 0.6:
        image = ImageEnhance.Contrast(image).enhance(rng.uniform(*config.contrast))
    if rng.random() < config.sharpen:
        image = ImageEnhance.Sharpness(image).enhance(rng.uniform(1.0, 1.6))
    return image


def add_gaussian_noise(array: np.ndarray, std: float, rng: np.random.Generator) -> np.ndarray:
    if std <= 0:
        return array
    noise = rng.normal(0.0, std, size=array.shape).astype(np.float32)
    return np.clip(array + noise, 0.0, 1.0)


class BrainMRIDataset(torch.utils.data.Dataset):
    """Maps image paths to ``(tensor, label)`` using the serving preprocessing."""

    def __init__(
        self,
        paths: Sequence[Path],
        labels: Sequence[int],
        spec: PreprocessSpec,
        *,
        augment: bool = False,
        augmentation: AugmentationConfig | None = None,
        noise_std: float = 0.0,
        seed: int = 42,
    ) -> None:
        if len(paths) != len(labels):
            raise ValueError("paths and labels must have the same length")
        self.paths = list(paths)
        self.labels = list(labels)
        self.spec = spec
        self.augment = augment
        self.augmentation = augmentation or AugmentationConfig()
        self.noise_std = noise_std
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)
        self.skipped: list[str] = []

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        path = self.paths[index]
        label = int(self.labels[index])

        try:
            image = Image.open(path)
            image.load()
            image = ImageOps.exif_transpose(image)
        except Exception as exc:  # unreadable files must not kill an epoch
            self.skipped.append(f"{path.name}: {exc}")
            image = Image.new("RGB" if self.spec.channels == 3 else "L", (self.spec.img_size, self.spec.img_size))

        image = normalize_mode(image, self.spec.channels)
        if self.spec.brain_extraction:
            image, _ = crop_to_brain(image, margin_ratio=self.spec.brain_margin)
        if self.augment:
            image = augment_image(image, self.augmentation, self._rng)

        image = image.resize((self.spec.img_size, self.spec.img_size), Image.Resampling.LANCZOS)
        array = np.asarray(image, dtype=np.float32) / 255.0
        if array.ndim == 2:
            array = array[:, :, None]
        if self.augment and self.noise_std > 0:
            array = add_gaussian_noise(array, self.noise_std, self._np_rng)

        mean = np.asarray(self.spec.mean, dtype=np.float32).reshape(1, 1, -1)
        std = np.asarray(self.spec.std, dtype=np.float32).reshape(1, 1, -1)
        tensor = torch.from_numpy((array - mean) / std).permute(2, 0, 1).contiguous()
        return tensor, label


def label_counts(labels: Sequence[int], class_names: Sequence[str] = CLASS_LABELS) -> dict[str, int]:
    counts = {name: 0 for name in class_names}
    for label in labels:
        counts[class_names[label]] += 1
    return counts
