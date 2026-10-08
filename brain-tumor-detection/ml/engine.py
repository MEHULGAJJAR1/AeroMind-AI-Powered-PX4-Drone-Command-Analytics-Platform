"""Reusable training and evaluation loops."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader


@dataclass
class EpochResult:
    loss: float
    accuracy: float
    labels: list[int] = field(default_factory=list)
    predictions: list[int] = field(default_factory=list)


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    scheduler: torch.optim.lr_scheduler.LRScheduler | None = None,
) -> EpochResult:
    model.train()
    total_loss, correct, seen = 0.0, 0, 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        if scheduler is not None:
            scheduler.step()
        total_loss += float(loss.item()) * labels.size(0)
        correct += int((logits.argmax(dim=1) == labels).sum().item())
        seen += labels.size(0)
    return EpochResult(loss=total_loss / max(seen, 1), accuracy=correct / max(seen, 1))


@torch.inference_mode()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module | None,
    device: torch.device,
) -> EpochResult:
    model.eval()
    total_loss, seen = 0.0, 0
    labels_all: list[int] = []
    preds_all: list[int] = []
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        logits = model(images)
        if criterion is not None:
            total_loss += float(criterion(logits, labels).item()) * labels.size(0)
        seen += labels.size(0)
        labels_all.extend(labels.cpu().tolist())
        preds_all.extend(logits.argmax(dim=1).cpu().tolist())
    accuracy = float(np.mean(np.asarray(labels_all) == np.asarray(preds_all))) if seen else 0.0
    return EpochResult(
        loss=total_loss / max(seen, 1),
        accuracy=accuracy,
        labels=labels_all,
        predictions=preds_all,
    )
