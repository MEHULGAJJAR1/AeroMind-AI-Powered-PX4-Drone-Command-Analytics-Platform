"""Project-wide constants shared by training, evaluation and the web backend.

Keeping the class list and input geometry in one place guarantees that the
trainer, the checkpoint and the API always agree on label order and size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH: Final[Path] = PROJECT_ROOT / "models" / "brain_tumor_cnn.pt"

# Canonical class names. The order defines the output index of the network.
CLASS_NAMES: Final[tuple[str, ...]] = ("glioma", "meningioma", "no_tumor", "pituitary")
NO_TUMOR_CLASS: Final[str] = "no_tumor"

# Folder names used by the Kaggle "Brain Tumor MRI Dataset" layout, mapped to canonical names.
FOLDER_TO_CLASS: Final[dict[str, str]] = {
    "glioma_tumor": "glioma",
    "meningioma_tumor": "meningioma",
    "no_tumor": "no_tumor",
    "pituitary_tumor": "pituitary",
}

CLASS_DISPLAY_NAMES: Final[dict[str, str]] = {
    "glioma": "Glioma",
    "meningioma": "Meningioma",
    "no_tumor": "No tumor",
    "pituitary": "Pituitary tumor",
}

# Bump when the preprocessing pipeline changes; checkpoints record it and are rejected on mismatch.
#   1 = fixed mean/std normalisation (superseded)
#   2 = per-image standardisation + resolution/erasing augmentation
PREPROCESSING_VERSION: Final[int] = 2

DEFAULT_IMG_SIZE: Final[int] = 128
IMAGE_EXTENSIONS: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
