import pytest
import torch

from ml.checkpoint import CheckpointError, load_checkpoint, save_checkpoint
from ml.constants import CLASS_NAMES
from ml.inference import Predictor
from ml.model import BrainTumorCNN


def test_forward_pass_returns_one_logit_per_class():
    model = BrainTumorCNN().eval()
    logits = model(torch.randn(2, 3, 128, 128))
    assert logits.shape == (2, len(CLASS_NAMES))


def test_checkpoint_roundtrip_preserves_outputs(tmp_path):
    torch.manual_seed(1)
    model = BrainTumorCNN().eval()
    path = save_checkpoint(tmp_path / "m.pt", model, img_size=64, metadata={"note": "x"})
    loaded = load_checkpoint(path)
    x = torch.randn(1, 3, 64, 64)
    with torch.no_grad():
        assert torch.allclose(model.eval()(x), loaded.model(x), atol=1e-6)
    assert loaded.class_names == CLASS_NAMES
    assert loaded.img_size == 64
    assert loaded.metadata["note"] == "x"


def test_missing_checkpoint_raises_clear_error(tmp_path):
    with pytest.raises(CheckpointError, match="not found"):
        load_checkpoint(tmp_path / "nope.pt")


def test_corrupt_checkpoint_is_rejected(tmp_path):
    bad = tmp_path / "bad.pt"
    bad.write_bytes(b"not a model")
    with pytest.raises(CheckpointError):
        load_checkpoint(bad)


def test_checkpoint_with_wrong_classes_is_rejected(tmp_path):
    model = BrainTumorCNN(num_classes=2)
    path = save_checkpoint(tmp_path / "two.pt", model, img_size=64, class_names=("a", "b"))
    with pytest.raises(CheckpointError, match="do not match"):
        load_checkpoint(path)


def test_predictor_outputs_probabilities_that_sum_to_one(tiny_checkpoint):
    from PIL import Image

    predictor = Predictor.from_checkpoint(tiny_checkpoint)
    result = predictor.predict(Image.new("L", (90, 70), 100))
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-5
    assert result.predicted_class in CLASS_NAMES
    assert result.confidence == max(result.probabilities.values())
    assert result.tumor_detected == (result.predicted_class != "no_tumor")


def test_checkpoint_from_old_preprocessing_is_rejected(tmp_path):
    model = BrainTumorCNN()
    path = save_checkpoint(tmp_path / "old.pt", model, img_size=64)
    payload = torch.load(path, weights_only=True)
    payload["preprocessing_version"] = 1
    torch.save(payload, path)
    with pytest.raises(CheckpointError, match="preprocessing"):
        load_checkpoint(path)
