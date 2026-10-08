import numpy as np
import torch
from PIL import Image

from ml.preprocessing import build_eval_transform, build_train_transform, preprocess_image, to_rgb


def test_grayscale_is_expanded_to_rgb():
    image = Image.new("L", (20, 10), color=128)
    rgb = to_rgb(image)
    assert rgb.mode == "RGB" and rgb.size == (20, 10)


def test_transparent_pixels_are_composited_on_black():
    image = Image.new("RGBA", (4, 4), (255, 255, 255, 0))
    rgb = to_rgb(image)
    assert rgb.getpixel((0, 0)) == (0, 0, 0)


def test_16_bit_greyscale_is_rescaled_to_8_bit():
    data = np.linspace(0, 65535, num=64 * 64, dtype=np.uint16).reshape(64, 64)
    image = Image.fromarray(data)  # mode "I;16"
    rgb = to_rgb(image)
    arr = np.asarray(rgb)
    assert arr.dtype == np.uint8
    assert arr.min() == 0 and arr.max() == 255


def test_eval_transform_output_shape_and_per_image_standardisation():
    rng = np.random.default_rng(0)
    noisy = Image.fromarray(rng.integers(0, 255, (200, 300, 3), dtype=np.uint8))
    tensor = preprocess_image(noisy, img_size=128)
    assert tensor.shape == (1, 3, 128, 128)
    assert abs(float(tensor.mean())) < 1e-4
    assert abs(float(tensor.std()) - 1.0) < 1e-3


def test_uniform_image_maps_to_zero_without_division_by_zero():
    tensor = preprocess_image(Image.new("RGB", (300, 200), (255, 255, 255)), img_size=64)
    assert torch.isfinite(tensor).all() and float(tensor.abs().max()) == 0.0


def test_intensity_shift_is_removed_by_standardisation():
    rng = np.random.default_rng(1)
    base = rng.integers(0, 120, (64, 64, 3), dtype=np.uint8)
    dim = Image.fromarray(base)
    bright = Image.fromarray(np.clip(base.astype(np.int32) + 100, 0, 255).astype(np.uint8))
    a = preprocess_image(dim, 64)
    b = preprocess_image(bright, 64)
    assert torch.allclose(a, b, atol=0.05)


def test_resolution_drop_preserves_size():
    from ml.preprocessing import RandomResolutionDrop

    transform = RandomResolutionDrop(p=1.0, min_scale=0.3)
    out = transform(Image.new("RGB", (128, 96), (10, 20, 30)))
    assert out.size == (128, 96)


def test_train_transform_is_stochastic_but_same_shape():
    image = Image.new("RGB", (80, 80), (120, 60, 30))
    transform = build_train_transform(64)
    a, b = transform(image), transform(image)
    assert a.shape == b.shape == (3, 64, 64)
    assert not torch.equal(a, b)
    assert torch.equal(build_eval_transform(64)(image), build_eval_transform(64)(image))
