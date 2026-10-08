"""Model loading, export and inference-service tests."""

from __future__ import annotations

import json

import pytest
import torch
from PIL import Image

from app.core.exceptions import ModelUnavailableError
from app.ml.cnn import BrainTumorCNN, build_model, model_from_config
from app.ml.predictor import Predictor, resolve_device
from app.ml.preprocess import PreprocessSpec
from tests.conftest import write_checkpoint
from training.synthetic import make_phantom
from training.train import export_torchscript


def test_cnn_forward_shape_and_logits():
    model = BrainTumorCNN(in_channels=3, num_classes=2, base_channels=8)
    logits = model(torch.zeros(2, 3, 64, 64))
    assert tuple(logits.shape) == (2, 2)
    assert torch.isfinite(logits).all()


def test_cnn_describe_counts_parameters():
    model = BrainTumorCNN(base_channels=32)
    info = model.describe()
    assert info["name"] == "BrainTumorCNN"
    assert info["parameters"] > 100_000
    assert info["parameters"] == info["trainable_parameters"]


def test_cnn_accepts_single_channel_input():
    model = BrainTumorCNN(in_channels=1, num_classes=2, base_channels=8)
    assert tuple(model(torch.zeros(1, 1, 48, 48)).shape) == (1, 2)


def test_build_model_rejects_unknown_architecture():
    with pytest.raises(ValueError, match="Unknown architecture"):
        build_model("vgg99")


def test_model_from_config_rebuilds_matching_state_dict():
    original = BrainTumorCNN(in_channels=3, num_classes=2, base_channels=8).eval()
    rebuilt = model_from_config(original.describe()).eval()
    rebuilt.load_state_dict(original.state_dict())

    example = torch.randn(1, 3, 64, 64)
    with torch.no_grad():  # eval() disables dropout, so the outputs must match exactly
        assert torch.allclose(original(example), rebuilt(example))


def test_dropout_makes_train_mode_stochastic():
    """Guards the eval()/no_grad() contract used everywhere at inference time."""
    torch.manual_seed(0)
    model = BrainTumorCNN(in_channels=3, num_classes=2, base_channels=8)
    example = torch.randn(1, 3, 64, 64)

    train_outputs = [model(example) for _ in range(2)]
    assert not torch.allclose(train_outputs[0], train_outputs[1])  # dropout active

    model.eval()
    with torch.no_grad():
        assert torch.allclose(model(example), model(example))


def test_resolve_device_falls_back_to_cpu():
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("auto") in {"cpu", "cuda", "mps"}
    # Unknown values degrade gracefully instead of raising.
    assert resolve_device("quantum") in {"cpu", "cuda", "mps"}


def test_predictor_loads_checkpoint_and_predicts(tmp_path):
    write_checkpoint(tmp_path, img_size=64)
    predictor = Predictor(tmp_path).load()

    assert predictor.is_loaded
    assert predictor.class_labels == ["no_tumor", "tumor"]

    result = predictor.predict(make_phantom(120, tumor=True, seed=1).convert("RGB"))
    assert result.label in {"no_tumor", "tumor"}
    assert 0.0 <= result.confidence <= 1.0
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-4
    assert result.timing["total_ms"] >= 0
    payload = result.to_dict()
    assert payload["prediction"]["recommendation"]
    assert "preprocessed_image" not in payload


def test_predictor_can_return_preprocessed_preview(tmp_path):
    write_checkpoint(tmp_path, img_size=64)
    predictor = Predictor(tmp_path).load()
    result = predictor.predict(make_phantom(120, tumor=False, seed=2).convert("RGB"), include_preprocessed=True)
    assert result.preprocessed_image.startswith("data:image/png;base64,")


def test_predictor_without_checkpoint_is_not_loaded(tmp_path):
    predictor = Predictor(tmp_path / "missing").load()
    assert predictor.is_loaded is False
    assert "No model checkpoint found" in predictor.health()["error"]
    with pytest.raises(ModelUnavailableError):
        predictor.predict(Image.new("RGB", (64, 64)))


def test_predictor_rejects_foreign_checkpoint(tmp_path):
    torch.save({"something": "else"}, tmp_path / "model.pt")
    predictor = Predictor(tmp_path).load()
    assert predictor.is_loaded is False
    assert "not a BrainScan checkpoint bundle" in predictor.health()["error"]


def test_predictor_rejects_mismatched_weights(tmp_path):
    write_checkpoint(tmp_path, img_size=64)
    bundle = torch.load(tmp_path / "model.pt", weights_only=False)
    bundle["architecture"]["base_channels"] = 64  # forces a different width
    torch.save(bundle, tmp_path / "model.pt")

    predictor = Predictor(tmp_path).load()
    assert predictor.is_loaded is False
    assert "do not match" in predictor.health()["error"]


def test_predictor_prefers_torchscript_archive(tmp_path):
    write_checkpoint(tmp_path, img_size=64)
    spec = PreprocessSpec(img_size=64, channels=3)
    export_torchscript(BrainTumorCNN(in_channels=3, num_classes=2, base_channels=8), tmp_path / "model_scripted.pt", spec)

    predictor = Predictor(tmp_path).load()
    assert predictor.is_loaded
    assert predictor.health()["model"]["checkpoint"] == "model_scripted.pt"

    result = predictor.predict(make_phantom(120, tumor=True, seed=5).convert("RGB"))
    assert result.label in {"no_tumor", "tumor"}
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-4


def test_predictor_reload_picks_up_new_checkpoint(tmp_path):
    predictor = Predictor(tmp_path).load()
    assert predictor.is_loaded is False

    write_checkpoint(tmp_path, img_size=64)
    predictor.reload()
    assert predictor.is_loaded is True


def test_predictor_sidecar_metadata_wins(tmp_path):
    write_checkpoint(tmp_path, img_size=64)
    sidecar = {"name": "Sidecar CNN", "metrics": {"val_accuracy": 0.88}, "class_labels": ["no_tumor", "tumor"]}
    (tmp_path / "metadata.json").write_text(json.dumps(sidecar), encoding="utf-8")

    predictor = Predictor(tmp_path).load()
    assert predictor.public_metadata()["name"] == "Sidecar CNN"
    assert predictor.public_metadata()["metrics"]["val_accuracy"] == 0.88


def test_uncertainty_flag_uses_threshold(tmp_path):
    write_checkpoint(tmp_path, img_size=64)
    strict = Predictor(tmp_path, uncertainty_threshold=1.01).load()
    result = strict.predict(make_phantom(120, tumor=True, seed=4).convert("RGB"))
    assert result.uncertain is True

    lenient = Predictor(tmp_path, uncertainty_threshold=0.0).load()
    assert lenient.predict(make_phantom(120, tumor=True, seed=4).convert("RGB")).uncertain is False


def test_predictor_is_thread_safe(tmp_path):
    """Flask serves requests concurrently — inference must stay consistent."""
    import concurrent.futures

    write_checkpoint(tmp_path, img_size=64)
    predictor = Predictor(tmp_path).load()
    image = make_phantom(120, tumor=True, seed=6).convert("RGB")

    reference = predictor.predict(image).confidence
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: predictor.predict(image).confidence, range(24)))

    assert all(value == reference for value in results)


def test_predictor_spec_matches_checkpoint(tmp_path):
    """Regression: evaluate.py rebuilt the spec from public_metadata() and silently
    fell back to the 224px default, so it preprocessed differently than training."""
    write_checkpoint(tmp_path, img_size=64, channels=3)
    predictor = Predictor(tmp_path).load()

    assert predictor.spec.img_size == 64
    assert predictor.spec.channels == 3
    assert predictor.spec.brain_extraction is True

    # public_metadata() intentionally exposes a display-friendly "input" block,
    # which must NOT be mistaken for a PreprocessSpec source.
    rebuilt = PreprocessSpec.from_metadata(predictor.public_metadata())
    assert rebuilt.img_size == 224  # the silent-default trap the property avoids
    assert predictor.spec.img_size != rebuilt.img_size


def test_evaluate_uses_the_checkpoint_spec(tmp_path, monkeypatch):
    """`training.evaluate` must preprocess with the model's own spec."""
    import training.evaluate as evaluate_module

    captured = {}
    real_split = evaluate_module.split_index

    def fake_split(index, **kwargs):
        train_paths, train_labels, val_paths, val_labels = real_split(index, **kwargs)
        captured["spec"] = None
        return train_paths, train_labels, val_paths[:2], val_labels[:2]

    monkeypatch.setattr(evaluate_module, "split_index", fake_split)

    from training.synthetic import generate_dataset

    dataset = generate_dataset(tmp_path / "data", per_class=4, size=96, seed=3)
    write_checkpoint(tmp_path / "models", img_size=64)

    original_dataset = evaluate_module.BrainMRIDataset

    class CapturingDataset(original_dataset):
        def __init__(self, paths, labels, spec, **kwargs):
            captured["spec"] = spec
            super().__init__(paths, labels, spec, **kwargs)

    monkeypatch.setattr(evaluate_module, "BrainMRIDataset", CapturingDataset)

    payload = evaluate_module.evaluate(str(dataset), str(tmp_path / "models"), batch_size=2, seed=42)
    assert captured["spec"].img_size == 64
    assert payload["metrics"]["accuracy"] >= 0.0
