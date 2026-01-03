from typing import List, Optional
from .types import System, Measure, Score, Barline, Page

class MeasureNumberer:
    """
    Assigns measure numbers to systems of music.
    """

    def number_score(self, score: Score, start_number: int = 1) -> int:
        """
        Numbers all pages and systems in a score sequentially.
        Returns the next available measure number.
        """
        current_number = start_number
        if not score.pages:
            return current_number

        for page in score.pages:
            for system in page.systems:
                current_number = self.number_system(system, current_number)
        
        return current_number

    def number_system(self, system: System, start_number: int) -> int:
        """
        Creates Measure objects for a single system and assigns numbers.
        Returns the next start number.
        """
        if not system.staves:
            return start_number

        # 1. Collect all unique barlines in the system
        # Merge barlines from all staves. 
        # Since we might have duplicates (same barline object ref), set logic helps.
        # But we also need to handle distinct barline objects that are spatially same? 
        # (Assuming builder or detector simplified this. For now, we trust object identity or X-pos)
        
        all_barlines = set()
        for staff in system.staves:
            all_barlines.update(staff.barlines)
            
        sorted_barlines = sorted(list(all_barlines), key=lambda b: b.bbox.x1)
        
        # 2. Iterate intervals to create Measures
        # Logic: Space between Barline i and Barline i+1 is a Measure.
        # What about Pickup bars? (Before first barline) -> Not handled in "Basic" logic yet.
        # What about End? (After last barline) -> Usually implies empty space or end.
        
        current_number = start_number
        system.measures = []
        
        # If no barlines, the whole system might be 1 measure? Or 0?
        if not sorted_barlines:
            # Degenerate case using system width?
            pass
        else:
            # Check for pickup: Space before first barline?
            # Requires Staff X-start info which we rely on BBox for.
            # Assume strict barline-to-barline for now.
            
            for i in range(len(sorted_barlines) - 1):
                left_bar = sorted_barlines[i]
                right_bar = sorted_barlines[i+1]
                
                # Create Measure
                # Bounding box is implied by the system's vertical extent and barlines' X.
                # Union of staves Y?
                sys_y1 = min(s.bbox.y1 for s in system.staves)
                sys_y2 = max(s.bbox.y2 for s in system.staves)
                
                # Measure count increments
                # (Future: Check for multi-measure rests logic here)
                
                measure = Measure(
                    number=current_number,
                    start_bar=left_bar,
                    end_bar=right_bar,
                    # Approximate bbox
                    bbox=None # TBD
                )
                system.measures.append(measure)
                current_number += 1
                
        return current_number
