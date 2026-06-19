from typing import Any, Dict, List, Optional

import numpy as np

from .builder import SystemBuilder as BaseSystemBuilder
from .types import Staff, System


class ConnectorAwareSystemBuilder(BaseSystemBuilder):
    """SystemBuilder variant that treats generated connector absence as a split signal."""

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

            if has_explicit_connector_evidence and not left_connector_present:
                continue

            if image is not None:
                aligned_connection = self._check_aligned_connection(s1, s2, aligned_pairs, image)
                if aligned_connection and within_distance:
                    union(i, i + 1)
                    continue

                if (
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
