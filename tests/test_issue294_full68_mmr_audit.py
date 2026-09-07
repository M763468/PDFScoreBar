from __future__ import annotations

from tools.issue294.run_full68_mmr_audit import _compact, _row_start_semantic_equal


def test_compact_sorts_global_mmr_overrides() -> None:
    payload = {
        "measure_overrides": [
            {"page": 41, "system": 2, "measure": 0, "skip": 3, "comment": "x"},
            {"page": 32, "system": 0, "measure": 1, "skip": 7, "comment": "y"},
        ]
    }

    assert _compact(payload) == [
        {"page": 32, "system": 0, "measure": 1, "skip": 7},
        {"page": 41, "system": 2, "measure": 0, "skip": 3},
    ]


def test_row_start_semantics_require_exact_row_start_overrides() -> None:
    expected = {
        "overrides": [
            {"page": 41, "system": 2, "measure": 0, "skip": 3},
            {"page": 41, "system": 2, "measure": 4, "skip": 8},
        ]
    }
    same_row_start = {
        "measure_overrides": [
            {"page": 41, "system": 2, "measure": 0, "skip": 3},
            {"page": 41, "system": 9, "measure": 5, "skip": 2},
        ]
    }
    wrong_row_start = {
        "measure_overrides": [
            {"page": 41, "system": 2, "measure": 0, "skip": 4},
        ]
    }

    assert _row_start_semantic_equal(expected, same_row_start) is True
    assert _row_start_semantic_equal(expected, wrong_row_start) is False
