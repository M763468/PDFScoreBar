from copy import deepcopy

import pytest

from tools.verification import verify_downstream_full68 as verifier


def _accepted_detector_report() -> dict:
    return {
        "status": "completed",
        "page_count": 68,
        "authoritative_full68": True,
        "historical_detector_target_met": True,
        "historical_detector_artifact_runtime_input": False,
        "detector_input_contract": {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": [],
        },
    }


def _connector_contract() -> dict:
    return {
        "source": "proxy_symbol_layers",
        "coordinate_space": "homr_segmentation_mask",
        "include_absent_pairs": True,
    }


def test_validate_detector_report_requires_authoritative_fresh_full68() -> None:
    report = _accepted_detector_report()
    verifier._validate_detector_report(report)

    historical = deepcopy(report)
    historical["detector_input_contract"]["mode"] = "historical_checkpoint"
    with pytest.raises(ValueError, match="fresh_upstream"):
        verifier._validate_detector_report(historical)

    overridden = deepcopy(report)
    overridden["detector_input_contract"]["override_keys"] = ["probe_candidates"]
    with pytest.raises(ValueError, match="runtime detector overrides"):
        verifier._validate_detector_report(overridden)


def test_focused_contract_accepts_known_issue254_structural_targets() -> None:
    pages = [
        {
            "selector": "Shostakovich-Sym5-Va/page_013",
            "global_page_number": 21,
            "membership": [2, 2, 2, 2, 2],
            "physical_measures_per_system": [6, 6, 5, 5, 5],
            "physical_measure_count": 27,
            "connector_evidence": _connector_contract(),
        },
        {
            "selector": "Shostakovich-Sym5-Va/page_014",
            "global_page_number": 22,
            "membership": [2, 2, 2, 2, 2],
            "physical_measure_count": 24,
            "connector_evidence": _connector_contract(),
        },
        {
            "selector": "Va_Prokofiev_Symphony1/page_004",
            "global_page_number": 45,
            "membership": [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1],
            "physical_measure_count": 101,
            "connector_evidence": _connector_contract(),
        },
    ]

    assert verifier._focused_contract_mismatches(pages) == {}


def test_focused_contract_reports_geometry_and_connector_mismatches() -> None:
    page = {
        "selector": "Shostakovich-Sym5-Va/page_014",
        "global_page_number": 22,
        "membership": [1, 1, 2, 2, 2, 2],
        "physical_measure_count": 23,
        "connector_evidence": {
            "source": "page_image_ink",
            "coordinate_space": "page_image",
            "include_absent_pairs": False,
        },
    }

    mismatches = verifier._focused_contract_mismatches([page])

    assert mismatches[page["selector"]]["membership"]["expected"] == [2, 2, 2, 2, 2]
    assert mismatches[page["selector"]]["physical_measure_count"] == {
        "expected": 24,
        "actual": 23,
    }
    assert mismatches[page["selector"]]["connector_evidence.source"] == {
        "expected": "proxy_symbol_layers",
        "actual": "page_image_ink",
    }


def test_row_starts_preserve_empty_systems_as_none() -> None:
    page = {
        "systems": [
            {"measures": [{"number": 1}, {"number": 2}]},
            {"measures": []},
            {"measures": [{"number": 9}]},
        ]
    }

    assert verifier._row_starts(page) == [1, None, 9]
