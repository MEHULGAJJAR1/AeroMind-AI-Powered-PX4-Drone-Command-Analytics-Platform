"""Synthetic MRI phantom generator.

Purpose: exercise the *whole* pipeline (dataset discovery → augmentation →
training → checkpoint export → serving → API) on a machine without the real
dataset and without internet access. The images are procedurally drawn skull
phantoms, **not** medical data — a model trained on them proves the plumbing
works, nothing more.

    python -m training.synthetic --out data/synthetic --per-class 120 --size 256
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def make_phantom(
    size: int = 256,
    *,
    tumor: bool = False,
    seed: int | None = None,
    background: int = 0,
) -> Image.Image:
    """Draw one axial-slice-like phantom (grayscale ``L`` image)."""
    rng = np.random.default_rng(seed)
    canvas = Image.new("L", (size, size), background)
    draw = ImageDraw.Draw(canvas)

    cx = size / 2 + rng.uniform(-0.02, 0.02) * size
    cy = size / 2 + rng.uniform(-0.02, 0.02) * size
    rx = size * rng.uniform(0.30, 0.38)
    ry = size * rng.uniform(0.34, 0.42)

    draw = ImageDraw.Draw(canvas)

    # Skull rim (bright) with brain tissue (darker) inside it.
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=int(rng.integers(195, 240)))
    shrink = rng.uniform(0.86, 0.94)
    draw.ellipse(
        [cx - rx * shrink, cy - ry * shrink, cx + rx * shrink, cy + ry * shrink],
        fill=int(rng.integers(95, 135)),
    )
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=max(0.6, size * 0.008)))
    draw = ImageDraw.Draw(canvas)

    # Fake sulci / vessels for texture.
    for _ in range(int(rng.integers(8, 18))):
        angle = rng.uniform(0, 2 * math.pi)
        radius = rng.uniform(0.15, 0.8)
        px = cx + math.cos(angle) * rx * radius
        py = cy + math.sin(angle) * ry * radius
        blob = rng.uniform(0.01, 0.05) * size
        shade = int(rng.integers(60, 175))
        draw.ellipse([px - blob, py - blob, px + blob, py + blob], fill=shade)

    if tumor:
        # Mass with a hypointense core, hyperintense rim and surrounding edema.
        angle = rng.uniform(0, 2 * math.pi)
        radius = rng.uniform(0.2, 0.55)
        tx = cx + math.cos(angle) * rx * radius
        ty = cy + math.sin(angle) * ry * radius
        tr = size * rng.uniform(0.05, 0.13)

        edema = Image.new("L", (size, size), 0)
        edema_draw = ImageDraw.Draw(edema)
        edema_draw.ellipse([tx - tr * 2.2, ty - tr * 2.2, tx + tr * 2.2, ty + tr * 2.2], fill=60)
        edema = edema.filter(ImageFilter.GaussianBlur(radius=size * 0.05))
        # Blend using the blurred edema layer as its own mask (soft transition).
        canvas = Image.composite(edema, canvas, edema)
        draw = ImageDraw.Draw(canvas)

        for jitter in range(6):
            offset = rng.uniform(-0.25, 0.25) * tr
            r = tr * (1.0 - jitter * 0.12)
            shade = int(200 + jitter * 8) if jitter % 2 == 0 else int(120 + jitter * 12)
            shade = int(np.clip(shade, 0, 255))
            draw.ellipse(
                [tx + offset - r, ty - offset - r, tx + offset + r, ty - offset + r],
                fill=shade,
            )
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=max(0.4, size * 0.004)))

    # Intensity inhomogeneity + Rician-ish noise, then letterbox padding.
    array = np.asarray(canvas, dtype=np.float32)
    gradient = np.linspace(0.85, 1.15, size, dtype=np.float32)[None, :]
    array = array * gradient
    array = np.clip(array + rng.normal(0, 4.0, size=array.shape), 0, 255)
    canvas = Image.fromarray(array.astype(np.uint8), mode="L")

    # Random black padding + a text-like artefact, as seen in many public sets.
    padded = Image.new("L", (size, size), 0)
    scale = rng.uniform(0.72, 0.95)
    resized = canvas.resize((int(size * scale), int(size * scale)), Image.Resampling.BILINEAR)
    padded.paste(resized, ((size - resized.size[0]) // 2, (size - resized.size[1]) // 2))
    if rng.random() < 0.3:
        artefact = ImageDraw.Draw(padded)
        artefact.rectangle([4, 4, 4 + rng.integers(20, 60), 12], fill=int(rng.integers(120, 200)))
    return padded


def generate_dataset(
    out_dir: str | Path,
    *,
    per_class: int = 120,
    size: int = 256,
    seed: int = 0,
    val_fraction: float = 0.0,
) -> Path:
    """Write ``out_dir/<class>/*.png`` (optionally with a ``val/`` split)."""
    out = Path(out_dir)
    for label, is_tumor in (("no_tumor", False), ("tumor", True)):
        folder = out / label
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(per_class):
            image = make_phantom(size, tumor=is_tumor, seed=seed + index + (0 if not is_tumor else 10_000))
            image.save(folder / f"{label}_{index:05d}.png")

    if val_fraction > 0:
        import random
        import shutil

        rng = random.Random(seed)
        for label in ("no_tumor", "tumor"):
            source = out / label
            target = out / "val" / label
            target.mkdir(parents=True, exist_ok=True)
            files = sorted(source.iterdir())
            for path in rng.sample(files, max(1, int(len(files) * val_fraction))):
                shutil.move(str(path), str(target / path.name))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic MRI phantoms for pipeline testing")
    parser.add_argument("--out", default="data/synthetic", help="Output directory")
    parser.add_argument("--per-class", type=int, default=120)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--val-fraction", type=float, default=0.0)
    args = parser.parse_args()

    path = generate_dataset(
        args.out,
        per_class=args.per_class,
        size=args.size,
        seed=args.seed,
        val_fraction=args.val_fraction,
    )
    total = sum(1 for _ in path.rglob("*.png"))
    print(f"Wrote {total} synthetic phantoms to {path}")


if __name__ == "__main__":
    main()
