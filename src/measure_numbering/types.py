"""Measure numbering data records and their JSON serialization contract."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


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
    """Represents a vertical barline detected in the score."""

    bbox: BBox
    is_ghost: bool = (
        False  # If True, this is a logical marker (e.g. system start) not a detected line.
    )


@dataclass
class MeasureAttribute:
    """Manual override for a specific measure's behavior."""

    skip: int = 0  # Number of additional measures to skip (for multi-measure rests)
    set_number: Optional[int] = None  # Force a specific number
    comment: str = ""


@dataclass
class Measure:
    """
    Represents a musical measure.
    """

    number: int  # The computed measure number
    start_bar: Optional[Barline]  # None for the start of a system (implicit)
    end_bar: Optional[Barline]  # None for the end of a system (implicit) or open?
    bbox: BBox  # The bounding region of the measure on the staff
    attribute: Optional[MeasureAttribute] = None


@dataclass
class Staff:
    """
    Represents a single staff line (graphical entity) containing barlines and measures.
    """

    bbox: BBox
    barlines: List[Barline] = field(default_factory=list)

    # Metadata for system inference
    system_index: Optional[int] = None  # Explicit index from upstream (homr)
    bracket_group: Optional[int] = None  # ID of the bracket this staff belongs to

    # Staff-line spacing in the same coordinate frame as bbox/barlines.
    # Kept after the legacy fields so positional construction remains compatible.
    # Production extraction populates this from the staff mask when available.
    unit_size: Optional[float] = None


@dataclass
class System:
    """
    Represents a system of staves (e.g., Piano grand staff, or orchestral system).
    Measures in a system are vertically aligned across staves.
    """

    staves: List[Staff] = field(default_factory=list)
    measures: List[Measure] = field(default_factory=list)


@dataclass
class Page:
    systems: List[System] = field(default_factory=list)
    page_number: int = 1
    width: int = 0
    height: int = 0


@dataclass
class Score:
    pages: List[Page] = field(default_factory=list)


def _serialize_staves(staves):
    return [
        {"bbox": [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]} for staff in staves
    ]


def _serialize_measure(measure):
    return {
        "number": measure.number,
        "bbox": [measure.bbox.x1, measure.bbox.y1, measure.bbox.x2, measure.bbox.y2],
    }


def score_to_dict(score) -> dict:
    """Convert a Score object tree into the numbering JSON contract.

    ``systems`` contains only systems with measures, in Page.systems order.
    Its zero-based compact index is the identity used by MMR/manual overrides
    and movement boundaries. Empty systems have no address in that namespace.
    """
    data = {"pages": []}
    for page in score.pages:
        page_data = {
            "page_number": page.page_number,
            "width": page.width,
            "height": page.height,
            "systems": [],
            "empty_systems": [],
        }
        for system in page.systems:
            staves = _serialize_staves(system.staves)
            if not system.measures:
                page_data["empty_systems"].append({"staves": staves, "reason": "no_measures"})
                continue

            page_data["systems"].append(
                {
                    "staves": staves,
                    "measures": [_serialize_measure(measure) for measure in system.measures],
                }
            )
        data["pages"].append(page_data)
    return data
