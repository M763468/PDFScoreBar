from typing import List, Dict, Optional
from .types import Staff, Barline, System

class SystemBuilder:
    """
    Groups staves into systems. 
    Currently exclusively relies on:
    1. Explicit `system_index` metdata.
    2. Fallback: Treating the entire page as a single system (safe default for single-system parts).
    """

    def build_systems(self, staves: List[Staff], barlines: List[Barline]) -> List[System]:
        """
        Main entry point.
        """
        if not staves:
            return []

        # Ensure staves are sorted by vertical position (y1)
        sorted_staves = sorted(staves, key=lambda s: s.bbox.y1)
        
        # Pre-assign barlines to staves (spatial join)
        self._assign_barlines_to_staves(sorted_staves, barlines)
        
        # Strategy 1: Explicit System Index (from homr or upstream)
        has_indices = any(s.system_index is not None and s.system_index >= 0 for s in sorted_staves)
        
        if has_indices:
             return self._group_by_index(sorted_staves)
        
        # Strategy 2: Simple Default (Fallback)
        # Without reliable geometric inference, we assume the page is a single system.
        # This is correct for parts, but wrong for full scores (which will need explicit indices).
        return [System(staves=sorted_staves)]

    def _group_by_index(self, staves: List[Staff]) -> List[System]:
        groups: Dict[int, List[Staff]] = {}
        orphan_counter = -1
        
        for s in staves:
            idx = s.system_index if (s.system_index is not None and s.system_index >= 0) else orphan_counter
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

    def _assign_barlines_to_staves(self, staves: List[Staff], barlines: List[Barline]):
        """
        Assigns barlines to staves based on vertical intersection.
        """
        for bar in barlines:
            for staff in staves:
                # Simple intersection check
                s_y1, s_y2 = staff.bbox.y1, staff.bbox.y2
                b_y1, b_y2 = bar.bbox.y1, bar.bbox.y2
                
                inter_y1 = max(s_y1, b_y1)
                inter_y2 = min(s_y2, b_y2)
                
                if inter_y2 > inter_y1:
                    overlap_h = inter_y2 - inter_y1
                    staff_h = s_y2 - s_y1
                    # Significant overlap
                    if overlap_h > staff_h * 0.5:
                        staff.barlines.append(bar)
