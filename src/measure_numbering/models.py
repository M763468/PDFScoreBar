from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class Barline:
    x: float
    type: str = "SINGLE"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Barline':
        return cls(
            x=data.get('x', 0.0),
            type=data.get('type', "SINGLE")
        )

@dataclass
class StaffSystem:
    index: int
    barlines: List[Barline] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StaffSystem':
        return cls(
            index=data.get('index', 0),
            barlines=[Barline.from_dict(b) for b in data.get('barlines', [])]
        )

@dataclass
class Page:
    index: int
    systems: List[StaffSystem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Page':
        return cls(
            index=data.get('index', 0),
            systems=[StaffSystem.from_dict(s) for s in data.get('systems', [])]
        )

@dataclass
class BarlineReference:
    page_index: int
    system_index: int
    barline_index: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BarlineReference':
        return cls(
            page_index=data.get('page_index', 0),
            system_index=data.get('system_index', 0),
            barline_index=data.get('barline_index', 0)
        )

@dataclass
class Measure:
    number: int
    start_barline_ref: Optional[BarlineReference] = None
    end_barline_ref: Optional[BarlineReference] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Measure':
        start_ref = data.get('start_barline_ref')
        end_ref = data.get('end_barline_ref')
        return cls(
            number=data.get('number', 0),
            start_barline_ref=BarlineReference.from_dict(start_ref) if start_ref else None,
            end_barline_ref=BarlineReference.from_dict(end_ref) if end_ref else None
        )

@dataclass
class ScoreInput:
    pages: List[Page] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScoreInput':
        return cls(
            pages=[Page.from_dict(p) for p in data.get('pages', [])]
        )

@dataclass
class MeasureOutput:
    measures: List[Measure] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MeasureOutput':
        return cls(
            measures=[Measure.from_dict(m) for m in data.get('measures', [])]
        )
