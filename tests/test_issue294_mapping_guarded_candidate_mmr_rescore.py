from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.measure_numbering.types import BBox, Measure
from tools.issue264.phase_c_fixture_rebase import rebase_expected_overrides
from tools.issue294.rescore_full68_mmr_audit import _score_overrides
from tools.issue294.rescore_mapping_guarded_candidate_mmr import (
    _assert_source_numbering_shape,
    _rebase_accepted_expected_to_candidate,
    _score_shape,
    _score_to_numbering,
)


def test_score_to_numbering_uses_serialized_mmr_system_indices() -> None:
    measure = Measure(number=1, start_bar=None, end_bar=None, bbox=BBox(10, 20, 30, 40))
    score = SimpleNamespace(
        pages=[
            SimpleNamespace(
                page_number=1,
                width=100,
                height=200,
                systems=[
                    SimpleNamespace(
                        staves=[SimpleNamespace(bbox=BBox(0, 0, 50, 10))],
                        measures=[],
                    ),
                    SimpleNamespace(
                        staves=[SimpleNamespace(bbox=BBox(0, 20, 50, 40))],
                        measures=[measure],
                    ),
                ],
            )
        ]
    )

    numbering = _score_to_numbering(score)
    assert numbering["pages"][0]["systems"] == [
        {
            "staves": [{"bbox": [0, 20, 50, 40]}],
            "measures": [{"number": 1, "bbox": [10, 20, 30, 40]}],
        }
    ]
    assert numbering["pages"][0]["empty_systems"] == [
        {
            "staves": [{"bbox": [0, 0, 50, 10]}],
            "reason": "no_measures",
        }
    ]
    assert _score_shape(score) == {
        "total_measures": 1,
        "system_staff_counts": [1],
        "system_measure_counts": [1],
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
    retained_actual = {"overrides": [{"page": 0, "system": 1, "measure": 0, "skip": 3}]}
    candidate_expected = {"overrides": [{"page": 0, "system": 0, "measure": 0, "skip": 3}]}

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


def test_accepted_issue264_anchor_rebases_without_historical_numbering_file() -> None:
    accepted_page = {
        "fixture_rebase": {
            "mappings": [
                {
                    "historical_key": [0, 2, 0],
                    "current_key": [0, 1, 0],
                    "current_bbox": [0, 20, 10, 30],
                    "skip": 3,
                    "coalesced_equivalent_fixture": False,
                }
            ]
        }
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

    rebased, mappings = _rebase_accepted_expected_to_candidate(
        accepted_page,
        candidate_numbering,
        global_page_index=0,
    )

    assert rebased == {"overrides": [{"page": 0, "system": 0, "measure": 0, "skip": 3}]}
    assert mappings[0]["source_historical_key"] == [0, 2, 0]
    assert mappings[0]["accepted_key"] == [0, 1, 0]
    assert mappings[0]["candidate_key"] == [0, 0, 0]
    assert mappings[0]["changed_from_accepted"] is True
    assert mappings[0]["accepted_bbox"] == [0.0, 20.0, 10.0, 30.0]
    assert mappings[0]["candidate_bbox"] == [0.0, 20.0, 10.0, 30.0]


def test_accepted_issue264_equivalent_source_items_remain_coalesced() -> None:
    accepted_page = {
        "fixture_rebase": {
            "mappings": [
                {
                    "historical_key": [0, 1, 0],
                    "current_key": [0, 0, 0],
                    "current_bbox": [0, 20, 10, 30],
                    "skip": 3,
                    "coalesced_equivalent_fixture": False,
                },
                {
                    "historical_key": [0, 2, 0],
                    "current_key": [0, 0, 0],
                    "current_bbox": [0, 20, 10, 30],
                    "skip": 3,
                    "coalesced_equivalent_fixture": True,
                },
            ]
        }
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

    rebased, mappings = _rebase_accepted_expected_to_candidate(
        accepted_page,
        candidate_numbering,
        global_page_index=0,
    )

    assert rebased == {"overrides": [{"page": 0, "system": 0, "measure": 0, "skip": 3}]}
    assert len(mappings) == 2
    assert mappings[0]["candidate_coalesced"] is False
    assert mappings[1]["accepted_source_coalesced"] is True
    assert mappings[1]["candidate_coalesced"] is True
    assert mappings[1]["candidate_coalesced_with_historical_key"] == [0, 1, 0]


def test_source_numbering_shape_accepts_completed_audit_geometry() -> None:
    source_page = {
        "page_id": "page_001",
        "total_measures": 3,
        "system_staff_counts": [1, 2],
        "system_measure_counts": [1, 2],
    }
    reconstructed = {
        "total_measures": 3,
        "system_staff_counts": [1, 2],
        "system_measure_counts": [1, 2],
    }

    _assert_source_numbering_shape(source_page, reconstructed)


def test_source_numbering_shape_rejects_wrong_geometry_contract() -> None:
    source_page = {
        "page_id": "page_001",
        "total_measures": 3,
        "system_staff_counts": [1, 2],
        "system_measure_counts": [1, 2],
    }
    reconstructed = {
        "total_measures": 3,
        "system_staff_counts": [1, 1, 1],
        "system_measure_counts": [1, 1, 1],
    }

    with pytest.raises(RuntimeError, match="page_001"):
        _assert_source_numbering_shape(source_page, reconstructed)
