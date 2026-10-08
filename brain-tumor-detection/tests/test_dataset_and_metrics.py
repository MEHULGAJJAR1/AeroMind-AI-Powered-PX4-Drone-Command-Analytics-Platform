import pytest
from PIL import Image

from ml.constants import CLASS_NAMES
from ml.dataset import (
    DatasetError,
    class_weights,
    discover_samples,
    limit_per_class,
    load_dataset_splits,
    stratified_split,
)
from ml.metrics import compute_classification_metrics, format_metrics_report

FOLDERS = ["glioma_tumor", "meningioma_tumor", "no_tumor", "pituitary_tumor"]


def _make_split(root, split, per_class):
    for folder in FOLDERS:
        target = root / split / folder
        target.mkdir(parents=True)
        for i in range(per_class):
            Image.new("L", (40, 40), i).save(target / f"img_{i}.png")


def test_discover_maps_folders_to_canonical_labels(tmp_path):
    _make_split(tmp_path, "Training", 3)
    (tmp_path / "Training" / "unexpected_folder").mkdir()
    (tmp_path / "Training" / "unexpected_folder" / "x.png").write_bytes(b"x")
    samples = discover_samples(tmp_path / "Training")
    assert len(samples) == 12
    assert {s.class_name for s in samples} == set(CLASS_NAMES)


def test_missing_split_is_reported(tmp_path):
    with pytest.raises(DatasetError):
        load_dataset_splits(tmp_path)


def test_missing_class_is_reported(tmp_path):
    _make_split(tmp_path, "Training", 2)
    for img in (tmp_path / "Training" / "glioma_tumor").iterdir():
        img.unlink()
    with pytest.raises(DatasetError, match="glioma"):
        discover_samples(tmp_path / "Training")


def test_stratified_split_keeps_every_class_in_validation(tmp_path):
    _make_split(tmp_path, "Training", 20)
    samples = discover_samples(tmp_path / "Training")
    train, val = stratified_split(samples, 0.2, seed=0)
    assert len(train) + len(val) == len(samples)
    assert {s.label for s in val} == set(range(len(CLASS_NAMES)))
    assert not {s.path for s in train} & {s.path for s in val}


def test_limit_per_class_and_weights(tmp_path):
    _make_split(tmp_path, "Training", 10)
    samples = discover_samples(tmp_path / "Training")
    limited = limit_per_class(samples, 4, seed=1)
    assert len(limited) == 4 * len(CLASS_NAMES)
    weights = class_weights(samples)
    assert weights.shape == (len(CLASS_NAMES),)
    assert abs(float(weights.mean()) - 1.0) < 1e-6


def test_metrics_perfect_and_mixed():
    perfect = compute_classification_metrics([0, 1, 2, 3], [0, 1, 2, 3], CLASS_NAMES)
    assert perfect["accuracy"] == 1.0 and perfect["macro_f1"] == 1.0
    mixed = compute_classification_metrics([0, 0, 1, 1], [0, 1, 1, 1], CLASS_NAMES[:2])
    assert mixed["accuracy"] == 0.75
    assert mixed["confusion_matrix"] == [[1, 1], [0, 2]]
    assert mixed["per_class"]["meningioma"]["precision"] == round(2 / 3, 4)
    assert "Accuracy: 75.00%" in format_metrics_report(mixed)
