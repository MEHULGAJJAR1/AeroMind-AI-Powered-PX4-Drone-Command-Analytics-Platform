"""CNN architectures for brain tumour classification.

``BrainTumorCNN`` is a compact four-block convolutional network (~1.4 M
parameters) that trains comfortably on CPU and reaches high accuracy on the
public brain-MRI datasets. Pretrained torchvision backbones can be used instead
via :func:`build_model` (requires ``torchvision``).
"""

from __future__ import annotations

import math
from typing import Any

import torch
import torch.nn as nn

DEFAULT_ARCHITECTURES: tuple[str, ...] = ("cnn", "resnet18", "resnet50", "efficientnet_b0")


class ConvBlock(nn.Module):
    """conv3x3 → BN → ReLU → conv3x3 → BN → ReLU → MaxPool → Dropout2d."""

    def __init__(self, in_channels: int, out_channels: int, dropout: float = 0.1) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),
            nn.Dropout2d(p=dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class BrainTumorCNN(nn.Module):
    """Compact CNN with a global-average-pool head.

    Parameters
    ----------
    in_channels: 1 for grayscale MRI, 3 for RGB.
    num_classes: 2 for the binary no_tumor / tumor task.
    base_channels: width of the first block; doubles at every block.
    dropout / classifier_dropout: regularisation strengths.
    """

    def __init__(
        self,
        in_channels: int = 3,
        num_classes: int = 2,
        base_channels: int = 32,
        dropout: float = 0.15,
        classifier_dropout: float = 0.4,
        head_hidden: int = 128,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.num_classes = num_classes
        self.base_channels = base_channels
        self.dropout = dropout
        self.classifier_dropout = classifier_dropout
        self.head_hidden = head_hidden

        widths = [base_channels, base_channels * 2, base_channels * 4, base_channels * 8]
        layers: list[nn.Module] = []
        previous = in_channels
        for width in widths:
            layers.append(ConvBlock(previous, width, dropout=dropout))
            previous = width

        self.features = nn.Sequential(*layers)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(p=classifier_dropout),
            nn.Linear(widths[-1], head_hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(p=classifier_dropout / 2),
            nn.Linear(head_hidden, num_classes),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv2d):
                # Conv layers are followed by BatchNorm → fan_out + ReLU is the standard choice.
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.BatchNorm2d):
                nn.init.constant_(module.weight, 1.0)
                nn.init.constant_(module.bias, 0.0)
            elif isinstance(module, nn.Linear):
                # Fan-in scaling (PyTorch's own default) — fan_out here blows up the logits.
                nn.init.kaiming_uniform_(module.weight, a=math.sqrt(5))
                if module.bias is not None:
                    fan_in = module.weight.shape[1]
                    bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
                    nn.init.uniform_(module.bias, -bound, bound)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Return raw logits (``B x num_classes``)."""
        return self.classifier(self.pool(self.features(x)))

    def describe(self) -> dict[str, Any]:
        return {
            "architecture": "cnn",
            "name": "BrainTumorCNN",
            "in_channels": self.in_channels,
            "num_classes": self.num_classes,
            "base_channels": self.base_channels,
            "dropout": self.dropout,
            "classifier_dropout": self.classifier_dropout,
            "head_hidden": self.head_hidden,
            "parameters": sum(p.numel() for p in self.parameters()),
            "trainable_parameters": sum(p.numel() for p in self.parameters() if p.requires_grad),
        }


def build_model(
    architecture: str = "cnn",
    *,
    in_channels: int = 3,
    num_classes: int = 2,
    base_channels: int = 32,
    dropout: float = 0.15,
    classifier_dropout: float = 0.4,
    head_hidden: int = 128,
    pretrained: bool = False,
) -> nn.Module:
    """Construct a model by name.

    ``cnn`` → :class:`BrainTumorCNN` (no external download).
    ``resnet18`` / ``resnet50`` / ``efficientnet_b0`` → torchvision backbones;
    ``pretrained=True`` downloads ImageNet weights (needs internet access).
    """
    arch = (architecture or "cnn").lower()

    if arch in {"cnn", "custom", "brainnet"}:
        return BrainTumorCNN(
            in_channels=in_channels,
            num_classes=num_classes,
            base_channels=base_channels,
            dropout=dropout,
            classifier_dropout=classifier_dropout,
            head_hidden=head_hidden,
        )

    try:
        from torchvision import models  # imported lazily: optional dependency
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            f"Architecture '{arch}' requires torchvision. Install it with `pip install torchvision` "
            "or train with --architecture cnn."
        ) from exc

    weights_arg: Any = "IMAGENET1K_V1" if pretrained else None
    if arch == "resnet18":
        model: nn.Module = models.resnet18(weights=weights_arg)
        features_out = 512
    elif arch == "resnet50":
        model = models.resnet50(weights=weights_arg)
        features_out = 2048
    elif arch == "efficientnet_b0":
        model = models.efficientnet_b0(weights=weights_arg)
        features_out = 1280
    else:
        raise ValueError(
            f"Unknown architecture '{architecture}'. Choose one of {', '.join(DEFAULT_ARCHITECTURES)}."
        )

    if in_channels != 3:
        first = next(model.children())
        if isinstance(first, nn.Conv2d):
            new_first = nn.Conv2d(
                in_channels,
                first.out_channels,
                kernel_size=first.kernel_size,
                stride=first.stride,
                padding=first.padding,
                bias=first.bias is not None,
            )
            with torch.no_grad():
                # Average the pretrained RGB filters so grayscale keeps the learned statistics.
                new_first.weight.copy_(first.weight.mean(dim=1, keepdim=True).repeat(1, in_channels, 1, 1))
                if first.bias is not None:
                    new_first.bias.copy_(first.bias)
            children = list(model.children())
            children[0] = new_first
            model = nn.Sequential(*children)

    if arch.startswith("resnet"):
        model.fc = nn.Sequential(
            nn.Dropout(p=classifier_dropout),
            nn.Linear(features_out, head_hidden),
            nn.ReLU(inplace=True),
            nn.Linear(head_hidden, num_classes),
        )
    else:
        model.classifier = nn.Sequential(
            nn.Dropout(p=classifier_dropout, inplace=True),
            nn.Linear(features_out, head_hidden),
            nn.ReLU(inplace=True),
            nn.Linear(head_hidden, num_classes),
        )
    return model


def model_from_config(config: dict[str, Any]) -> nn.Module:
    """Rebuild a model from a checkpoint's stored ``architecture`` block.

    Unknown keys (``name``, ``parameters``, ...) are ignored so metadata can grow
    without breaking older checkpoints.
    """
    import inspect

    allowed = set(inspect.signature(build_model).parameters)
    params = {key: value for key, value in (config or {}).items() if key in allowed}
    params.setdefault("pretrained", False)
    return build_model(**params)
