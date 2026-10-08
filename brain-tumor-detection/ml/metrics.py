"""Classification metrics computed with NumPy only (no scikit-learn dependency)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def compute_classification_metrics(
    y_true: Sequence[int], y_pred: Sequence[int], class_names: Sequence[str]
) -> dict[str, Any]:
    """Accuracy, macro-F1, per-class precision/recall/F1 and the confusion matrix."""
    n = len(class_names)
    y_true_arr = np.asarray(y_true, dtype=np.int64)
    y_pred_arr = np.asarray(y_pred, dtype=np.int64)
    confusion = np.zeros((n, n), dtype=np.int64)
    np.add.at(confusion, (y_true_arr, y_pred_arr), 1)

    per_class: dict[str, dict[str, float]] = {}
    f1_values: list[float] = []
    for idx, name in enumerate(class_names):
        tp = float(confusion[idx, idx])
        fp = float(confusion[:, idx].sum() - tp)
        fn = float(confusion[idx, :].sum() - tp)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1_values.append(f1)
        per_class[name] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": int(confusion[idx, :].sum()),
        }

    total = int(confusion.sum())
    accuracy = float(np.trace(confusion)) / total if total else 0.0
    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(float(np.mean(f1_values)), 4),
        "num_samples": total,
        "per_class": per_class,
        "confusion_matrix": confusion.tolist(),
        "class_names": list(class_names),
    }


def format_metrics_report(metrics: dict[str, Any]) -> str:
    """Human-readable table for the console."""
    names = metrics["class_names"]
    lines = [
        f"Accuracy: {metrics['accuracy'] * 100:.2f}%   Macro-F1: {metrics['macro_f1']:.4f}   "
        f"Samples: {metrics['num_samples']}",
        "",
        f"{'class':<14}{'precision':>10}{'recall':>10}{'f1':>10}{'support':>10}",
    ]
    for name in names:
        row = metrics["per_class"][name]
        lines.append(
            f"{name:<14}{row['precision']:>10.4f}{row['recall']:>10.4f}{row['f1']:>10.4f}{row['support']:>10d}"
        )
    lines += ["", "Confusion matrix (rows = true, columns = predicted):"]
    header = " " * 14 + "".join(f"{n[:10]:>12}" for n in names)
    lines.append(header)
    for name, row in zip(names, metrics["confusion_matrix"]):
        lines.append(f"{name:<14}" + "".join(f"{v:>12d}" for v in row))
    return "\n".join(lines)
