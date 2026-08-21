from copy import deepcopy

from tools.issue274.verify_two_homr_full68_counterfactual import (
    exact_serialized_signature,
    topology_signature,
)


def _page() -> dict:
    return {
        "page_number": 7,
        "width": 1000,
        "height": 1400,
        "systems": [
            {
                "staves": [{"bbox": [10, 100, 990, 200]}],
                "measures": [
                    {"number": 1, "bbox": [11, 100, 400, 200]},
                    {"number": 2, "bbox": [410, 100, 980, 200]},
                ],
            }
        ],
        "empty_systems": [
            {"staves": [{"bbox": [10, 300, 990, 400]}], "reason": "no_measures"}
        ],
    }


def test_counterfactual_topology_ignores_measure_boundary_jitter_but_exact_does_not() -> None:
    control = _page()
    candidate = deepcopy(control)
    candidate["page_number"] = 1
    candidate["systems"][0]["measures"][0]["bbox"][2] += 3
    candidate["systems"][0]["measures"][1]["bbox"][0] += 3

    assert topology_signature(control) == topology_signature(candidate)
    assert exact_serialized_signature(control) != exact_serialized_signature(candidate)


def test_counterfactual_topology_detects_staff_grouping_change() -> None:
    control = _page()
    candidate = deepcopy(control)
    candidate["systems"][0]["staves"].append({"bbox": [10, 220, 990, 320]})

    assert topology_signature(control) != topology_signature(candidate)


def test_counterfactual_topology_detects_measure_number_change() -> None:
    control = _page()
    candidate = deepcopy(control)
    candidate["systems"][0]["measures"][1]["number"] = 3

    assert topology_signature(control) != topology_signature(candidate)


def test_counterfactual_topology_detects_empty_system_change() -> None:
    control = _page()
    candidate = deepcopy(control)
    candidate["empty_systems"] = []

    assert topology_signature(control) != topology_signature(candidate)
