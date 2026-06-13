"""Shared crop contract helpers for CNN barline candidate crops.

This module is intentionally small and dependency-light so that both dataset
construction and inference-side scoring can use the same crop geometry.
The default contract mirrors the historical binary CNN crop behavior:

- crop height = bbox height * 3.0, clamped to [48, 256]
- crop width = crop height * 0.5, clamped to [16, 128]
- crop is centered on the candidate center and padded with white at image edges

Issue #206 uses the same helpers to preview wider context variants without
changing existing training or scoring defaults.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

import cv2
import numpy as np


BBox = Sequence[float]
WHITE_BGR = (255, 255, 255)


@dataclass(frozen=True)
class CropContract:
    """Geometry settings for candidate-centered CNN crops."""

    name: str = "current_like"
    scale: float = 3.0
    aspect_ratio: float = 0.5
    min_h: int = 48
    max_h: int = 256
    min_w: int = 16
    max_w: int = 128
    pad_value: tuple[int, int, int] = WHITE_BGR

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CropResult:
    """Result metadata for a generated crop."""

    crop: np.ndarray
    crop_box: tuple[int, int, int, int]
    padding: tuple[int, int, int, int]

    @property
    def padding_applied(self) -> bool:
        return any(v > 0 for v in self.padding)


CURRENT_LIKE_CONTRACT = CropContract()

CONTEXT_PREVIEW_CONTRACTS: dict[str, CropContract] = {
    "current_like": CURRENT_LIKE_CONTRACT,
    "wider_x": CropContract(
        name="wider_x",
        scale=3.0,
        aspect_ratio=1.5,
        min_h=48,
        max_h=256,
        min_w=48,
        max_w=384,
    ),
    "square_context": CropContract(
        name="square_context",
        scale=4.0,
        aspect_ratio=1.0,
        min_h=64,
        max_h=512,
        min_w=64,
        max_w=512,
    ),
}


def bbox_center(box: BBox) -> tuple[int, int]:
    """Return the integer center point for a bbox."""

    x1, y1, x2, y2 = box
    return int(round((float(x1) + float(x2)) / 2.0)), int(round((float(y1) + float(y2)) / 2.0))


def crop_size_from_bbox(box: BBox, contract: CropContract = CURRENT_LIKE_CONTRACT) -> tuple[int, int]:
    """Compute `(crop_w, crop_h)` from bbox height and a crop contract."""

    _, y1, _, y2 = box
    bbox_h = max(1.0, abs(float(y2) - float(y1)))
    crop_h = int(round(bbox_h * float(contract.scale)))
    crop_h = max(int(contract.min_h), min(int(contract.max_h), crop_h))
    crop_w = int(round(crop_h * float(contract.aspect_ratio)))
    crop_w = max(int(contract.min_w), min(int(contract.max_w), crop_w))
    return crop_w, crop_h


def center_crop(
    img: np.ndarray,
    cx: int,
    cy: int,
    crop_w: int,
    crop_h: int,
    pad_value: Iterable[int] = WHITE_BGR,
) -> CropResult:
    """Crop around `(cx, cy)` and pad with `pad_value` when crossing image bounds."""

    if img is None or not hasattr(img, "shape") or len(img.shape) < 2:
        raise ValueError("img must be a loaded image array")
    if crop_w <= 0 or crop_h <= 0:
        raise ValueError(f"crop size must be positive: crop_w={crop_w}, crop_h={crop_h}")

    img_h, img_w = img.shape[:2]
    w_half = crop_w // 2
    h_half = crop_h // 2
    cx1 = max(0, int(cx) - w_half)
    cx2 = min(img_w, int(cx) + w_half)
    cy1 = max(0, int(cy) - h_half)
    cy2 = min(img_h, int(cy) + h_half)

    crop = img[cy1:cy2, cx1:cx2]

    pad_y1 = max(0, h_half - (int(cy) - cy1))
    pad_y2 = max(0, h_half - (cy2 - int(cy)))
    pad_x1 = max(0, w_half - (int(cx) - cx1))
    pad_x2 = max(0, w_half - (cx2 - int(cx)))

    if pad_y1 or pad_y2 or pad_x1 or pad_x2:
        crop = cv2.copyMakeBorder(
            crop,
            pad_y1,
            pad_y2,
            pad_x1,
            pad_x2,
            cv2.BORDER_CONSTANT,
            value=list(pad_value),
        )

    return CropResult(
        crop=crop,
        crop_box=(int(cx1), int(cy1), int(cx2), int(cy2)),
        padding=(int(pad_y1), int(pad_y2), int(pad_x1), int(pad_x2)),
    )


def crop_candidate(
    img: np.ndarray,
    box: BBox,
    contract: CropContract = CURRENT_LIKE_CONTRACT,
    *,
    center_override: tuple[int, int] | None = None,
) -> CropResult:
    """Generate a candidate crop using the supplied contract."""

    cx, cy = center_override if center_override is not None else bbox_center(box)
    crop_w, crop_h = crop_size_from_bbox(box, contract)
    return center_crop(img, cx, cy, crop_w, crop_h, contract.pad_value)


def contract_from_mapping(data: dict, *, name: str | None = None) -> CropContract:
    """Create a `CropContract` from a config mapping."""

    base = CURRENT_LIKE_CONTRACT.as_dict()
    base.update({k: v for k, v in data.items() if k in base and k != "pad_value"})
    if name is not None:
        base["name"] = name
    if "pad_value" in data:
        base["pad_value"] = tuple(int(v) for v in data["pad_value"])
    return CropContract(**base)


def resolve_contracts(names: Sequence[str] | None = None) -> list[CropContract]:
    """Resolve named built-in preview contracts."""

    if not names:
        names = ["current_like"]
    contracts = []
    for name in names:
        if name not in CONTEXT_PREVIEW_CONTRACTS:
            known = ", ".join(sorted(CONTEXT_PREVIEW_CONTRACTS))
            raise ValueError(f"unknown crop contract variant: {name}; known variants: {known}")
        contracts.append(CONTEXT_PREVIEW_CONTRACTS[name])
    return contracts
