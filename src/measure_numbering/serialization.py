"""Serialization helpers for measure numbering results."""

from __future__ import annotations


def _serialize_staves(staves):
    return [
        {"bbox": [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]}
        for staff in staves
    ]


def _serialize_measure(measure):
    return {
        "number": measure.number,
        "bbox": [measure.bbox.x1, measure.bbox.y1, measure.bbox.x2, measure.bbox.y2],
    }


def score_to_dict(score) -> dict:
    """Convert a Score object tree into the numbering JSON contract."""
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
                page_data["empty_systems"].append(
                    {"staves": staves, "reason": "no_measures"}
                )
                continue

            page_data["systems"].append(
                {
                    "staves": staves,
                    "measures": [
                        _serialize_measure(measure) for measure in system.measures
                    ],
                }
            )
        data["pages"].append(page_data)
    return data
