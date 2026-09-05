#!/usr/bin/env python3
"""Temporary Issue #296 shared-backbone multi-view EfficientNet-B0.

Diagnostic-only. Delete before PR preparation unless this design is selected.
"""
from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
from torchvision import models


class EfficientNetB0MultiView(nn.Module):
    """Encode tight and square-context views with one shared ImageNet backbone."""

    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        weights = "DEFAULT" if pretrained else None
        base = models.efficientnet_b0(weights=weights)
        self.features = base.features
        self.avgpool = base.avgpool
        feature_dim = base.classifier[1].in_features
        self.dropout = nn.Dropout(p=0.2)
        self.classifier = nn.Linear(feature_dim * 2, 1)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.avgpool(x)
        return torch.flatten(x, 1)

    def forward(self, tight: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        tight_features = self.encode(tight)
        context_features = self.encode(context)
        fused = torch.cat([tight_features, context_features], dim=1)
        return self.classifier(self.dropout(fused))


def build_multiview_model(pretrained: bool = True) -> EfficientNetB0MultiView:
    return EfficientNetB0MultiView(pretrained=pretrained)


def load_multiview_checkpoint(
    checkpoint: Path | str,
    device: torch.device | str,
) -> EfficientNetB0MultiView:
    model = build_multiview_model(pretrained=False)
    state = torch.load(Path(checkpoint), map_location="cpu")
    if any(key.startswith("_orig_mod.") for key in state):
        state = {
            (key[len("_orig_mod.") :] if key.startswith("_orig_mod.") else key): value
            for key, value in state.items()
        }
    model.load_state_dict(state)
    model.to(device)
    model.eval()
    return model


def parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())
