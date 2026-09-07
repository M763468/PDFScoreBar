from __future__ import annotations

from tools.issue264.phase_c_fixture_rebase import rebase_expected_overrides
from tools.issue294.rescore_full68_mmr_audit import (
    _score_overrides,
    _signature_to_numbering,
)


def test_signature_to_numbering_preserves_empty_system_indices() -> None:
    signature = {
        "pages": [
            {
                "systems": [
                    {
                        "staff_count": 1,
                        "measure_count": 0,
                        "measure_numbers": [],
                        "measure_bboxes": [],
                    },
                    {
                        "staff_count": 1,
                        "measure_count": 1,
                        "measure_numbers": [1],
                        "measure_bboxes": [[10, 20, 30, 40]],
                    },
                ]
            }
        ]
    }

    numbering = _signature_to_numbering(signature)

    assert numbering == {
        "pages": [
            {
                "systems": [
                    {"measures": []},
                    {"measures": [{"bbox": [10, 20, 30, 40]}]},
                ]
            }
        ]
    }


def test_geometry_rebase_repairs_direct_index_false_mismatch() -> None:
    historical_numbering = {
        "pages": [
            {
                "systems": [
                    {"measures": [{"bbox": [0, 0, 10, 10]}]},
                    {"measures": [{"bbox": [0, 20, 10, 30]}]},
                ]
            }
        ]
    }
    current_signature = {
        "pages": [
            {
                "systems": [
                    {
                        "staff_count": 1,
                        "measure_count": 1,
                        "measure_numbers": [1],
                        "measure_bboxes": [[0, 20, 10, 30]],
                    }
                ]
            }
        ]
    }
    current_numbering = _signature_to_numbering(current_signature)
    historical_expected = {
        "overrides": [{"page": 0, "system": 1, "measure": 0, "skip": 2}]
    }
    actual = {"overrides": [{"page": 0, "system": 0, "measure": 0, "skip": 2}]}

    direct = _score_overrides(historical_expected, actual)
    rebased, mappings = rebase_expected_overrides(
        historical_expected,
        historical_numbering,
        current_numbering,
        global_page_index=0,
    )
    rescored = _score_overrides(rebased, actual)

    assert direct["counts"] == {
        "expected": 1,
        "detected": 1,
        "matched_tp": 0,
        "missed_fn": 1,
        "skip_mismatch": 0,
        "unexpected_fp": 1,
    }
    assert rescored["counts"] == {
        "expected": 1,
        "detected": 1,
        "matched_tp": 1,
        "missed_fn": 0,
        "skip_mismatch": 0,
        "unexpected_fp": 0,
    }
    assert mappings[0]["historical_key"] == [0, 1, 0]
    assert mappings[0]["current_key"] == [0, 0, 0]
    assert mappings[0]["changed"] is True
