"""Preprocessing pipeline tests — no model required."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from app.ml.preprocess import (
    ImageLoadError,
    PreprocessSpec,
    crop_to_brain,
    extract_brain_bbox,
    normalize_mode,
    open_image,
    otsu_threshold,
    preprocess_image,
    preprocess_to_pil,
    tensor_to_preview,
)
from training.synthetic import make_phantom


def test_spec_defaults_and_channel_expansion():
    spec = PreprocessSpec(channels=3, mean=0.5, std=0.25)
    assert spec.mean == (0.5, 0.5, 0.5)
    assert spec.std == (0.25, 0.25, 0.25)
    assert spec.to_metadata()["img_size"] == 224


def test_spec_rejects_bad_values():
    with pytest.raises(ValueError):
        PreprocessSpec(channels=4)
    with pytest.raises(ValueError):
        PreprocessSpec(img_size=8)
    with pytest.raises(ValueError):
        PreprocessSpec(channels=1, mean=(0.5, 0.5))  # wrong length


def test_spec_roundtrips_through_metadata():
    spec = PreprocessSpec(img_size=128, channels=1, mean=(0.1,), std=(0.9,), brain_extraction=False)
    restored = PreprocessSpec.from_metadata(spec.to_metadata())
    assert restored == spec


def test_otsu_separates_bimodal_intensity():
    values = np.concatenate([np.zeros(500), np.full(500, 200.0)])
    threshold = otsu_threshold(values)
    assert 1 < threshold < 200


def test_otsu_handles_empty_and_flat_input():
    assert otsu_threshold(np.array([])) == 0.0
    assert 0 <= otsu_threshold(np.full((10, 10), 128.0)) <= 255


def test_extract_brain_bbox_crops_to_head():
    image = make_phantom(200, tumor=False, seed=5)
    gray = np.asarray(image.convert("L"), dtype=np.float64)
    bbox = extract_brain_bbox(gray)
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    assert x1 > x0 and y1 > y0
    # The crop must be substantially smaller than the padded frame.
    assert (x1 - x0) * (y1 - y0) < gray.size
    cropped, returned = crop_to_brain(image)
    assert returned == bbox
    assert cropped.size == (x1 - x0, y1 - y0)


def test_extract_brain_bbox_returns_none_for_blank_image():
    blank = np.zeros((64, 64), dtype=np.float64)
    assert extract_brain_bbox(blank) is None


def test_normalize_mode_handles_alpha_by_compositing_on_black():
    rgba = Image.new("RGBA", (16, 16), (255, 255, 255, 0))
    rgb = normalize_mode(rgba, channels=3)
    assert rgb.mode == "RGB"
    assert np.asarray(rgb).max() == 0  # fully transparent → black background

    gray = normalize_mode(rgba, channels=1)
    assert gray.mode == "L"


def test_preprocess_image_output_shape_and_range():
    spec = PreprocessSpec(img_size=64, channels=3)
    image = make_phantom(180, tumor=True, seed=11).convert("RGB")
    tensor, meta = preprocess_image(image, spec)

    assert tuple(tensor.shape) == (1, 3, 64, 64)
    assert tensor.dtype.is_floating_point
    # mean=std=0.5 → normalised values stay inside [-1, 1]
    assert float(tensor.min()) >= -1.001
    assert float(tensor.max()) <= 1.001
    assert meta["original_size"] == {"width": 180, "height": 180}
    assert meta["input_size"] == {"width": 64, "height": 64}
    assert meta["channels"] == 3


def test_preprocess_image_grayscale_single_channel():
    spec = PreprocessSpec(img_size=48, channels=1)
    tensor, meta = preprocess_image(make_phantom(120, tumor=False, seed=2), spec)
    assert tuple(tensor.shape) == (1, 1, 48, 48)
    assert meta["channels"] == 1


def test_preprocess_to_pil_is_displayable_and_square():
    spec = PreprocessSpec(img_size=64, channels=3)
    preview, meta = preprocess_to_pil(make_phantom(160, tumor=True, seed=4).convert("RGB"), spec)
    assert preview.size == (64, 64)
    assert preview.mode == "RGB"
    assert "brain_bbox" in meta


def test_tensor_to_preview_inverts_normalisation():
    spec = PreprocessSpec(img_size=64, channels=3)
    original = make_phantom(160, tumor=True, seed=8).convert("RGB")
    tensor, _ = preprocess_image(original, spec)
    preview = tensor_to_preview(tensor, spec)

    assert preview.size == (64, 64)
    assert preview.mode == "RGB"
    # Round-tripping through tensor_to_preview must recover the preprocessed pixels.
    reference, _ = preprocess_to_pil(original, spec)
    delta = np.abs(np.asarray(preview, dtype=int) - np.asarray(reference, dtype=int))
    assert delta.max() <= 1


def test_open_image_rejects_empty_and_corrupt_payloads():
    with pytest.raises(ImageLoadError):
        open_image(b"")
    with pytest.raises(ImageLoadError):
        open_image(b"this is definitely not an image")


def test_open_image_rejects_truncated_jpeg():
    buffer = io.BytesIO()
    make_phantom(120, tumor=False, seed=1).convert("RGB").save(buffer, format="JPEG")
    truncated = buffer.getvalue()[: len(buffer.getvalue()) // 3]
    with pytest.raises(ImageLoadError):
        open_image(truncated)


def test_open_image_enforces_size_limits():
    buffer = io.BytesIO()
    make_phantom(64, tumor=False, seed=6).convert("RGB").save(buffer, format="PNG")
    raw = buffer.getvalue()

    with pytest.raises(ImageLoadError, match="too small"):
        open_image(raw, min_dimension=128)
    with pytest.raises(ImageLoadError, match="too large"):
        open_image(raw, max_pixels=1000)


def test_open_image_applies_exif_orientation():
    image = Image.new("RGB", (40, 80), "white")
    exif = Image.Exif()
    exif[274] = 6  # orientation: rotate 90° CW
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())

    raw = Image.open(io.BytesIO(buffer.getvalue()))
    assert raw.size == (40, 80)  # stored dimensions

    loaded = open_image(buffer.getvalue())
    assert loaded.size == (80, 40)  # orientation applied
