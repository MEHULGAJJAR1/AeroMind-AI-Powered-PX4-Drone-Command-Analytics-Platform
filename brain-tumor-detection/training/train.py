"""Train the brain tumour classifier.

Examples
--------
Train on a real dataset (Kaggle "Brain Tumor MRI" layout ``Train/no``, ``Train/yes``):

    python -m training.train --data-dir data/brain-tumor --epochs 25 --batch-size 32

Quick end-to-end pipeline check on synthetic phantoms (no dataset needed):

    python -m training.synthetic --out data/synthetic --per-class 150
    python -m training.train --data-dir data/synthetic --epochs 3 --img-size 128 \\
        --output-dir data/models --tag demo

Outputs written to ``--output-dir`` (default ``data/models``):

* ``model.pt``              — checkpoint bundle consumed by the Flask app
* ``metadata.json``         — preprocessing spec, metrics, provenance
* ``model_scripted.pt``     — TorchScript archive (``--export-torchscript``)
* ``training_report.json``  — per-epoch history + final metrics
* ``training_curves.png``   — loss / accuracy / LR curves
* ``confusion_matrix.png``  — validation confusion matrix
* ``classification_report.txt``
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from torch.utils.data import DataLoader

from app.ml.cnn import build_model
from app.ml.predictor import CHECKPOINT_NAME, FORMAT_VERSION, METADATA_NAME, SCRIPTED_NAME
from app.ml.preprocess import PreprocessSpec
from app.version import __version__
from training.dataset import (
    CLASS_LABELS,
    AugmentationConfig,
    BrainMRIDataset,
    DatasetError,
    compute_class_weights,
    discover_dataset,
    label_counts,
    split_index,
)


@dataclass
class TrainConfig:
    data_dir: str = "data/brain-tumor"
    output_dir: str = "data/models"
    tag: str = ""
    architecture: str = "cnn"
    pretrained: bool = False
    epochs: int = 25
    batch_size: int = 32
    img_size: int = 224
    channels: int = 3
    base_channels: int = 32
    dropout: float = 0.15
    classifier_dropout: float = 0.4
    lr: float = 1e-3
    weight_decay: float = 1e-4
    val_fraction: float = 0.15
    seed: int = 42
    device: str = "auto"
    patience: int = 6
    num_workers: int = 0
    brain_extraction: bool = True
    augment: bool = True
    use_class_weights: bool = True
    scheduler: str = "cosine"  # cosine | plateau | none
    amp: bool = True
    monitor: str = "val_accuracy"  # val_accuracy | val_f1 | val_loss
    export_torchscript: bool = False
    limit_batches: int = 0  # >0 = smoke-test mode
    notes: str = ""
    history: list[dict[str, float]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def resolve_device(requested: str) -> torch.device:
    requested = (requested or "auto").lower()
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    if requested == "mps" and getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def human_duration(seconds: float) -> str:
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


# --------------------------------------------------------------------------- #
# Train / evaluate
# --------------------------------------------------------------------------- #
def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None = None,
    *,
    scaler: Any | None = None,
    use_amp: bool = False,
    limit_batches: int = 0,
    log_prefix: str = "",
    epoch: int = 0,
    total_epochs: int = 0,
    print_every: int = 25,
) -> tuple[float, np.ndarray, np.ndarray]:
    """One pass over ``loader``. Returns ``(average_loss, y_true, y_pred)``."""
    training = optimizer is not None
    model.train(training)

    running_loss = 0.0
    seen = 0
    all_true: list[np.ndarray] = []
    all_pred: list[np.ndarray] = []
    started = time.perf_counter()

    iterator = loader
    if limit_batches > 0:
        iterator = [batch for _, batch in zip(range(limit_batches), loader)]

    for step, (images, labels) in enumerate(iterator, start=1):
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        if training:
            optimizer.zero_grad(set_to_none=True)

        use_amp_here = bool(use_amp and training and scaler is not None and device.type == "cuda")
        if use_amp_here:
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                logits = model(images)
                loss = criterion(logits, labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            logits = model(images)
            loss = criterion(logits, labels)
            if training:
                loss.backward()
                optimizer.step()

        batch_size = labels.size(0)
        running_loss += float(loss.detach()) * batch_size
        seen += batch_size
        all_true.append(labels.detach().cpu().numpy())
        all_pred.append(logits.detach().argmax(dim=1).cpu().numpy())

        if training and print_every and step % print_every == 0:
            print(
                f"  {log_prefix}epoch {epoch}/{total_epochs} "
                f"step {step}/{len(loader)} loss={running_loss / max(seen, 1):.4f} "
                f"({time.perf_counter() - started:.1f}s)",
                flush=True,
            )

    y_true = np.concatenate(all_true) if all_true else np.array([], dtype=int)
    y_pred = np.concatenate(all_pred) if all_pred else np.array([], dtype=int)
    average_loss = running_loss / max(seen, 1)
    return average_loss, y_true, y_pred


def collect_probabilities(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    *,
    limit_batches: int = 0,
) -> np.ndarray:
    """Softmax probabilities for every batch (used for ROC-AUC)."""
    model.eval()
    chunks: list[np.ndarray] = []
    iterator = loader
    if limit_batches > 0:
        iterator = [batch for _, batch in zip(range(limit_batches), loader)]
    with torch.no_grad():
        for images, _ in iterator:
            logits = model(images.to(device, non_blocking=True))
            chunks.append(torch.softmax(logits.float(), dim=1).cpu().numpy())
    return np.concatenate(chunks) if chunks else np.zeros((0, len(CLASS_LABELS)), dtype=np.float64)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, probabilities: np.ndarray, average_loss: float) -> dict:
    if y_true.size == 0:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0, "roc_auc": 0.0, "loss": average_loss}

    metrics = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "loss": round(float(average_loss), 4),
    }
    try:
        if len(np.unique(y_true)) > 1 and probabilities.size:
            metrics["roc_auc"] = round(float(roc_auc_score(y_true, probabilities[:, 1])), 4)
        else:
            metrics["roc_auc"] = None
    except ValueError:  # pragma: no cover - single-class batch
        metrics["roc_auc"] = None
    return metrics


# --------------------------------------------------------------------------- #
# Artefacts
# --------------------------------------------------------------------------- #
def normalize_metrics(metrics: dict) -> dict:
    """Store validation metrics under consistent ``val_*`` keys.

    Both the checkpoint bundle and ``metadata.json`` must expose the same names,
    otherwise ``/api/model`` reports metrics for one artifact and ``—`` for the
    other (the server prefers the TorchScript archive when it exists).
    """
    aliases = {
        "accuracy": "val_accuracy",
        "precision": "val_precision",
        "recall": "val_recall",
        "f1": "val_f1",
        "roc_auc": "val_roc_auc",
        "loss": "val_loss",
    }
    out: dict[str, Any] = {}
    for key, value in (metrics or {}).items():
        out[aliases.get(key, key)] = value
    return out


def save_checkpoint(
    path: Path,
    model: nn.Module,
    *,
    config: TrainConfig,
    spec: PreprocessSpec,
    metrics: dict,
    dataset_info: dict,
    arch_config: dict,
    epoch: int,
) -> None:
    bundle = {
        "format_version": FORMAT_VERSION,
        "architecture": arch_config,
        "state_dict": model.state_dict(),
        "class_labels": list(CLASS_LABELS),
        "metadata": build_metadata(config, spec, metrics, dataset_info, epoch=epoch),
    }
    torch.save(bundle, path)


def build_metadata(
    config: TrainConfig,
    spec: PreprocessSpec,
    metrics: dict,
    dataset_info: dict,
    *,
    epoch: int | None = None,
) -> dict[str, Any]:
    arch_config = {
        "architecture": config.architecture,
        "in_channels": config.channels,
        "num_classes": len(CLASS_LABELS),
        "base_channels": config.base_channels,
        "dropout": config.dropout,
        "classifier_dropout": config.classifier_dropout,
    }
    return {
        "name": "BrainScan CNN" if config.architecture == "cnn" else f"BrainScan {config.architecture}",
        "version": __version__,
        "class_labels": list(CLASS_LABELS),
        "channels": config.channels,
        "img_size": config.img_size,
        "preprocess": spec.to_metadata(),
        "architecture": arch_config,
        "metrics": normalize_metrics(metrics),
        "dataset": dataset_info,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "trained_on": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "platform": platform.platform(),
            "device": config.device,
        },
        "hyperparameters": {
            k: v
            for k, v in asdict(config).items()
            if k not in {"history", "data_dir", "output_dir", "notes"} and not isinstance(v, (list, dict))
        },
        "epochs_completed": epoch,
        "notes": config.notes
        or (
            "DEMO MODEL trained on procedurally generated phantom images. It validates the pipeline "
            "only — it is not trained on medical data and must not be used for diagnosis."
            if "synthetic" in config.data_dir.lower()
            else ""
        ),
    }


def write_metadata(path: Path, metadata: dict) -> None:
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def export_torchscript(model: nn.Module, path: Path, spec: PreprocessSpec) -> None:
    model.eval().cpu()
    example = torch.zeros((1, spec.channels, spec.img_size, spec.img_size))
    try:
        scripted = torch.jit.trace(model, example)
    except Exception:  # pragma: no cover - fall back to scripting
        scripted = torch.jit.script(model)
    scripted.save(str(path))


def plot_curves(history: list[dict[str, float]], path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - matplotlib is optional for reports
        return
    if not history:
        return

    epochs = [entry["epoch"] for entry in history]
    panels = [
        ("loss", ["train_loss", "val_loss"], "Loss"),
        ("accuracy", ["train_accuracy", "val_accuracy"], "Accuracy"),
        ("metrics", ["val_precision", "val_recall", "val_f1"], "Validation metrics"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, (_, keys, title) in zip(axes, panels):
        for key in keys:
            values = [entry.get(key) for entry in history]
            if any(v is not None for v in values):
                ax.plot(epochs, values, marker="o", markersize=3, label=key)
        ax.set_title(title)
        ax.set_xlabel("Epoch")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover
        return
    matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(CLASS_LABELS))))
    fig, ax = plt.subplots(figsize=(4.5, 4))
    image = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(CLASS_LABELS)), [name.replace("_", " ") for name in CLASS_LABELS])
    ax.set_yticks(range(len(CLASS_LABELS)), [name.replace("_", " ") for name in CLASS_LABELS])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Validation confusion matrix")
    threshold = matrix.max() / 2 if matrix.max() else 1
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                    color="white" if matrix[i, j] > threshold else "black")
    fig.colorbar(image, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def train(config: TrainConfig) -> dict[str, Any]:
    set_seed(config.seed)
    device = resolve_device(config.device)
    config.device = str(device)

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("BrainScan AI — training")
    print("=" * 78)
    print(f"dataset      : {config.data_dir}")
    print(f"device       : {device}")
    print(f"architecture : {config.architecture} (base_channels={config.base_channels})")
    print(f"input        : {config.img_size}px x {config.channels}ch  brain_extraction={config.brain_extraction}")

    try:
        index = discover_dataset(config.data_dir)
    except DatasetError as exc:
        raise SystemExit(f"Dataset error: {exc}") from exc

    train_paths, train_labels, val_paths, val_labels = split_index(
        index, val_fraction=config.val_fraction, seed=config.seed
    )
    if not val_paths:  # tiny datasets: hold out one image per class
        val_paths, val_labels = train_paths[-2:], train_labels[-2:]
        train_paths, train_labels = train_paths[:-2], train_labels[:-2]

    dataset_info = {
        "root": str(index.root),
        "layout": index.summary(),
        "counts": {
            "train": label_counts(train_labels),
            "val": label_counts(val_labels),
            "total": len(train_paths) + len(val_paths),
        },
        "class_labels": list(CLASS_LABELS),
        "synthetic": "synthetic" in str(index.root).lower(),
    }
    print(f"train images : {len(train_paths)} {label_counts(train_labels)}")
    print(f"val images   : {len(val_paths)} {label_counts(val_labels)}")

    spec = PreprocessSpec(
        img_size=config.img_size,
        channels=config.channels,
        brain_extraction=config.brain_extraction,
    )

    train_dataset = BrainMRIDataset(
        train_paths,
        train_labels,
        spec,
        augment=config.augment,
        noise_std=0.015 if config.augment else 0.0,
        seed=config.seed,
    )
    val_dataset = BrainMRIDataset(val_paths, val_labels, spec, augment=False, seed=config.seed)

    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        drop_last=len(train_dataset) > config.batch_size,
        persistent_workers=config.num_workers > 0,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=config.batch_size, shuffle=False, num_workers=config.num_workers
    )

    model = build_model(
        config.architecture,
        in_channels=config.channels,
        num_classes=len(CLASS_LABELS),
        base_channels=config.base_channels,
        dropout=config.dropout,
        classifier_dropout=config.classifier_dropout,
        pretrained=config.pretrained,
    ).to(device)

    arch_config = {
        "architecture": config.architecture,
        "in_channels": config.channels,
        "num_classes": len(CLASS_LABELS),
        "base_channels": config.base_channels,
        "dropout": config.dropout,
        "classifier_dropout": config.classifier_dropout,
    }
    parameters = sum(p.numel() for p in model.parameters())
    print(f"parameters   : {parameters:,}")

    weights = None
    if config.use_class_weights:
        weights = torch.tensor(compute_class_weights(train_labels, len(CLASS_LABELS)), dtype=torch.float32, device=device)
        print(f"class weights: {weights.tolist()}")
    criterion = nn.CrossEntropyLoss(weight=weights)

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr, weight_decay=config.weight_decay)
    scheduler: Any = None
    if config.scheduler == "cosine":
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, config.epochs), eta_min=config.lr * 0.01)
    elif config.scheduler == "plateau":
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    scaler = torch.amp.GradScaler("cuda") if (config.amp and device.type == "cuda") else None

    best_score = -float("inf")
    best_epoch = 0
    patience_counter = 0
    started = time.time()

    for epoch in range(1, config.epochs + 1):
        train_loss, train_true, train_pred = run_epoch(
            model,
            train_loader,
            criterion,
            device,
            optimizer=optimizer,
            scaler=scaler,
            use_amp=config.amp,
            limit_batches=config.limit_batches,
            epoch=epoch,
            total_epochs=config.epochs,
            log_prefix="train ",
        )
        val_loss, val_true, val_pred = run_epoch(
            model,
            val_loader,
            criterion,
            device,
            limit_batches=config.limit_batches,
            epoch=epoch,
            total_epochs=config.epochs,
            log_prefix="val   ",
        )
        val_probs = collect_probabilities(model, val_loader, device, limit_batches=config.limit_batches)

        train_metrics = compute_metrics(train_true, train_pred, np.zeros((0, 2)), train_loss)
        val_metrics = compute_metrics(val_true, val_pred, val_probs, val_loss)

        current_lr = float(optimizer.param_groups[0]["lr"])
        record = {
            "epoch": epoch,
            "lr": round(current_lr, 6),
            "train_loss": train_metrics["loss"],
            "train_accuracy": train_metrics["accuracy"],
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_precision": val_metrics["precision"],
            "val_recall": val_metrics["recall"],
            "val_f1": val_metrics["f1"],
            "val_roc_auc": val_metrics["roc_auc"],
            "seconds": round(time.time() - started, 1),
        }
        config.history.append(record)

        print(
            f"[epoch {epoch:>3}/{config.epochs}] "
            f"train_loss={record['train_loss']:.4f} acc={record['train_accuracy']:.4f} | "
            f"val_loss={record['val_loss']:.4f} acc={record['val_accuracy']:.4f} "
            f"f1={record['val_f1']:.4f} auc={record['val_roc_auc']} lr={current_lr:.2e}",
            flush=True,
        )

        score = {
            "val_accuracy": val_metrics["accuracy"],
            "val_f1": val_metrics["f1"],
            "val_loss": -val_metrics["loss"],
        }.get(config.monitor, val_metrics["accuracy"])

        if score > best_score:
            best_score = score
            best_epoch = epoch
            patience_counter = 0
            save_checkpoint(
                output_dir / CHECKPOINT_NAME,
                model,
                config=config,
                spec=spec,
                metrics={
                    **normalize_metrics(val_metrics),
                    "train_accuracy": train_metrics["accuracy"],
                    "train_loss": train_metrics["loss"],
                    "epoch": epoch,
                    "parameters": parameters,
                },
                dataset_info=dataset_info,
                arch_config=arch_config,
                epoch=epoch,
            )
            print(f"    ↳ new best ({config.monitor}={score:.4f}) → {output_dir / CHECKPOINT_NAME}")
        else:
            patience_counter += 1
            if config.patience and patience_counter >= config.patience:
                print(f"Early stopping at epoch {epoch} (no improvement for {config.patience} epochs).")
                break

        if scheduler is not None:
            if config.scheduler == "plateau":
                scheduler.step(val_metrics["accuracy"])
            else:
                scheduler.step()

    # ---- final report -----------------------------------------------------
    # Restore the BEST checkpoint before reporting/exporting so that
    # model.pt, model_scripted.pt, metadata.json and the report all describe
    # the same weights.
    best_checkpoint = output_dir / CHECKPOINT_NAME
    if best_checkpoint.is_file():
        model.load_state_dict(torch.load(best_checkpoint, map_location=device, weights_only=False)["state_dict"])
        model.to(device)
        print(f"Restored best checkpoint (epoch {best_epoch}) for reporting and export.")

    model.eval()
    val_loss, val_true, val_pred = run_epoch(model, val_loader, criterion, device, limit_batches=config.limit_batches)
    val_probs = collect_probabilities(model, val_loader, device, limit_batches=config.limit_batches)
    final_metrics = compute_metrics(val_true, val_pred, val_probs, val_loss)
    final_metrics["parameters"] = parameters
    final_metrics["best_epoch"] = best_epoch
    final_metrics["monitor"] = config.monitor
    final_metrics["monitor_score"] = round(float(best_score), 4)

    elapsed = time.time() - started
    report_text = classification_report(
        val_true, val_pred, target_names=[name.replace("_", " ") for name in CLASS_LABELS], zero_division=0
    )

    metadata = build_metadata(config, spec, final_metrics, dataset_info, epoch=best_epoch)
    write_metadata(output_dir / METADATA_NAME, metadata)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {k: v for k, v in asdict(config).items() if k != "history"},
        "dataset": dataset_info,
        "final_metrics": final_metrics,
        "history": config.history,
        "classification_report": report_text,
        "confusion_matrix": confusion_matrix(
            val_true, val_pred, labels=list(range(len(CLASS_LABELS)))
        ).tolist(),
        "duration_seconds": round(elapsed, 1),
        "duration_human": human_duration(elapsed),
    }
    (output_dir / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "classification_report.txt").write_text(report_text, encoding="utf-8")

    plot_curves(config.history, output_dir / "training_curves.png")
    if val_true.size:
        plot_confusion_matrix(val_true, val_pred, output_dir / "confusion_matrix.png")

    if config.export_torchscript:
        export_torchscript(model, output_dir / SCRIPTED_NAME, spec)
        print(f"TorchScript archive → {output_dir / SCRIPTED_NAME}")

    print("-" * 78)
    print(f"Training finished in {human_duration(elapsed)} (best epoch {best_epoch})")
    print(f"val accuracy {final_metrics['accuracy']:.4f} | f1 {final_metrics['f1']:.4f} | "
          f"precision {final_metrics['precision']:.4f} | recall {final_metrics['recall']:.4f} | "
          f"auc {final_metrics['roc_auc']}")
    print(f"Checkpoint  → {output_dir / CHECKPOINT_NAME}")
    print(f"Metadata    → {output_dir / METADATA_NAME}")
    print(f"Report      → {output_dir / 'training_report.json'}")
    print("-" * 78)
    print(report_text)
    return report


def parse_args(argv: list[str] | None = None) -> TrainConfig:
    parser = argparse.ArgumentParser(
        description="Train the BrainScan AI brain tumour classifier",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--data-dir", default="data/brain-tumor", help="Dataset root (class sub-folders)")
    parser.add_argument("--output-dir", default="data/models", help="Where to write checkpoints and reports")
    parser.add_argument("--tag", default="", help="Optional run tag stored in metadata")
    parser.add_argument("--architecture", default="cnn", help="cnn | resnet18 | resnet50 | efficientnet_b0")
    parser.add_argument("--pretrained", action="store_true", help="Use ImageNet weights (torchvision backbones)")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--channels", type=int, default=3, choices=(1, 3))
    parser.add_argument("--base-channels", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--classifier-dropout", type=float, default=0.4)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto", help="auto | cpu | cuda | mps")
    parser.add_argument("--patience", type=int, default=6, help="Early-stopping patience (0 disables)")
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--no-brain-extraction", action="store_true", help="Disable head cropping in preprocessing")
    parser.add_argument("--no-augment", action="store_true", help="Disable training augmentation")
    parser.add_argument("--no-class-weights", action="store_true", help="Disable inverse-frequency class weights")
    parser.add_argument("--scheduler", default="cosine", choices=("cosine", "plateau", "none"))
    parser.add_argument("--no-amp", action="store_true", help="Disable mixed precision on CUDA")
    parser.add_argument("--monitor", default="val_accuracy", choices=("val_accuracy", "val_f1", "val_loss"))
    parser.add_argument("--export-torchscript", action="store_true", help="Also export a TorchScript archive")
    parser.add_argument("--limit-batches", type=int, default=0, help="Smoke-test mode: N batches per epoch")
    parser.add_argument("--notes", default="", help="Free-text note stored in the checkpoint metadata")
    args = parser.parse_args(argv)

    return TrainConfig(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        tag=args.tag,
        architecture=args.architecture,
        pretrained=args.pretrained,
        epochs=args.epochs,
        batch_size=args.batch_size,
        img_size=args.img_size,
        channels=args.channels,
        base_channels=args.base_channels,
        dropout=args.dropout,
        classifier_dropout=args.classifier_dropout,
        lr=args.lr,
        weight_decay=args.weight_decay,
        val_fraction=args.val_fraction,
        seed=args.seed,
        device=args.device,
        patience=args.patience,
        num_workers=args.num_workers,
        brain_extraction=not args.no_brain_extraction,
        augment=not args.no_augment,
        use_class_weights=not args.no_class_weights,
        scheduler=args.scheduler,
        amp=not args.no_amp,
        monitor=args.monitor,
        export_torchscript=args.export_torchscript,
        limit_batches=args.limit_batches,
        notes=args.notes,
    )


def main(argv: list[str] | None = None) -> None:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    train(parse_args(argv))


if __name__ == "__main__":
    main()
