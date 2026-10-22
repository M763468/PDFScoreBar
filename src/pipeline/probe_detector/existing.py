"""Lookup and suppression against existing barlines in a staff band."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from .types import Box


@dataclass
class ExistingBarlines:
    boxes: Sequence[Box]
    x_merge_tol: int
    min_vertical_iou: float
    disable_suppression: bool

    def has_existing(self, x_center: float, y1: int, y2: int) -> bool:
        band_h = max(1.0, y2 - y1)
        for bx1, by1, bx2, by2 in self.boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= self.x_merge_tol:
                if self.min_vertical_iou > 0:
                    iy1 = max(y1, min(by1, by2))
                    iy2 = min(y2, max(by1, by2))
                    inter = max(0.0, iy2 - iy1)
                    box_h = max(1.0, abs(by2 - by1))
                    union = max(1.0, band_h + box_h - inter)
                    v_iou = inter / union
                    if v_iou < self.min_vertical_iou:
                        continue
                return True
        return False

    def has_existing_for_suppression(self, x_center: float, y1: int, y2: int) -> bool:
        if self.disable_suppression:
            return False
        return self.has_existing(x_center, y1, y2)

    def closest_existing_band(self, x_center: float, y1: int, y2: int) -> Tuple[int, int] | None:
        best = None
        best_dx = None
        for bx1, by1, bx2, by2 in self.boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            dx = abs(cx - x_center)
            if best_dx is None or dx < best_dx:
                best_dx = dx
                best = (int(by1), int(by2))
        return best
