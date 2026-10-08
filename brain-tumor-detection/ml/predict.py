"""Classify a single MRI image from the command line.

    python -m ml.predict path/to/scan.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from .checkpoint import CheckpointError
from .constants import DEFAULT_MODEL_PATH
from .inference import Predictor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify one brain MRI image.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)

    try:
        predictor = Predictor.from_checkpoint(args.model, device=args.device)
        with Image.open(args.image) as image:
            result = predictor.predict(image)
    except (CheckpointError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({
        "predicted_class": result.predicted_class,
        "tumor_detected": result.tumor_detected,
        "confidence": round(result.confidence, 4),
        "probabilities": {k: round(v, 4) for k, v in result.probabilities.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
