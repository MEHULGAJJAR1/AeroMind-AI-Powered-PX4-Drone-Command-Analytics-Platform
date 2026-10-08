"""Train the brain tumor CNN from a folder of labelled MRI images.

Example::

    python -m ml.train --data-dir data/raw --epochs 20

The best validation checkpoint is evaluated once on the held-out ``Testing``
split, then written to ``models/brain_tumor_cnn.pt`` together with its metrics
and a ``*_metrics.json`` report.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from .checkpoint import save_checkpoint
from .constants import CLASS_NAMES, DEFAULT_IMG_SIZE, DEFAULT_MODEL_PATH
from .dataset import (
    DatasetError,
    MRIDataset,
    class_weights,
    limit_per_class,
    load_dataset_splits,
    stratified_split,
)
from .engine import evaluate, train_one_epoch
from .metrics import compute_classification_metrics, format_metrics_report
from .model import BrainTumorCNN
from .preprocessing import build_eval_transform, build_train_transform

logger = logging.getLogger("ml.train")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the brain tumor MRI classifier.")
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="Folder containing Training/ and Testing/ subfolders.")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH,
                        help="Where to save the checkpoint (default: models/brain_tumor_cnn.pt).")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--img-size", type=int, default=DEFAULT_IMG_SIZE)
    parser.add_argument("--lr", type=float, default=1e-3, help="Peak learning rate (OneCycle schedule).")
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--patience", type=int, default=6, help="Early-stopping patience in epochs.")
    parser.add_argument("--limit-per-class", type=int, default=None,
                        help="Cap images per class (useful for a quick smoke test).")
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--threads", type=int, default=None, help="torch.set_num_threads value.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto", help="'auto', 'cpu' or 'cuda'.")
    return parser.parse_args(argv)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def resolve_device(choice: str) -> torch.device:
    if choice == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(choice)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.threads:
        torch.set_num_threads(args.threads)
    set_seed(args.seed)
    device = resolve_device(args.device)

    try:
        train_pool, test_samples = load_dataset_splits(args.data_dir)
    except DatasetError as exc:
        logger.error("%s", exc)
        return 2

    train_pool = limit_per_class(train_pool, args.limit_per_class, args.seed)
    test_samples = limit_per_class(test_samples, args.limit_per_class, args.seed)
    train_samples, val_samples = stratified_split(train_pool, args.val_fraction, args.seed)
    logger.info("Device=%s  image_size=%d  classes=%s", device, args.img_size, CLASS_NAMES)
    logger.info("Samples: train=%d  val=%d  test=%d", len(train_samples), len(val_samples), len(test_samples))

    train_loader = DataLoader(
        MRIDataset(train_samples, build_train_transform(args.img_size)),
        batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, drop_last=False,
    )
    val_loader = DataLoader(
        MRIDataset(val_samples, build_eval_transform(args.img_size)),
        batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers,
    )
    test_loader = DataLoader(
        MRIDataset(test_samples, build_eval_transform(args.img_size)),
        batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers,
    )

    model = BrainTumorCNN().to(device)
    criterion = nn.CrossEntropyLoss(
        weight=class_weights(train_samples).to(device), label_smoothing=args.label_smoothing
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=args.lr, epochs=args.epochs, steps_per_epoch=len(train_loader)
    )

    best_acc, best_loss, best_state, best_epoch = -1.0, float("inf"), None, 0
    stale, history = 0, []
    started = time.time()
    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()
        train_res = train_one_epoch(model, train_loader, criterion, optimizer, device, scheduler)
        val_res = evaluate(model, val_loader, criterion, device)
        history.append({
            "epoch": epoch,
            "train_loss": round(train_res.loss, 4), "train_acc": round(train_res.accuracy, 4),
            "val_loss": round(val_res.loss, 4), "val_acc": round(val_res.accuracy, 4),
        })
        logger.info(
            "epoch %02d/%d  train loss %.4f acc %.4f | val loss %.4f acc %.4f | %.0fs",
            epoch, args.epochs, train_res.loss, train_res.accuracy,
            val_res.loss, val_res.accuracy, time.time() - epoch_start,
        )
        improved = val_res.accuracy > best_acc or (
            val_res.accuracy == best_acc and val_res.loss < best_loss
        )
        if improved:
            best_acc, best_loss, best_epoch = val_res.accuracy, val_res.loss, epoch
            best_state = copy.deepcopy({k: v.detach().cpu() for k, v in model.state_dict().items()})
            stale = 0
        else:
            stale += 1
            if stale >= args.patience:
                logger.info("Early stopping: no validation improvement for %d epochs.", args.patience)
                break

    if best_state is None:  # pragma: no cover - only if every epoch produced NaN
        logger.error("Training did not produce a usable model.")
        return 1
    model.load_state_dict(best_state)
    logger.info("Best validation accuracy %.4f at epoch %d. Evaluating on the test split...",
                best_acc, best_epoch)

    test_res = evaluate(model, test_loader, None, device)
    metrics = compute_classification_metrics(test_res.labels, test_res.predictions, CLASS_NAMES)
    print(format_metrics_report(metrics))

    metadata = {
        "trained_on": str(args.data_dir),
        "epochs_run": len(history),
        "best_epoch": best_epoch,
        "best_val_accuracy": round(best_acc, 4),
        "test_accuracy": metrics["accuracy"],
        "test_macro_f1": metrics["macro_f1"],
        "train_seconds": round(time.time() - started, 1),
        "hyperparameters": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "history": history,
        "test_metrics": metrics,
    }
    output = save_checkpoint(args.output, model, img_size=args.img_size, metadata=metadata)
    metrics_path = output.with_name(f"{output.stem}_metrics.json")
    metrics_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    logger.info("Saved checkpoint to %s and metrics to %s", output, metrics_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
