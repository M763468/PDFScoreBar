import json
from pathlib import Path

import pytest

from src.pipeline.steps.manual_corrections import (
    apply_mmr_measure_span_corrections,
    barline_construction_overrides,
    measure_construction_overrides,
    merge_barline_overrides,
    merge_measure_overrides,
    normalise_measure_overrides,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "manual_corrections"


def test_normalise_measure_overrides_accepts_legacy_and_current_keys():
    legacy = {"overrides": [{"page": "1", "system": "2", "measure": "3", "skip": "4"}]}
    current = {
        "measure_overrides": [{"page": "5", "system": "6", "measure": "7", "skip": "8"}]
    }

    assert normalise_measure_overrides(legacy) == [
        {"page": 1, "system": 2, "measure": 3, "skip": 4}
    ]
    assert normalise_measure_overrides(current) == [
        {"page": 5, "system": 6, "measure": 7, "skip": 8}
    ]


def test_normalise_measure_overrides_keeps_none_without_crashing():
    payload = {
        "overrides": [{"page": None, "system": "2", "measure": "3", "skip": None}]
    }

    assert normalise_measure_overrides(payload) == [
        {"page": None, "system": 2, "measure": 3, "skip": None}
    ]


def test_mmr_measure_span_corrections_suppress_and_set_span():
    auto_payload = {
        "measure_overrides": [
            {
                "page": 32,
                "system": 0,
                "measure": 0,
                "skip": 10,
                "comment": "auto unexpected detection",
            },
            {
                "page": 40,
                "system": 2,
                "measure": 1,
                "skip": 2,
                "comment": "auto keep",
            },
        ]
    }
    manual_payload = json.loads(
        (FIXTURE_DIR / "mmr_measure_span_basic.json").read_text()
    )

    merged = merge_measure_overrides(auto_payload, manual_payload)

    assert merged["measure_overrides"] == [
        {
            "page": 40,
            "system": 2,
            "measure": 1,
            "skip": 2,
            "comment": "auto keep",
        },
        {
            "page": 41,
            "system": 8,
            "measure": 0,
            "skip": 2,
            "comment": "synthetic explicit MMR measure span",
            "source": "manual:mmr_measure_span",
        },
    ]
    assert merged["overrides"] == merged["measure_overrides"]


def test_merge_measure_overrides_applies_manual_last_regardless_of_payload_order():
    auto_payload = {
        "measure_overrides": [
            {"page": 32, "system": 0, "measure": 0, "skip": 10},
            {"page": 40, "system": 2, "measure": 1, "skip": 2},
        ]
    }
    manual_payload = json.loads(
        (FIXTURE_DIR / "mmr_measure_span_basic.json").read_text()
    )

    auto_first = merge_measure_overrides(auto_payload, manual_payload)
    manual_first = merge_measure_overrides(manual_payload, auto_payload)

    assert manual_first == auto_first
    assert manual_first["measure_overrides"] == [
        {"page": 40, "system": 2, "measure": 1, "skip": 2},
        {
            "page": 41,
            "system": 8,
            "measure": 0,
            "skip": 2,
            "comment": "synthetic explicit MMR measure span",
            "source": "manual:mmr_measure_span",
        },
    ]


def test_mmr_suppress_matches_string_typed_existing_override_keys():
    auto_overrides = [{"page": "1", "system": "0", "measure": "0", "skip": "9"}]
    manual_payload = {
        "schema_version": 1,
        "correction_type": "mmr_measure_span",
        "items": [{"op": "suppress", "page": 1, "system": 0, "measure": 0}],
    }

    assert apply_mmr_measure_span_corrections(auto_overrides, manual_payload) == []


def test_mmr_set_measure_span_replaces_existing_override():
    auto_overrides = [{"page": 1, "system": 0, "measure": 0, "skip": 9}]
    manual_payload = {
        "schema_version": 1,
        "correction_type": "mmr_measure_span",
        "items": [
            {
                "op": "set_measure_span",
                "page": 1,
                "system": 0,
                "measure": 0,
                "measure_span": 4,
                "reason": "manual replacement",
            }
        ],
    }

    assert apply_mmr_measure_span_corrections(auto_overrides, manual_payload) == [
        {
            "page": 1,
            "system": 0,
            "measure": 0,
            "skip": 3,
            "comment": "manual replacement",
            "source": "manual:mmr_measure_span",
        }
    ]


def test_mmr_measure_span_must_be_at_least_one():
    with pytest.raises(ValueError, match="measure_span"):
        apply_mmr_measure_span_corrections(
            [],
            {
                "schema_version": 1,
                "correction_type": "mmr_measure_span",
                "items": [
                    {
                        "op": "set_measure_span",
                        "page": 0,
                        "system": 0,
                        "measure": 0,
                        "measure_span": 0,
                    }
                ],
            },
        )


def test_mmr_malformed_item_reports_descriptive_error():
    payload = {
        "schema_version": 1,
        "correction_type": "mmr_measure_span",
        "items": [{"op": "suppress", "page": 1, "system": 0}],
    }

    with pytest.raises(ValueError, match="page/system/measure"):
        apply_mmr_measure_span_corrections([], payload)


def test_measure_construction_force_measure_is_separate_from_future_grouping_ops():
    payload = {
        "schema_version": 1,
        "correction_type": "measure_construction",
        "items": [
            {
                "op": "force_measure",
                "page": 52,
                "system": 0,
                "interval": 0,
                "reason": "manual interval exception",
            },
            {
                "op": "group_staves_as_system",
                "page": 20,
                "staff_indices": [0, 1],
                "reason": "future divisi grouping correction shape",
            },
        ],
    }

    assert measure_construction_overrides(payload) == [
        {
            "page": 52,
            "system": 0,
            "measure": 0,
            "force_measure": True,
            "comment": "manual interval exception",
            "source": "manual:measure_construction",
        }
    ]
    assert merge_measure_overrides(payload)["measure_overrides"] == (
        measure_construction_overrides(payload)
    )


def test_measure_construction_malformed_item_reports_descriptive_error():
    payload = {
        "schema_version": 1,
        "correction_type": "measure_construction",
        "items": [{"op": "force_measure", "page": 52, "system": 0}],
    }

    with pytest.raises(ValueError, match="page/system/interval"):
        measure_construction_overrides(payload)


def test_barline_construction_add_and_remove_are_not_measure_overrides():
    payload = json.loads((FIXTURE_DIR / "barline_construction_basic.json").read_text())

    expected = [
        {
            "page": 12,
            "op": "add",
            "bbox": [100, 200, 104, 500],
            "comment": "synthetic missing detected barline",
            "source": "manual:barline_construction",
        },
        {
            "page": 12,
            "op": "remove",
            "bbox": [300, 200, 304, 500],
            "comment": "synthetic extra detected barline",
            "source": "manual:barline_construction",
        },
    ]

    assert barline_construction_overrides(payload) == expected
    assert merge_barline_overrides(payload) == {"barline_overrides": expected}
    assert merge_measure_overrides(payload)["measure_overrides"] == []
