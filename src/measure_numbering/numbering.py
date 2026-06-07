from typing import Any, Dict, List, Optional

from .types import Barline, BBox, Measure, MeasureAttribute, Score, System


class MeasureNumberer:
    """
    Assigns measure numbers to systems of music.
    """

    # Constants for logic thresholds
    DEDUPLICATION_THRESHOLD = 15  # px: merge barlines closer than this
    IMPLICIT_START_THRESHOLD = 50  # px: if first barline is > this from edge, assume hidden measure
    MIN_MEASURE_WIDTH = 25  # px: reject intervals narrower than this (e.g. double barlines)
    FIRST_GHOST_MEASURE_MAX_MEDIAN_RATIO = 0.5
    FIRST_GHOST_MEASURE_MAX_STAFF_HEIGHT_RATIO = 1.2

    def number_score(
        self, score: Score, start_number: int = 1, overrides: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """
        Numbers all pages and systems in a score sequentially.
        Returns the next available measure number.
        """
        current_number = start_number
        if not score.pages:
            return current_number

        # Map overrides by (page_index, system_index, measure_index) for fast lookup
        ov_map = {}
        if overrides:
            for ov in overrides:
                key = (ov.get("page"), ov.get("system"), ov.get("measure"))
                ov_map[key] = ov

        for p_idx, page in enumerate(score.pages):
            for s_idx, system in enumerate(page.systems):
                # Prepare system-specific overrides
                sys_ov = {
                    m_idx: ov for (p, s, m_idx), ov in ov_map.items() if p == p_idx and s == s_idx
                }
                current_number = self.number_system(system, current_number, overrides=sys_ov)

        return current_number

    def number_system(
        self, system: System, start_number: int, overrides: Optional[Dict[int, Any]] = None
    ) -> int:
        """
        Creates Measure objects for a single system and assigns numbers.
        Returns the next start number.
        """
        if not system.staves:
            return start_number

        overrides = overrides or {}

        # 1. Collect and Deduplicate barlines in the system
        all_barlines = set()
        for staff in system.staves:
            all_barlines.update(staff.barlines)

        raw_sorted = sorted(list(all_barlines), key=lambda b: b.bbox.x1)
        sorted_barlines = self._deduplicate_barlines(raw_sorted)

        # 2. System and Staff geometry
        sys_x1 = min(s.bbox.x1 for s in system.staves)
        max(s.bbox.x2 for s in system.staves)
        sys_y1 = min(s.bbox.y1 for s in system.staves)
        sys_y2 = max(s.bbox.y2 for s in system.staves)
        avg_staff_height = sum(s.bbox.height for s in system.staves) / len(system.staves)

        # 3. Detect and insert Implicit Start if necessary
        if sorted_barlines:
            first_bar = sorted_barlines[0]
            if first_bar.bbox.x1 - sys_x1 > self.IMPLICIT_START_THRESHOLD:
                ghost_start = Barline(bbox=BBox(sys_x1, sys_y1, sys_x1 + 1, sys_y2), is_ghost=True)
                sorted_barlines.insert(0, ghost_start)

        interval_widths = self._measure_interval_widths(sorted_barlines)
        median_widths = (
            interval_widths[1:]
            if sorted_barlines and sorted_barlines[0].is_ghost
            else interval_widths
        )
        median_interval_width = self._median(median_widths)

        # 4. Iterate intervals to create Measures
        current_number = start_number
        system.measures = []

        if not sorted_barlines:
            pass
        else:
            for i in range(len(sorted_barlines) - 1):
                left_bar = sorted_barlines[i]
                right_bar = sorted_barlines[i + 1]

                m_x1 = left_bar.bbox.x2
                m_x2 = right_bar.bbox.x1
                measure_width = m_x2 - m_x1

                # Check for insufficient width (e.g. double barline gap)
                if measure_width < self.MIN_MEASURE_WIDTH:
                    continue

                # Override keys are visible measure indices, not raw barline-interval
                # indices. An explicit override also means the first interval is a
                # deliberate measure and must not be filtered by the ghost-start guard.
                visible_measure_idx = len(system.measures)
                ov = overrides.get(visible_measure_idx)

                if ov is None and self._is_narrow_ghost_start_interval(
                    i=i,
                    left_bar=left_bar,
                    measure_width=measure_width,
                    median_interval_width=median_interval_width,
                    avg_staff_height=avg_staff_height,
                ):
                    continue

                attr = None
                if ov:
                    attr = MeasureAttribute(
                        skip=ov.get("skip", 0),
                        set_number=ov.get("set_number"),
                        comment=ov.get("comment", ""),
                    )

                if attr and attr.set_number is not None:
                    current_number = attr.set_number

                # Create Measure
                measure = Measure(
                    number=current_number,
                    start_bar=left_bar,
                    end_bar=right_bar,
                    bbox=BBox(m_x1, sys_y1, m_x2, sys_y2),
                    attribute=attr,
                )
                system.measures.append(measure)

                # Increment for next measure
                increment = 1 + (attr.skip if attr else 0)
                current_number += increment

        return current_number

    def _is_narrow_ghost_start_interval(
        self,
        *,
        i: int,
        left_bar: Barline,
        measure_width: float,
        median_interval_width: Optional[float],
        avg_staff_height: float,
    ) -> bool:
        """Return true for a short non-measure region after an implicit system start."""
        if i != 0 or not left_bar.is_ghost or median_interval_width is None:
            return False
        return (
            measure_width < median_interval_width * self.FIRST_GHOST_MEASURE_MAX_MEDIAN_RATIO
            and measure_width < avg_staff_height * self.FIRST_GHOST_MEASURE_MAX_STAFF_HEIGHT_RATIO
        )

    def _measure_interval_widths(self, barlines: List[Barline]) -> List[float]:
        widths = []
        for left_bar, right_bar in zip(barlines, barlines[1:]):
            width = right_bar.bbox.x1 - left_bar.bbox.x2
            if width >= self.MIN_MEASURE_WIDTH:
                widths.append(width)
        return widths

    def _median(self, values: List[float]) -> Optional[float]:
        if not values:
            return None
        sorted_values = sorted(values)
        midpoint = len(sorted_values) // 2
        if len(sorted_values) % 2:
            return sorted_values[midpoint]
        return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2

    def _deduplicate_barlines(self, barlines: List[Barline]) -> List[Barline]:
        """
        Merges barlines that are too close to each other.
        """
        if not barlines:
            return []

        deduped = []
        if barlines:
            current = barlines[0]
            for next_bar in barlines[1:]:
                # Distance check (center to center or x1 to x1)
                dist = abs(next_bar.bbox.x1 - current.bbox.x1)
                if dist < self.DEDUPLICATION_THRESHOLD:
                    # Merge: keep the one that is wider or just the first?
                    # Usually detector produces multiple thin candidates.
                    continue
                else:
                    deduped.append(current)
                    current = next_bar
            deduped.append(current)

        return deduped
