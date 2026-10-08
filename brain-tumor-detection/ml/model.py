"""CNN architecture for brain tumor classification.

A compact VGG-style network: strided stem, three conv+pool stages, one refinement
conv, batch normalisation and global average pooling. It trains on a laptop
CPU in minutes and keeps inference fast enough for interactive use.
"""

from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn

from .constants import CLASS_NAMES

DEFAULT_CHANNELS: tuple[int, ...] = (64, 128, 256)


def conv_bn_relu(in_channels: int, out_channels: int, stride: int = 1) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False),
        nn.BatchNorm2d(out_channels),
        nn.ReLU(inplace=True),
    )


class ConvBlock(nn.Sequential):
    """3x3 convolution (BN + ReLU) followed by 2x2 max pooling."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__(conv_bn_relu(in_channels, out_channels), nn.MaxPool2d(kernel_size=2))


class BrainTumorCNN(nn.Module):
    """Feature extractor, global average pooling and a two-layer classifier head."""

    def __init__(
        self,
        num_classes: int = len(CLASS_NAMES),
        channels: Sequence[int] = DEFAULT_CHANNELS,
        dropout: float = 0.4,
        in_channels: int = 3,
    ) -> None:
        super().__init__()
        # Strided stem halves the resolution cheaply before the expensive stages.
        blocks: list[nn.Module] = [conv_bn_relu(in_channels, channels[0] // 2, stride=2)]
        previous = channels[0] // 2
        for width in channels:
            blocks.append(ConvBlock(previous, width))
            previous = width
        # Extra refinement conv at the deepest (cheapest) resolution.
        blocks.append(conv_bn_relu(previous, previous))
        self.features = nn.Sequential(*blocks)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(p=dropout),
            nn.Linear(previous, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout / 2),
            nn.Linear(128, num_classes),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv2d):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, 0.0, 0.01)
                nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Return unnormalised class logits of shape ``(batch, num_classes)``."""
        x = self.features(x)
        x = self.pool(x)
        return self.classifier(x)
