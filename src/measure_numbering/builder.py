from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .types import Barline, Staff, System


class SystemBuilder:
    """
    Groups staves into systems.

    Strategy order:
    1. Explicit `system_index` metadata.
    2. Geometric grouping with optional left/system-start connector evidence.
    """

    DIVISI_DIST_RATIO = 1.5
    CONNECTOR_RESCUE_DIST_RATIO = 1.56
    ALIGN_TOL = 10
    MIN_ALIGN_COUNT = 2
    CONNECTOR_RESCUE_MIN_ALIGN_COUNT = 3
    FALSE_MERGE_MAX_ALIGN_COUNT = 2
    CONNECTOR_DENSITY_THRESHOLD = 0.05

    def build_systems(
        self,
        staves: List[Staff],
        barlines: List[Barline],
        image: Optional[np.ndarray] = None,
        connector_evidence: Optional[Dict[Any, Any]] = None,
    ) -> List[System]:
        """Main entry point."""
        if not staves:
            return []

        sorted_staves = sorted(staves, key=lambda s: s.bbox.y1)
        self._assign_barlines_to_staves(sorted_staves, barlines)

        has_indices = any(s.system_index is not None and s.system_index >= 0 for s in sorted_staves)
        if has_indices:
            return self._group_by_index(sorted_staves)

        return self._group_by_geometry(sorted_staves, image, connector_evidence)

    def _group_by_index(self, staves: List[Staff]) -> List[System]:
        groups: Dict[int, List[Staff]] = {}
        orphan_counter = -1

        for s in staves:
            idx = (
                s.system_index
                if (s.system_index is not None and s.system_index >= 0)
                else orphan_counter
            )
            if idx == orphan_counter:
                orphan_counter -= 1

            if idx not in groups:
                groups[idx] = []
            groups[idx].append(s)

        systems = []
        for idx in groups:
            systems.append(System(staves=groups[idx]))

        systems.sort(key=lambda sys: sys.staves[0].bbox.y1)
        return systems

    def _group_by_geometry(
        self,
        staves: List[Staff],
        image: Optional[np.ndarray],
        connector_evidence: Optional[Dict[Any, Any]] = None,
    ) -> List[System]:
        if not staves:
            return []

        connector_by_pair = self._normalize_connector_evidence(connector_evidence)
        parent = list(range(len(staves)))

        def find(i):
            if parent[i] != i:
                parent[i] = find(parent[i])
            return parent[i]

        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_j] = root_i

        global_heights = [s.bbox.height for s in staves]
        avg_height = sum(global_heights) / len(global_heights) if global_heights else 100.0

        for i in range(len(staves) - 1):
            s1 = staves[i]
            s2 = staves[i + 1]

            gap = s2.bbox.y1 - s1.bbox.y2
            within_distance = gap <= avg_height * self.DIVISI_DIST_RATIO
            within_connector_rescue_distance = gap <= avg_height * self.CONNECTOR_RESCUE_DIST_RATIO

            aligned_pairs = self._find_aligned_pairs(s1, s2)
            pair_evidence = connector_by_pair.get((i, i + 1))
            has_explicit_connector_evidence = pair_evidence is not None
            left_connector_present = self._has_left_connector_evidence(pair_evidence)

            if not within_distance and not (
                left_connector_present and within_connector_rescue_distance
            ):
                continue

            if image is not None:
                aligned_connection = self._check_aligned_connection(s1, s2, aligned_pairs, image)
                if aligned_connection:
                    if (
                        has_explicit_connector_evidence
                        and not left_connector_present
                        and len(aligned_pairs) <= self.FALSE_MERGE_MAX_ALIGN_COUNT
                    ):
                        continue

                    if within_distance or (
                        left_connector_present
                        and within_connector_rescue_distance
                        and len(aligned_pairs) >= self.CONNECTOR_RESCUE_MIN_ALIGN_COUNT
                    ):
                        union(i, i + 1)
                        continue

            if image is None:
                if within_distance and len(aligned_pairs) >= self.MIN_ALIGN_COUNT:
                    union(i, i + 1)
                elif (
                    left_connector_present
                    and within_connector_rescue_distance
                    and len(aligned_pairs) >= self.CONNECTOR_RESCUE_MIN_ALIGN_COUNT
                ):
                    union(i, i + 1)

        groups: Dict[int, List[Staff]] = {}
        for i in range(len(staves)):
            root = find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(staves[i])

        systems = []
        sorted_roots = sorted(groups.keys(), key=lambda r: groups[r][0].bbox.y1)
        for root in sorted_roots:
            systems.append(System(staves=groups[root]))

        return systems

    def _find_aligned_pairs(self, s1: Staff, s2: Staff) -> List[Tuple[Barline, Barline]]:
        aligned_pairs: List[Tuple[Barline, Barline]] = []
        for b1 in s1.barlines:
            c1 = (b1.bbox.x1 + b1.bbox.x2) / 2
            for b2 in s2.barlines:
                c2 = (b2.bbox.x1 + b2.bbox.x2) / 2
                if abs(c1 - c2) <= self.ALIGN_TOL:
                    aligned_pairs.append((b1, b2))
        return aligned_pairs

    def _normalize_connector_evidence(
        self, connector_evidence: Optional[Dict[Any, Any]]
    ) -> Dict[Tuple[int, int], Any]:
        if not connector_evidence:
            return {}

        if isinstance(connector_evidence, dict) and "staff_pairs" in connector_evidence:
            result: Dict[Tuple[int, int], Any] = {}
            staff_pairs = connector_evidence.get("staff_pairs", [])
            if not isinstance(staff_pairs, list):
                return result
            for item in staff_pairs:
                if not isinstance(item, dict):
                    continue
                pair = self._parse_staff_pair(item.get("staff_pair"))
                if pair is not None:
                    result[pair] = item
            return result

        if isinstance(connector_evidence, dict):
            result = {}
            for key, value in connector_evidence.items():
                pair = self._parse_staff_pair(key)
                if pair is not None:
                    result[pair] = value
            return result

        return {}

    def _parse_staff_pair(self, value: Any) -> Optional[Tuple[int, int]]:
        try:
            if isinstance(value, (tuple, list)) and len(value) == 2:
                return int(value[0]), int(value[1])
            if isinstance(value, str):
                normalized = value.strip().strip("[]()")
                separator = "," if "," in normalized else "-" if "-" in normalized else None
                if separator is None:
                    return None
                parts = [p.strip() for p in normalized.split(separator)]
                if len(parts) != 2:
                    return None
                return int(parts[0]), int(parts[1])
        except (TypeError, ValueError):
            return None
        return None

    def _has_left_connector_evidence(self, evidence: Any) -> bool:
        if evidence is None:
            return False
        if isinstance(evidence, bool):
            return evidence
        if isinstance(evidence, (int, float)):
            return evidence > 0
        if not isinstance(evidence, dict):
            return False

        if "left_connector_present" in evidence:
            return bool(evidence["left_connector_present"])
        if "brace_or_bracket_present" in evidence:
            return bool(evidence["brace_or_bracket_present"])

        density_keys = (
            "symbols_vertical_open_density",
            "brace_dot_vertical_open_density",
            "symbols_density",
            "brace_dot_density",
        )
        for key in density_keys:
            value = evidence.get(key)
            if isinstance(value, (int, float)) and value >= self.CONNECTOR_DENSITY_THRESHOLD:
                return True
        return False

    def _check_aligned_connection(
        self, s1: Staff, s2: Staff, aligned_pairs: List[Tuple[Barline, Barline]], image: np.ndarray
    ) -> bool:
        if not aligned_pairs:
            return False

        y1_bot = int(s1.bbox.y2)
        y2_top = int(s2.bbox.y1)
        gap_h = y2_top - y1_bot

        if gap_h <= 0:
            return True

        if len(image.shape) == 3:
            import cv2

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, bin_img = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            import cv2

            _, bin_img = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        _h_img, w_img = bin_img.shape[:2]
        valid_connections = 0

        for b1, b2 in aligned_pairs:
            x1 = int(min(b1.bbox.x1, b2.bbox.x1))
            x2 = int(max(b1.bbox.x2, b2.bbox.x2))

            x1 = max(0, x1 - 2)
            x2 = min(w_img, x2 + 2)

            roi = bin_img[y1_bot:y2_top, x1:x2]

            if gap_h < 5:
                valid_connections += 1
                continue

            v_kernel_size = max(1, int(gap_h * 0.8))
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
            opened = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)

            if cv2.countNonZero(opened) > 0:
                valid_connections += 1

        return valid_connections >= 1

    def _assign_barlines_to_staves(self, staves: List[Staff], barlines: List[Barline]):
        for bar in barlines:
            for staff in staves:
                s_y1, s_y2 = staff.bbox.y1, staff.bbox.y2
                b_y1, b_y2 = bar.bbox.y1, bar.bbox.y2

                inter_y1 = max(s_y1, b_y1)
                inter_y2 = min(s_y2, b_y2)

                if inter_y2 > inter_y1:
                    overlap_h = inter_y2 - inter_y1
                    staff_h = s_y2 - s_y1
                    if overlap_h > staff_h * 0.2 or overlap_h > 10:
                        staff.barlines.append(bar)
