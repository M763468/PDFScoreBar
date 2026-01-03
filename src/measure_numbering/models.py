"""
Measure Numbering Data Models

This module defines the data structures for the measure numbering system.
It includes models for the input score structure (Pages, Systems, Barlines)
and the output measure definitions.

These models correspond to the JSON schema defined in `docs/measure_numbering_schema.md`.
"""

from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

@dataclass
class Barline:
    """
    Represents a single barline in the score.
    """
    x: float
    type: str = "SINGLE"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Barline':
        """Creates a Barline instance from a dictionary."""
        return cls(
            x=data.get('x', 0.0),
            type=data.get('type', "SINGLE")
        )

@dataclass
class StaffSystem:
    """
    Represents a staff system on a page, containing a list of barlines.
    """
    index: int
    barlines: List[Barline] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StaffSystem':
        """Creates a StaffSystem instance from a dictionary."""
        return cls(
            index=data.get('index', 0),
            barlines=[Barline.from_dict(b) for b in data.get('barlines', [])]
        )

@dataclass
class Page:
    """
    Represents a page in the score, containing a list of staff systems.
    """
    index: int
    systems: List[StaffSystem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Page':
        """Creates a Page instance from a dictionary."""
        return cls(
            index=data.get('index', 0),
            systems=[StaffSystem.from_dict(s) for s in data.get('systems', [])]
        )

@dataclass
class BarlineReference:
    """
    A reference to a specific barline in the score hierarchy.
    Used to define the start and end points of a measure.
    """
    page_index: int
    system_index: int
    barline_index: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BarlineReference':
        """Creates a BarlineReference instance from a dictionary."""
        return cls(
            page_index=data.get('page_index', 0),
            system_index=data.get('system_index', 0),
            barline_index=data.get('barline_index', 0)
        )

@dataclass
class Measure:
    """
    Represents a musical measure with an assigned number and boundary references.
    """
    number: Union[int, str]
    start_barline_ref: Optional[BarlineReference] = None
    end_barline_ref: Optional[BarlineReference] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Measure':
        """Creates a Measure instance from a dictionary."""
        start_ref = data.get('start_barline_ref')
        end_ref = data.get('end_barline_ref')
        return cls(
            number=data.get('number', 0),
            start_barline_ref=BarlineReference.from_dict(start_ref) if start_ref else None,
            end_barline_ref=BarlineReference.from_dict(end_ref) if end_ref else None
        )

@dataclass
class ScoreInput:
    """
    Root object for the input schema, containing a list of pages.
    """
    pages: List[Page] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScoreInput':
        """Creates a ScoreInput instance from a dictionary."""
        return cls(
            pages=[Page.from_dict(p) for p in data.get('pages', [])]
        )

@dataclass
class MeasureOutput:
    """
    Root object for the output schema, containing a list of measures.
    """
    measures: List[Measure] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MeasureOutput':
        """Creates a MeasureOutput instance from a dictionary."""
        return cls(
            measures=[Measure.from_dict(m) for m in data.get('measures', [])]
        )

if __name__ == "__main__":
    # Example usage
    print("Running example usage for Measure Numbering Models...")

    # Simulate loading input JSON
    input_data = {
        "pages": [
            {
                "index": 0,
                "systems": [
                    {
                        "index": 0,
                        "barlines": [{"x": 100, "type": "SINGLE"}, {"x": 200, "type": "DOUBLE"}]
                    }
                ]
            }
        ]
    }
    score_input = ScoreInput.from_dict(input_data)
    print(f"Loaded ScoreInput with {len(score_input.pages)} page(s).")

    # Simulate loading output JSON
    output_data = {
        "measures": [
            {
                "number": 1,
                "start_barline_ref": {"page_index": 0, "system_index": 0, "barline_index": 0},
                "end_barline_ref": {"page_index": 0, "system_index": 0, "barline_index": 1}
            }
        ]
    }
    measure_output = MeasureOutput.from_dict(output_data)
    print(f"Loaded MeasureOutput with {len(measure_output.measures)} measure(s).")
    print(f"First measure number: {measure_output.measures[0].number}")
