"""Dataset discovery, stratified splitting and the PyTorch ``Dataset`` wrapper.

Expected layout (the Kaggle "Brain Tumor MRI Dataset" structure)::

    <data-dir>/
        Training/
            glioma_tumor/*.jpg  meningioma_tumor/*.jpg  no_tumor/*.jpg  pituitary_tumor/*.jpg
        Testing/
            (same four folders)
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset

from .constants import CLASS_NAMES, FOLDER_TO_CLASS, IMAGE_EXTENSIONS
from .preprocessing import to_rgb

TRAIN_DIR_NAME = "Training"
TEST_DIR_NAME = "Testing"


class DatasetError(ValueError):
    """Raised when the dataset folder does not match the expected layout."""


@dataclass(frozen=True)
class Sample:
    path: Path
    label: int  # index into CLASS_NAMES

    @property
    def class_name(self) -> str:
        return CLASS_NAMES[self.label]


def discover_samples(split_dir: Path) -> list[Sample]:
    """List every labelled image under ``split_dir``. Unknown folders are ignored."""
    if not split_dir.is_dir():
        raise DatasetError(f"Expected folder '{split_dir}' does not exist.")

    samples: list[Sample] = []
    for folder in sorted(p for p in split_dir.iterdir() if p.is_dir()):
        class_name = FOLDER_TO_CLASS.get(folder.name)
        if class_name is None:
            continue
        for image_path in sorted(folder.iterdir()):
            if image_path.suffix.lower() in IMAGE_EXTENSIONS and image_path.is_file():
                samples.append(Sample(image_path, CLASS_NAMES.index(class_name)))

    found = {s.class_name for s in samples}
    missing = [c for c in CLASS_NAMES if c not in found]
    if missing:
        raise DatasetError(
            f"No images found for class(es) {missing} under '{split_dir}'. "
            f"Expected folders: {sorted(FOLDER_TO_CLASS)}."
        )
    return samples


def load_dataset_splits(data_dir: Path) -> tuple[list[Sample], list[Sample]]:
    """Return ``(training_pool, held_out_test)`` discovered from ``data_dir``."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise DatasetError(f"Data directory '{data_dir}' does not exist.")
    train = discover_samples(data_dir / TRAIN_DIR_NAME)
    test = discover_samples(data_dir / TEST_DIR_NAME)
    return train, test


def limit_per_class(samples: Sequence[Sample], max_per_class: int | None, seed: int) -> list[Sample]:
    """Randomly keep at most ``max_per_class`` images per class (for quick experiments)."""
    if not max_per_class:
        return list(samples)
    rng = random.Random(seed)
    grouped: dict[int, list[Sample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.label].append(sample)
    kept: list[Sample] = []
    for label in sorted(grouped):
        pool = grouped[label]
        rng.shuffle(pool)
        kept.extend(pool[:max_per_class])
    return kept


def stratified_split(
    samples: Sequence[Sample], val_fraction: float, seed: int
) -> tuple[list[Sample], list[Sample]]:
    """Split into (train, validation) keeping class proportions in both parts."""
    if not 0.0 < val_fraction < 1.0:
        raise ValueError("val_fraction must be between 0 and 1 (exclusive).")
    rng = random.Random(seed)
    grouped: dict[int, list[Sample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.label].append(sample)

    train: list[Sample] = []
    val: list[Sample] = []
    for label in sorted(grouped):
        pool = sorted(grouped[label], key=lambda s: str(s.path))
        rng.shuffle(pool)
        n_val = max(1, round(len(pool) * val_fraction))
        val.extend(pool[:n_val])
        train.extend(pool[n_val:])
    rng.shuffle(train)
    return train, val


def class_weights(samples: Sequence[Sample]) -> torch.Tensor:
    """Inverse-frequency weights (normalised to mean 1) to counter class imbalance."""
    counts = torch.zeros(len(CLASS_NAMES))
    for sample in samples:
        counts[sample.label] += 1
    counts = torch.clamp(counts, min=1.0)
    weights = counts.sum() / (len(CLASS_NAMES) * counts)
    return weights / weights.mean()


class MRIDataset(Dataset):
    """Loads an MRI image from disk, converts it to RGB and applies ``transform``."""

    def __init__(self, samples: Sequence[Sample], transform: Callable[[Image.Image], torch.Tensor]) -> None:
        self.samples = list(samples)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        sample = self.samples[index]
        with Image.open(sample.path) as image:
            rgb = to_rgb(image)
        return self.transform(rgb), sample.label
