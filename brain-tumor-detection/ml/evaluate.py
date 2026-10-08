"""Evaluate a saved checkpoint on the held-out Testing split (or any labelled folder).

    python -m ml.evaluate --data-dir data/raw
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from .checkpoint import CheckpointError, load_checkpoint
from .constants import CLASS_NAMES, DEFAULT_MODEL_PATH
from .dataset import DatasetError, MRIDataset, discover_samples, TEST_DIR_NAME
from .engine import evaluate
from .metrics import compute_classification_metrics, format_metrics_report
from .preprocessing import build_eval_transform


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the brain tumor classifier.")
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="Folder containing the class sub-folders, or a parent with Testing/.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--json", action="store_true", help="Print metrics as JSON.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        checkpoint = load_checkpoint(args.model, device=args.device)
    except CheckpointError as exc:
        logging.getLogger("ml.evaluate").error("%s", exc)
        return 2

    split_dir = args.data_dir / TEST_DIR_NAME if (args.data_dir / TEST_DIR_NAME).is_dir() else args.data_dir
    try:
        samples = discover_samples(split_dir)
    except DatasetError as exc:
        logging.getLogger("ml.evaluate").error("%s", exc)
        return 2

    loader = DataLoader(
        MRIDataset(samples, build_eval_transform(checkpoint.img_size)),
        batch_size=args.batch_size, shuffle=False,
    )
    result = evaluate(checkpoint.model, loader, None, torch.device(args.device))
    metrics = compute_classification_metrics(result.labels, result.predictions, CLASS_NAMES)
    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(format_metrics_report(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
