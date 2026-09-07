from __future__ import annotations

from tools.issue294.audit_full68_retained_semantics import _internal_x_compare


def _variant(*, first_x: int, internal_x: list[int], final_x: int, y1: int, y2: int):
    starts = [first_x, *internal_x]
    ends = [*internal_x, final_x]
    bboxes = [[left, y1, right, y2] for left, right in zip(starts, ends)]
    return {
        "numbering": {
            "pages": [
                {
                    "systems": [
                        {
                            "staff_count": 1,
                            "measure_count": len(bboxes),
                            "measure_numbers": list(range(1, len(bboxes) + 1)),
                            "measure_bboxes": bboxes,
                        }
                    ]
                }
            ]
        }
    }


def test_internal_x_compare_ignores_staff_derived_outer_geometry() -> None:
    a = _variant(first_x=10, internal_x=[100, 200], final_x=300, y1=20, y2=40)
    b = _variant(first_x=15, internal_x=[100, 200], final_x=320, y1=30, y2=60)

    comparison = _internal_x_compare(a, b)

    assert comparison["comparable"] is True
    assert comparison["boundary_count"] == 2
    assert comparison["exact"] is True
    assert comparison["changed_boundary_count"] == 0
    assert comparison["max_abs_delta"] == 0


def test_internal_x_compare_reports_only_internal_boundary_shift() -> None:
    a = _variant(first_x=10, internal_x=[100, 200], final_x=300, y1=20, y2=40)
    b = _variant(first_x=15, internal_x=[102, 200], final_x=320, y1=30, y2=60)

    comparison = _internal_x_compare(a, b)

    assert comparison["comparable"] is True
    assert comparison["exact"] is False
    assert comparison["changed_boundary_count"] == 1
    assert comparison["max_abs_delta"] == 2
    assert comparison["changed"] == [
        {"system": 0, "boundary": 0, "A_x": 100, "B_x": 102, "delta": 2}
    ]
