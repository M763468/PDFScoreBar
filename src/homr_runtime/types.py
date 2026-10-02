"""HOMR prediction and coordinate transformation records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Box = Tuple[int, int, int, int]


@dataclass
class TransformInfo:
    original_shape: Tuple[int, int]  # width, height
    crop_box: Tuple[int, int, int, int]  # x, y, w, h
    resize_shape: Tuple[int, int]
    seg_shape: Tuple[int, int]
    resize_scale: Tuple[float, float]
    seg_scale: Tuple[float, float]

    @property
    def total_scale(self) -> Tuple[float, float]:
        return (
            self.resize_scale[0] * self.seg_scale[0],
            self.resize_scale[1] * self.seg_scale[1],
        )


@dataclass
class BarlinePrediction:
    pred_bbox: Tuple[int, int, int, int]
    orig_bbox: Tuple[int, int, int, int]
    system_index: int
    staff_index: int
