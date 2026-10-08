"""Dataset discovery, splitting, augmentation and a mini training run."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
import torch

from app.ml.preprocess import PreprocessSpec
from training.dataset import (
    AugmentationConfig,
    BrainMRIDataset,
    DatasetError,
    augment_image,
    compute_class_weights,
    discover_dataset,
    label_counts,
    normalize_class_name,
    split_index,
)
from training.synthetic import generate_dataset, make_phantom
from training.train import TrainConfig, train


@pytest.fixture(scope="module")
def flat_dataset(tmp_path_factory) -> Path:
    return generate_dataset(tmp_path_factory.mktemp("flat"), per_class=6, size=96, seed=1)


@pytest.fixture(scope="module")
def split_dataset(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("split")
    for split, count in (("Train", 8), ("Test", 4)):
        for label, tumor in (("no", False), ("yes", True)):
            folder = root / split / label
            folder.mkdir(parents=True)
            for index in range(count):
                make_phantom(96, tumor=tumor, seed=hash((split, label, index)) % 10_000).save(
                    folder / f"{label}_{index}.png"
                )
    return root


# --------------------------------------------------------------------------- #
# Class-name normalisation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("no", "no_tumor"),
        ("No", "no_tumor"),
        ("notumor", "no_tumor"),
        ("no_tumor", "no_tumor"),
        ("Not Tumor", "no_tumor"),
        ("healthy", "no_tumor"),
        ("negative", "no_tumor"),
        ("0", "no_tumor"),
        ("yes", "tumor"),
        ("Yes", "tumor"),
        ("tumor", "tumor"),
        ("tumour", "tumor"),
        ("glioma", "tumor"),
        ("meningioma_tumor", "tumor"),
        ("pituitary", "tumor"),
        ("1", "tumor"),
        ("random", None),
        ("", None),
    ],
)
def test_normalize_class_name(raw, expected):
    assert normalize_class_name(raw) == expected


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def test_discover_flat_layout(flat_dataset):
    index = discover_dataset(flat_dataset)
    assert index.summary() == {"train": {"no_tumor": 6, "tumor": 6}}
    assert len(index) == 12
    assert all(path.suffix == ".png" for path in index.paths["train"])


def test_discover_train_test_layout(split_dataset):
    index = discover_dataset(split_dataset)
    summary = index.summary()
    assert summary["train"] == {"no_tumor": 8, "tumor": 8}
    assert summary["test"] == {"no_tumor": 4, "tumor": 4}


def test_discover_ignores_unknown_folders(flat_dataset):
    (flat_dataset / "reports").mkdir()
    (flat_dataset / "reports" / "notes.txt").write_text("not an image")
    index = discover_dataset(flat_dataset)
    assert len(index) == 12


def test_discover_raises_for_missing_directory(tmp_path):
    with pytest.raises(DatasetError, match="not found"):
        discover_dataset(tmp_path / "nope")


def test_discover_raises_when_no_images(tmp_path):
    empty = tmp_path / "empty"
    (empty / "no").mkdir(parents=True)
    (empty / "yes").mkdir(parents=True)
    with pytest.raises(DatasetError, match="No labelled images"):
        discover_dataset(empty)


# --------------------------------------------------------------------------- #
# Splitting & weights
# --------------------------------------------------------------------------- #
def test_split_uses_explicit_test_folder(split_dataset):
    index = discover_dataset(split_dataset)
    train_paths, train_labels, val_paths, val_labels = split_index(index, val_fraction=0.15)
    assert len(train_paths) == 16
    assert len(val_paths) == 8
    assert label_counts(train_labels) == {"no_tumor": 8, "tumor": 8}
    assert label_counts(val_labels) == {"no_tumor": 4, "tumor": 4}


def test_random_split_is_stratified_and_deterministic(flat_dataset):
    index = discover_dataset(flat_dataset)
    first = split_index(index, val_fraction=0.25, seed=7)
    second = split_index(index, val_fraction=0.25, seed=7)
    assert [str(p) for p in first[0]] == [str(p) for p in second[0]]

    train_paths, train_labels, val_paths, val_labels = first
    assert len(train_paths) + len(val_paths) == 12
    assert label_counts(val_labels)["tumor"] >= 1
    assert label_counts(val_labels)["no_tumor"] >= 1
    assert len(train_paths) == len(train_labels)


def test_split_without_validation(flat_dataset):
    index = discover_dataset(flat_dataset)
    train_paths, train_labels, val_paths, val_labels = split_index(index, val_fraction=0.0)
    assert len(train_paths) == 12
    assert val_paths == []
    assert val_labels == []


def test_compute_class_weights_balances_skewed_labels():
    weights = compute_class_weights([0] * 90 + [1] * 10)
    assert weights[1] > weights[0]
    assert abs(sum(weights) / 2 - 1.0) < 0.01


def test_compute_class_weights_handles_missing_class():
    weights = compute_class_weights([0, 0, 0])
    assert len(weights) == 2
    assert all(value > 0 and value == value for value in weights)  # positive and not NaN


# --------------------------------------------------------------------------- #
# Dataset & augmentation
# --------------------------------------------------------------------------- #
def test_dataset_returns_tensors_and_labels(flat_dataset):
    index = discover_dataset(flat_dataset)
    spec = PreprocessSpec(img_size=48, channels=3)
    dataset = BrainMRIDataset(index.paths["train"], index.labels["train"], spec)

    assert len(dataset) == 12
    tensor, label = dataset[0]
    assert tuple(tensor.shape) == (3, 48, 48)
    assert label in {0, 1}
    assert torch.isfinite(tensor).all()
    assert dataset.skipped == []


def test_dataset_grayscale(flat_dataset):
    index = discover_dataset(flat_dataset)
    spec = PreprocessSpec(img_size=32, channels=1)
    tensor, _ = BrainMRIDataset(index.paths["train"], index.labels["train"], spec)[0]
    assert tuple(tensor.shape) == (1, 32, 32)


def test_dataset_tolerates_unreadable_files(tmp_path, flat_dataset):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image at all")
    spec = PreprocessSpec(img_size=32, channels=3)
    dataset = BrainMRIDataset([broken], [0], spec)
    tensor, label = dataset[0]
    assert tuple(tensor.shape) == (3, 32, 32)
    assert label == 0
    assert len(dataset.skipped) == 1


def test_dataset_rejects_mismatched_inputs(flat_dataset):
    index = discover_dataset(flat_dataset)
    spec = PreprocessSpec(img_size=32, channels=3)
    with pytest.raises(ValueError, match="same length"):
        BrainMRIDataset(index.paths["train"], [0, 1], spec)


def test_augmentation_preserves_size_and_mode():
    image = make_phantom(96, tumor=True, seed=12).convert("RGB")
    rng = random.Random(3)
    config = AugmentationConfig()
    for _ in range(10):
        augmented = augment_image(image, config, rng)
        assert augmented.size == image.size
        assert augmented.mode == "RGB"


def test_augmentation_changes_pixels():
    image = make_phantom(96, tumor=False, seed=13).convert("RGB")
    rng = random.Random(5)
    augmented = augment_image(image, AugmentationConfig(rotation=30.0), rng)
    assert list(augmented.getdata()) != list(image.getdata())


# --------------------------------------------------------------------------- #
# Mini training run (proves the training loop end to end)
# --------------------------------------------------------------------------- #
def test_mini_training_run_produces_all_artifacts(tmp_path, flat_dataset):
    output = tmp_path / "models"
    config = TrainConfig(
        data_dir=str(flat_dataset),
        output_dir=str(output),
        epochs=2,
        batch_size=4,
        img_size=32,
        base_channels=8,
        val_fraction=0.25,
        patience=0,
        export_torchscript=True,
        notes="pytest mini run",
    )
    report = train(config)

    assert report["final_metrics"]["accuracy"] >= 0.0
    assert len(report["history"]) == 2
    assert (output / "model.pt").is_file()
    assert (output / "metadata.json").is_file()
    assert (output / "model_scripted.pt").is_file()
    assert (output / "training_report.json").is_file()
    assert (output / "classification_report.txt").is_file()
    assert (output / "training_curves.png").is_file()
    assert (output / "confusion_matrix.png").is_file()

    # The exported checkpoint must be loadable by the serving code.
    from app.ml.predictor import Predictor

    predictor = Predictor(output).load()
    assert predictor.is_loaded
    assert predictor.class_labels == ["no_tumor", "tumor"]
    result = predictor.predict(make_phantom(96, tumor=True, seed=21).convert("RGB"))
    assert result.label in {"no_tumor", "tumor"}
    assert predictor.public_metadata()["notes"] == "pytest mini run"


def test_torchscript_export_matches_best_checkpoint(tmp_path, flat_dataset):
    """Guard: the TorchScript archive must carry the same (best) weights as model.pt.

    Regression test — the export used to run on the final-epoch model, so the
    server (which prefers the scripted archive) served different weights than
    the ones metadata.json advertised.
    """
    import torch

    from app.ml.cnn import model_from_config
    from app.ml.preprocess import PreprocessSpec

    output = tmp_path / "models"
    train(
        TrainConfig(
            data_dir=str(flat_dataset),
            output_dir=str(output),
            epochs=2,
            batch_size=4,
            img_size=32,
            base_channels=8,
            val_fraction=0.25,
            patience=0,
            export_torchscript=True,
        )
    )

    bundle = torch.load(output / "model.pt", map_location="cpu", weights_only=False)
    checkpoint_model = model_from_config(bundle["architecture"]).eval()
    checkpoint_model.load_state_dict(bundle["state_dict"])

    spec = PreprocessSpec.from_metadata(bundle["metadata"])
    scripted = torch.jit.load(str(output / "model_scripted.pt"), map_location="cpu").eval()

    example = torch.zeros(1, spec.channels, spec.img_size, spec.img_size)
    with torch.no_grad():
        assert torch.allclose(checkpoint_model(example), scripted(example), atol=1e-5)

    # The metadata metrics must describe the same weights as the checkpoint.
    assert bundle["metadata"]["metrics"]["epoch"] == bundle["metadata"]["epochs_completed"]
