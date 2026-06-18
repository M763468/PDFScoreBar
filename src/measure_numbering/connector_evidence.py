from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import cv2
import numpy as np

from .types import Staff


class SystemConnectorEvidenceExtractor:
    """Builds staff-pair connector evidence from proxy symbol/brace masks."""

    CONNECTOR_DENSITY_THRESHOLD = 0.05
    LEFT_MARGIN = 100
    RIGHT_MARGIN = 120
    VERTICAL_OPEN_HEIGHT_RATIO = 0.65

    def extract(
        self,
        staves: list[Staff],
        image_size: Tuple[int, int],
        *,
        symbol_mask: Optional[np.ndarray] = None,
        brace_dot_mask: Optional[np.ndarray] = None,
        source: str = "proxy_symbol_layers",
    ) -> dict[str, Any]:
        """Return structured left/system-start connector evidence.

        `image_size` is `(width, height)` in the original page coordinate system used by
        staff and barline boxes. Masks may be rendered at another resolution; ROIs are
        scaled to each mask independently.
        """
        sorted_staves = sorted(staves, key=lambda staff: staff.bbox.y1)
        evidence = {
            "evidence_version": 1,
            "generated": True,
            "source": source,
            "image_size": [int(image_size[0]), int(image_size[1])],
            "staff_pairs": [],
        }

        for i in range(len(sorted_staves) - 1):
            s1 = sorted_staves[i]
            s2 = sorted_staves[i + 1]
            symbol_stats = self._mask_roi_stats(symbol_mask, s1, s2, image_size)
            brace_stats = self._mask_roi_stats(brace_dot_mask, s1, s2, image_size)
            symbols_vertical = symbol_stats.get("vertical_open_density", 0.0)
            brace_vertical = brace_stats.get("vertical_open_density", 0.0)
            left_connector_present = (
                symbols_vertical >= self.CONNECTOR_DENSITY_THRESHOLD
                or brace_vertical >= self.CONNECTOR_DENSITY_THRESHOLD
            )

            evidence["staff_pairs"].append(
                {
                    "staff_pair": [i, i + 1],
                    "left_connector_present": bool(left_connector_present),
                    "symbols_density": symbol_stats.get("density", 0.0),
                    "symbols_vertical_open_density": symbols_vertical,
                    "brace_dot_density": brace_stats.get("density", 0.0),
                    "brace_dot_vertical_open_density": brace_vertical,
                    "symbols": symbol_stats,
                    "brace_dot": brace_stats,
                    "source": source,
                }
            )

        return evidence

    def extract_from_paths(
        self,
        staves: list[Staff],
        image_size: Tuple[int, int],
        *,
        symbol_mask_path: Optional[Path] = None,
        brace_dot_mask_path: Optional[Path] = None,
        source: str = "proxy_symbol_layers",
    ) -> dict[str, Any]:
        return self.extract(
            staves,
            image_size,
            symbol_mask=self._load_mask(symbol_mask_path),
            brace_dot_mask=self._load_mask(brace_dot_mask_path),
            source=source,
        )

    def extract_from_mask_maps(
        self,
        staves: list[Staff],
        image_size: Tuple[int, int],
        *,
        connector_masks: Optional[Mapping[str, np.ndarray]] = None,
        connector_mask_paths: Optional[Mapping[str, Path | str]] = None,
        source: str = "proxy_symbol_layers",
    ) -> dict[str, Any]:
        masks = connector_masks or {}
        mask_paths = connector_mask_paths or {}
        symbol_mask = masks.get("symbols") or masks.get("symbol")
        brace_dot_mask = masks.get("brace_dot") or masks.get("brace")

        if symbol_mask is None:
            symbol_mask = self._load_mask_from_map(mask_paths, "symbols", "symbol")
        if brace_dot_mask is None:
            brace_dot_mask = self._load_mask_from_map(mask_paths, "brace_dot", "brace")

        return self.extract(
            staves,
            image_size,
            symbol_mask=symbol_mask,
            brace_dot_mask=brace_dot_mask,
            source=source,
        )

    def write_json(self, evidence: Mapping[str, Any], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False))

    def _load_mask_from_map(
        self, paths: Mapping[str, Path | str], *keys: str
    ) -> Optional[np.ndarray]:
        for key in keys:
            value = paths.get(key)
            if value is not None:
                return self._load_mask(Path(value))
        return None

    def _load_mask(self, path: Optional[Path]) -> Optional[np.ndarray]:
        if path is None:
            return None
        mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if mask is None:
            raise FileNotFoundError(f"Connector mask not found: {path}")
        return mask

    def _mask_roi_stats(
        self,
        mask: Optional[np.ndarray],
        s1: Staff,
        s2: Staff,
        image_size: Tuple[int, int],
    ) -> dict[str, Any]:
        if mask is None:
            return {
                "exists": False,
                "density": 0.0,
                "vertical_open_density": 0.0,
                "nonzero": 0,
                "vertical_open_pixels": 0,
            }

        binary = self._to_binary(mask)
        mask_h, mask_w = binary.shape[:2]
        x1, y1, x2, y2 = self._roi_for_pair(s1, s2, image_size, (mask_w, mask_h))
        roi = binary[y1:y2, x1:x2]
        nonzero = int(np.count_nonzero(roi))
        density = float(nonzero / max(1, roi.size))
        vertical_open_pixels = self._vertical_open_pixels(roi)
        vertical_open_density = float(vertical_open_pixels / max(1, roi.size))

        return {
            "exists": True,
            "mask_shape_hw": [int(mask_h), int(mask_w)],
            "roi_xyxy": [int(x1), int(y1), int(x2), int(y2)],
            "roi_shape_hw": [int(roi.shape[0]), int(roi.shape[1])],
            "nonzero": nonzero,
            "density": density,
            "vertical_open_pixels": int(vertical_open_pixels),
            "vertical_open_density": vertical_open_density,
        }

    def _to_binary(self, mask: np.ndarray) -> np.ndarray:
        if mask.ndim == 3:
            mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        if mask.dtype == bool:
            return mask.astype(np.uint8)
        if mask.size == 0:
            return mask.astype(np.uint8)
        if mask.max() <= 1:
            return (mask > 0).astype(np.uint8)
        return (mask > 0).astype(np.uint8)

    def _roi_for_pair(
        self,
        s1: Staff,
        s2: Staff,
        image_size: Tuple[int, int],
        mask_size: Tuple[int, int],
    ) -> tuple[int, int, int, int]:
        image_w, image_h = image_size
        mask_w, mask_h = mask_size
        scale_x = mask_w / image_w
        scale_y = mask_h / image_h
        left = min(s1.bbox.x1, s2.bbox.x1)

        x1 = self._clip(int(round((left - self.LEFT_MARGIN) * scale_x)), 0, mask_w)
        x2 = self._clip(int(round((left + self.RIGHT_MARGIN) * scale_x)), 0, mask_w)
        y1 = self._clip(int(round(s1.bbox.y2 * scale_y)), 0, mask_h)
        y2 = self._clip(int(round(s2.bbox.y1 * scale_y)), 0, mask_h)

        if x2 <= x1:
            x2 = min(mask_w, x1 + 1)
        if y2 <= y1:
            y2 = min(mask_h, y1 + 1)
        return x1, y1, x2, y2

    def _vertical_open_pixels(self, roi: np.ndarray) -> int:
        if roi.size == 0:
            return 0
        kernel_height = max(3, int(roi.shape[0] * self.VERTICAL_OPEN_HEIGHT_RATIO))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, kernel_height))
        opened = cv2.morphologyEx((roi * 255).astype(np.uint8), cv2.MORPH_OPEN, kernel)
        return int(cv2.countNonZero(opened))

    def _clip(self, value: int, lo: int, hi: int) -> int:
        return max(lo, min(hi, value))
