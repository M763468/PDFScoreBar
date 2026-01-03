from dataclasses import dataclass, field
from typing import List, Optional, Tuple, NewType
from enum import Enum

# Simple Bounding Box type: (x1, y1, x2, y2)
# Using a class for clarity, or just a tuple. Let's use a simple alias for now,
# but a dataclass is better for type safety and methods later.
@dataclass(unsafe_hash=True)
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1
    
    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

class BarlineType(Enum):
    SINGLE = "SINGLE"
    DOUBLE = "DOUBLE"
    END = "END"
    REPEAT_START = "REPEAT_START"
    REPEAT_END = "REPEAT_END"
    UNKNOWN = "UNKNOWN"

@dataclass(unsafe_hash=True)
class Barline:
    bbox: BBox
    type: BarlineType = BarlineType.SINGLE

@dataclass
class Measure:
    """
    Represents a musical measure.
    """
    number: int  # The computed measure number
    start_bar: Optional[Barline]  # None for the start of a system (implicit)
    end_bar: Optional[Barline]    # None for the end of a system (implicit) or open?
    bbox: BBox # The bounding region of the measure on the staff
    
    # We might want to link to the Staff it belongs to, but let's keep it simple tree for now.

@dataclass
class Staff:
    """
    Represents a single staff line (graphical entity) containing barlines and measures.
    """
    bbox: BBox
    barlines: List[Barline] = field(default_factory=list)
    
    # Metadata for system inference
    system_index: Optional[int] = None # Explicit index from upstream (homr)
    bracket_group: Optional[int] = None # ID of the bracket this staff belongs to

@dataclass
class System:
    """
    Represents a system of staves (e.g., Piano grand staff, or orchestral system).
    Measures in a system are vertically aligned across staves.
    """
    staves: List[Staff] = field(default_factory=list)
    measures: List[Measure] = field(default_factory=list) 
    # Note: Measures here might be "System Measures" which aggregate staff-measures, 
    # or we might just track the logical measure sequence.
    # For numbering, we primarily care about the sequence of measures.

@dataclass
class Page:
    systems: List[System] = field(default_factory=list)
    page_number: int = 1
    width: int = 0
    height: int = 0

@dataclass
class Score:
    pages: List[Page] = field(default_factory=list)
