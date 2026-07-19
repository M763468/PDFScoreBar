import pytest

from tools.issue252.audit_grouped_semantic_impact import (
    _route_evidence,
    compare_grouped_final_numbering,
    normalize_isolated_mmr_overrides,
)

TARGET = (847, 2675, 854, 2776)


def _grouped_payload(*, lower_measure_end: int = 850, component_count: int = 2):
    components = [
        {"bbox": [100, 2470, 1600, 2605]},
        {"bbox": [100, 2660, 1600, 2790]},
        {"bbox": [100, 2840, 1600, 2970]},
    ][:component_count]
    return {
        "pages": [
            {
                "page_number": 45,
                "systems": [
                    {
                        "staves": components,
                        "measures": [
                            {
                                "number": 72,
                                "bbox": [
                                    100,
                                    components[0]["bbox"][1],
                                    lower_measure_end,
                                    components[-1]["bbox"][3],
                                ],
                            },
                            {
                                "number": 73,
                                "bbox": [
                                    lower_measure_end,
                                    components[0]["bbox"][1],
                                    1200,
                                    components[-1]["bbox"][3],
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }


def _connector_evidence(*, component_count: int = 2, positive: bool = True):
    return {
        "staff_pairs": [
            {
                "staff_pair": [index, index + 1],
                "left_connector_present": positive,
                "symbols": {"roi_xyxy": [40, 2600 + index * 180, 120, 2660 + index * 180]},
            }
            for index in range(component_count - 1)
        ]
    }


def _route(payload, connector, *, x_tolerance=12.0):
    return _route_evidence(
        payload,
        connector,
        page_number=45,
        target=TARGET,
        x_tolerance=x_tolerance,
    )


def test_connector_supported_grouping_classifies_redundant_component_instance():
    payload = _grouped_payload()
    connector = _connector_evidence()
    default = _route(payload, connector)
    candidate = _route(payload, connector)

    result = compare_grouped_final_numbering(
        default,
        candidate,
        connector_evidence_equal=True,
    )

    assert default["selected_membership"]["system_index"] == 0
    assert default["selected_membership"]["component_index"] == 1
    assert default["connector_supported_grouping"] is True
    assert default["target_boundary_matches"] == [{"x": 850, "distance": 0.5}]
    assert result["semantic_equal"] is True
    assert result["classification"] == "redundant_connector_grouped_component_fn"


def test_three_component_chain_is_supported_without_max_two_limit():
    payload = _grouped_payload(component_count=3)
    connector = _connector_evidence(component_count=3)
    default = _route(payload, connector)
    candidate = _route(payload, connector)

    result = compare_grouped_final_numbering(
        default,
        candidate,
        connector_evidence_equal=True,
    )

    assert default["owning_system"]["component_count"] == 3
    assert default["connector_supported_component_indices"] == [0, 1, 2]
    assert result["classification"] == "redundant_connector_grouped_component_fn"


def test_same_x_boundary_without_connector_support_is_not_grouping_evidence():
    payload = {
        "pages": [
            {
                "page_number": 45,
                "systems": [
                    {
                        "staves": [{"bbox": [100, 2470, 1600, 2605]}],
                        "measures": [
                            {"number": 72, "bbox": [100, 2470, 850, 2605]},
                            {"number": 73, "bbox": [850, 2470, 1200, 2605]},
                        ],
                    },
                    {
                        "staves": [{"bbox": [100, 2660, 1600, 2790]}],
                        "measures": [
                            {"number": 72, "bbox": [100, 2660, 850, 2790]},
                            {"number": 73, "bbox": [850, 2660, 1200, 2790]},
                        ],
                    },
                ],
            }
        ]
    }
    connector = _connector_evidence(positive=False)
    default = _route(payload, connector)
    candidate = _route(payload, connector)

    result = compare_grouped_final_numbering(
        default,
        candidate,
        connector_evidence_equal=True,
    )

    assert default["connector_supported_grouping"] is False
    assert result["classification"] == "default_grouping_not_connector_supported"
    assert result["semantic_equal"] is False


def test_grouped_audit_reports_local_target_boundary_recovery():
    connector = _connector_evidence()
    default = _route(_grouped_payload(lower_measure_end=900), connector)
    candidate = _route(_grouped_payload(), connector)

    result = compare_grouped_final_numbering(
        default,
        candidate,
        connector_evidence_equal=True,
    )

    assert default["target_boundary_matches"] == []
    assert candidate["target_boundary_matches"] == [{"x": 850, "distance": 0.5}]
    assert result["page_comparison"]["broad_geometry_change"] is False
    assert result["classification"] == "target_boundary_recovered_with_local_numbering_change"


def test_grouped_audit_reports_connector_evidence_change_first():
    default = _route(_grouped_payload(), _connector_evidence())
    candidate = _route(_grouped_payload(), _connector_evidence())

    result = compare_grouped_final_numbering(
        default,
        candidate,
        connector_evidence_equal=False,
    )

    assert result["classification"] == "connector_evidence_changed"
    assert result["semantic_equal"] is False


def test_isolated_mmr_overrides_are_remapped_to_local_page_index_zero():
    raw, normalized = normalize_isolated_mmr_overrides(
        {
            "measure_overrides": [
                {
                    "page": 44,
                    "system": 2,
                    "measure": 1,
                    "skip": 3,
                }
            ]
        },
        serialized_page_number=45,
    )

    assert raw[0]["page"] == 44
    assert normalized == [
        {
            "page": 0,
            "source_page": 44,
            "system": 2,
            "measure": 1,
            "skip": 3,
        }
    ]


def test_isolated_mmr_override_rejects_unexpected_page_key():
    with pytest.raises(ValueError, match="Unexpected MMR page key"):
        normalize_isolated_mmr_overrides(
            {"measure_overrides": [{"page": 0}]},
            serialized_page_number=45,
        )
