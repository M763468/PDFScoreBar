from __future__ import annotations

from types import SimpleNamespace

from src.measure_numbering.types import BBox, Measure
from tools.issue264.phase_c_fixture_rebase import rebase_expected_overrides
from tools.issue294.rescore_full68_mmr_audit import _score_overrides
from tools.issue294.rescore_mapping_guarded_candidate_mmr import _score_to_numbering


def test_score_to_numbering_preserves_empty_system_indices() -> None:
    measure = Measure(number=1, start_bar=None, end_bar=None, bbox=BBox(10, 20, 30, 40))
    score = SimpleNamespace(
        pages=[
            SimpleNamespace(
                systems=[
                    SimpleNamespace(measures=[]),
                    SimpleNamespace(measures=[measure]),
                ]
            )
        ]
    )

    assert _score_to_numbering(score) == {
        "pages": [
            {
                "systems": [
                    {"measures": []},
                    {"measures": [{"bbox": [10, 20, 30, 40]}]},
                ]
            }
        ]
    }


def test_retained_actual_can_be_rebased_after_empty_system_is_removed() -> None:
    retained_numbering = {
        "pages": [
            {
                "systems": [
                    {"measures": []},
                    {"measures": [{"bbox": [0, 20, 10, 30]}]},
                ]
            }
        ]
    }
    candidate_numbering = {
        "pages": [
            {
                "systems": [
                    {"measures": [{"bbox": [0, 20, 10, 30]}]},
                ]
            }
        ]
    }
    retained_actual = {
        "overrides": [{"page": 0, "system": 1, "measure": 0, "skip": 3}]
    }
    candidate_expected = {
        "overrides": [{"page": 0, "system": 0, "measure": 0, "skip": 3}]
    }

    rebased_actual, mappings = rebase_expected_overrides(
        retained_actual,
        retained_numbering,
        candidate_numbering,
        global_page_index=0,
    )

    assert mappings[0]["historical_key"] == [0, 1, 0]
    assert mappings[0]["current_key"] == [0, 0, 0]
    assert mappings[0]["changed"] is True
    assert _score_overrides(candidate_expected, rebased_actual)["counts"] == {
        "expected": 1,
        "detected": 1,
        "matched_tp": 1,
        "missed_fn": 0,
        "skip_mismatch": 0,
        "unexpected_fp": 0,
    }
