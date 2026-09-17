"""Shared-encoder staff aggregation model for Issue #332."""

from __future__ import annotations

import torch
import torch.nn as nn
from torchvision import models
from torchvision.models import ResNet18_Weights


class StaffRelativeResNet18(nn.Module):
    """Shared ResNet18 over staff crops with one max-logit per measure."""

    def __init__(self, *, weights=ResNet18_Weights.IMAGENET1K_V1):
        super().__init__()
        self.encoder = models.resnet18(weights=weights)
        self.encoder.fc = nn.Linear(self.encoder.fc.in_features, 1)

    def forward(self, staff_images: torch.Tensor, staff_mask: torch.Tensor) -> torch.Tensor:
        batch_size, staff_count = staff_images.shape[:2]
        logits = self.encoder(
            staff_images.reshape(batch_size * staff_count, *staff_images.shape[2:])
        )
        logits = logits.reshape(batch_size, staff_count)
        logits = logits.masked_fill(~staff_mask, torch.finfo(logits.dtype).min)
        return logits.max(dim=1, keepdim=True).values
