#!/usr/bin/env python3
"""Temporary model factory for Issue #296 architecture screening.

Delete before PR preparation unless a selected architecture needs equivalent
production support.
"""
from __future__ import annotations

from pathlib import Path

import torch
from torchvision import models


def build_model(model_name: str, pretrained: bool = True) -> torch.nn.Module:
    weights = "DEFAULT" if pretrained else None
    if model_name == "resnet18":
        model = models.resnet18(weights=weights)
        model.fc = torch.nn.Linear(model.fc.in_features, 1)
    elif model_name == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=weights)
        model.classifier[3] = torch.nn.Linear(model.classifier[3].in_features, 1)
    elif model_name == "mobilenet_v3_large":
        model = models.mobilenet_v3_large(weights=weights)
        model.classifier[3] = torch.nn.Linear(model.classifier[3].in_features, 1)
    elif model_name == "efficientnet_b0":
        model = models.efficientnet_b0(weights=weights)
        model.classifier[1] = torch.nn.Linear(model.classifier[1].in_features, 1)
    else:
        raise ValueError(f"unsupported Issue #296 architecture: {model_name}")
    return model


def load_checkpoint(
    checkpoint: Path | str,
    model_name: str,
    device: torch.device | str,
) -> torch.nn.Module:
    model = build_model(model_name, pretrained=False)
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


def parameter_count(model: torch.nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())
