"""Recover an open measure only when the original scan proves page clipping."""

from typing import List

import cv2
import numpy as np

from .types import Barline, BBox, System


class ClippedSystemEndDetector:
    # All distances use the extracted staff-line spacing in image coordinates.
    EDGE_STRIP_UNITS = 1.0
    CONTINUATION_STRIP_UNITS = 4.0
    MIN_TRAILING_WIDTH_UNITS = 4.0
    LINE_COVERAGE = 0.6
    MAX_LINE_THICKNESS_UNITS = 0.35
    MIN_LINE_SPACING_UNITS = 0.75
    MAX_LINE_SPACING_UNITS = 1.25
    MAX_LINE_SHIFT_UNITS = 0.5
    INK_THRESHOLD = 180
    MIN_SYMBOL_HEIGHT_UNITS = 0.5
    MIN_SYMBOL_WIDTH_UNITS = 0.4
    MIN_SYMBOL_AREA_UNITS = 0.25

    def apply(self, systems: List[System], image: np.ndarray) -> None:
        """Append a logical edge boundary after grouping, never a grouping cue.

        Staff masks can extend through blank page margins. Require five thin,
        regularly spaced lines in both the last staff space of the original
        scan and the preceding four spaces, plus non-line ink in the open tail.
        Unknown spacing, blank continuations and short post-bar regions abstain.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        ink = (gray < self.INK_THRESHOLD).astype(np.uint8)
        height, width = ink.shape
        for system in systems:
            bars = [bar for staff in system.staves for bar in staff.barlines]
            if not bars:
                continue
            last_x = max(bar.bbox.x2 for bar in bars)
            for staff in system.staves:
                unit = staff.unit_size
                if unit is None or not np.isfinite(unit) or unit <= 0:
                    continue
                if width - last_x < self.MIN_TRAILING_WIDTH_UNITS * unit:
                    continue
                if staff.bbox.x2 < width - unit:
                    continue
                top = max(0, staff.bbox.y1)
                bottom = min(height, staff.bbox.y2)
                edge_width = max(1, round(self.EDGE_STRIP_UNITS * unit))
                continuation_width = max(1, round(self.CONTINUATION_STRIP_UNITS * unit))
                edge_x = width - edge_width
                continuation_x = edge_x - continuation_width
                if continuation_x < last_x or bottom <= top:
                    continue
                edge = self._five_lines(ink[top:bottom, edge_x:width], unit)
                preceding = self._five_lines(ink[top:bottom, continuation_x:edge_x], unit)
                if edge is None or preceding is None:
                    continue
                if np.max(np.abs(edge - preceding)) > self.MAX_LINE_SHIFT_UNITS * unit:
                    continue
                # Limit musical evidence to the staff itself: a hairpin, caption
                # or page-border speck outside the five lines cannot qualify.
                y1 = top + int(min(edge[0], preceding[0]))
                y2 = top + int(max(edge[-1], preceding[-1])) + 1
                if not self._has_symbol(ink[y1:y2, max(0, last_x) : width], unit):
                    continue
                ghost = Barline(
                    bbox=BBox(
                        width,
                        min(s.bbox.y1 for s in system.staves),
                        width + 1,
                        max(s.bbox.y2 for s in system.staves),
                    ),
                    is_ghost=True,
                )
                staff.barlines.append(ghost)
                break

    def _five_lines(self, strip: np.ndarray, unit: float):
        if strip.size == 0:
            return None
        rows = np.flatnonzero(np.mean(strip, axis=1) >= self.LINE_COVERAGE)
        if not rows.size:
            return None
        runs = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)
        if len(runs) != 5 or any(len(run) > self.MAX_LINE_THICKNESS_UNITS * unit for run in runs):
            return None
        centers = np.array([(run[0] + run[-1]) / 2 for run in runs])
        spacing = np.diff(centers) / unit
        if np.any(spacing < self.MIN_LINE_SPACING_UNITS) or np.any(
            spacing > self.MAX_LINE_SPACING_UNITS
        ):
            return None
        return centers

    def _has_symbol(self, tail: np.ndarray, unit: float) -> bool:
        if tail.size == 0:
            return False
        # Remove persistent horizontal lines before looking for musical ink.
        kernel = np.ones((1, max(1, round(2 * unit))), np.uint8)
        lines = cv2.morphologyEx(tail, cv2.MORPH_OPEN, kernel)
        symbols = tail - lines
        count, _, stats, _ = cv2.connectedComponentsWithStats(symbols, connectivity=8)
        return any(
            stats[i, cv2.CC_STAT_HEIGHT] >= self.MIN_SYMBOL_HEIGHT_UNITS * unit
            and stats[i, cv2.CC_STAT_WIDTH] >= self.MIN_SYMBOL_WIDTH_UNITS * unit
            and stats[i, cv2.CC_STAT_AREA] >= self.MIN_SYMBOL_AREA_UNITS * unit * unit
            for i in range(1, count)
        )
