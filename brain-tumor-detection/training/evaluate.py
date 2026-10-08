"""Evaluate a trained checkpoint on a held-out split.

    python -m training.evaluate --data-dir data/brain-tumor --model-dir data/models

Writes ``evaluation_report.json`` and ``evaluation_confusion_matrix.png`` into
``--model-dir`` and prints the classification report.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix
from torch.utils.data import DataLoader

from app.ml.predictor import Predictor
from training.dataset import CLASS_LABELS, BrainMRIDataset, discover_dataset, split_index
from training.train import compute_metrics, plot_confusion_matrix, resolve_device, set_seed


def evaluate(data_dir: str, model_dir: str, *, batch_size: int = 32, seed: int = 42, num_workers: int = 0) -> dict:
    predictor = Predictor(model_dir)
    predictor.load()
    if not predictor.is_loaded:
        raise SystemExit(
            f"No checkpoint found in {model_dir}. Train one first: "
            "python -m training.train --data-dir <dataset>"
        )

    device = resolve_device(predictor.device_name)
    # Must be the spec the checkpoint was trained with — rebuilding it from
    # public_metadata() silently falls back to the 224px default.
    spec = predictor.spec

    index = discover_dataset(data_dir)
    _, _, val_paths, val_labels = split_index(index, val_fraction=0.15, seed=seed)
    if not val_paths:
        raise SystemExit("The dataset has no held-out split to evaluate (add a Test/ folder or more images).")

    set_seed(seed)
    dataset = BrainMRIDataset(val_paths, val_labels, spec, augment=False, seed=seed)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    model = predictor._model  # noqa: SLF001 - intentional reuse of the loaded module
    model.eval()

    all_true: list[np.ndarray] = []
    all_pred: list[np.ndarray] = []
    all_probs: list[np.ndarray] = []
    running_loss = 0.0
    seen = 0
    criterion = torch.nn.CrossEntropyLoss()

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            logits = model(images)
            running_loss += float(criterion(logits, labels)) * labels.size(0)
            seen += labels.size(0)
            probs = torch.softmax(logits.float(), dim=1)
            all_probs.append(probs.cpu().numpy())
            all_true.append(labels.cpu().numpy())
            all_pred.append(logits.argmax(dim=1).cpu().numpy())

    y_true = np.concatenate(all_true)
    y_pred = np.concatenate(all_pred)
    probabilities = np.concatenate(all_probs)

    metrics = compute_metrics(y_true, y_pred, probabilities, running_loss / max(seen, 1))
    report_text = classification_report(
        y_true, y_pred, target_names=[name.replace("_", " ") for name in CLASS_LABELS], zero_division=0
    )
    matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(CLASS_LABELS))))

    out_dir = Path(model_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": predictor.public_metadata(),
        "dataset": {"root": str(index.root), "samples": int(len(val_paths)), "layout": index.summary()},
        "metrics": metrics,
        "confusion_matrix": matrix.tolist(),
        "class_labels": list(CLASS_LABELS),
        "classification_report": report_text,
    }
    (out_dir / "evaluation_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    plot_confusion_matrix(y_true, y_pred, out_dir / "evaluation_confusion_matrix.png")

    print(f"Evaluated {len(val_paths)} images with {payload['model']['name']} on {device}")
    print(f"accuracy={metrics['accuracy']:.4f} precision={metrics['precision']:.4f} "
          f"recall={metrics['recall']:.4f} f1={metrics['f1']:.4f} auc={metrics['roc_auc']}")
    print(report_text)
    print(f"Report → {out_dir / 'evaluation_report.json'}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a BrainScan AI checkpoint")
    parser.add_argument("--data-dir", default="data/brain-tumor")
    parser.add_argument("--model-dir", default="data/models")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()
    evaluate(
        args.data_dir,
        args.model_dir,
        batch_size=args.batch_size,
        seed=args.seed,
        num_workers=args.num_workers,
    )


if __name__ == "__main__":
    main()
