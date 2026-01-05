from typing import List, Optional, Dict, Any
from .types import System, Measure, Score, Barline, Page, BBox, MeasureAttribute

class MeasureNumberer:
    """
    Assigns measure numbers to systems of music.
    """
    
    # Constants for logic thresholds
    DEDUPLICATION_THRESHOLD = 15 # px: merge barlines closer than this
    IMPLICIT_START_THRESHOLD = 50 # px: if first barline is > this from edge, assume hidden measure

    def number_score(self, score: Score, start_number: int = 1, overrides: Optional[List[Dict[str, Any]]] = None) -> int:
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
                sys_ov = {m_idx: ov for (p, s, m_idx), ov in ov_map.items() if p == p_idx and s == s_idx}
                current_number = self.number_system(system, current_number, overrides=sys_ov)
        
        return current_number

    def number_system(self, system: System, start_number: int, overrides: Optional[Dict[int, Any]] = None) -> int:
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
        sys_x2 = max(s.bbox.x2 for s in system.staves)
        sys_y1 = min(s.bbox.y1 for s in system.staves)
        sys_y2 = max(s.bbox.y2 for s in system.staves)

        # 3. Detect and insert Implicit Start if necessary
        if sorted_barlines:
            first_bar = sorted_barlines[0]
            if first_bar.bbox.x1 - sys_x1 > self.IMPLICIT_START_THRESHOLD:
                ghost_start = Barline(bbox=BBox(sys_x1, sys_y1, sys_x1 + 1, sys_y2), is_ghost=True)
                sorted_barlines.insert(0, ghost_start)
        
        # 4. Iterate intervals to create Measures
        current_number = start_number
        system.measures = []
        
        if not sorted_barlines:
            pass
        else:
            for i in range(len(sorted_barlines) - 1):
                left_bar = sorted_barlines[i]
                right_bar = sorted_barlines[i+1]
                
                # Check for overrides
                attr = None
                ov = overrides.get(i)
                if ov:
                    attr = MeasureAttribute(
                        skip=ov.get("skip", 0),
                        set_number=ov.get("set_number"),
                        comment=ov.get("comment", "")
                    )
                
                if attr and attr.set_number is not None:
                    current_number = attr.set_number

                # Create Measure
                m_x1 = left_bar.bbox.x2
                m_x2 = right_bar.bbox.x1
                
                measure = Measure(
                    number=current_number,
                    start_bar=left_bar,
                    end_bar=right_bar,
                    bbox=BBox(m_x1, sys_y1, m_x2, sys_y2),
                    attribute=attr
                )
                system.measures.append(measure)
                
                # Increment for next measure
                increment = 1 + (attr.skip if attr else 0)
                current_number += increment
                
        return current_number

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
