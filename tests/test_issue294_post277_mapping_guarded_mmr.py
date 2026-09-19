from tools.issue294.run_post277_mapping_guarded_mmr import (
    PRODUCTION_REFERENCE,
    candidate_not_worse,
    candidate_row_start_no_new_regression,
    focused_page_ids,
    production_acceptance_gates,
    production_reference_gates,
)


def _page(*, tp: int, fn: int, mismatch: int, fp: int) -> dict:
    return {
        "scoring": {
            "counts": {
                "matched_tp": tp,
                "missed_fn": fn,
                "skip_mismatch": mismatch,
                "unexpected_fp": fp,
            }
        }
    }


def _row_page(*, expected: list[dict], actual: list[dict]) -> dict:
    return {"expected": expected, "actual": actual}


def test_focused_set_covers_risk_grouping_and_issue277_controls() -> None:
    pages = set(focused_page_ids())
    assert {"page_013", "page_045", "page_066", "page_067"} <= pages
    assert {"page_025", "page_033", "page_042", "page_055"} <= pages
    assert "page_052" in pages
    assert {"page_001", "page_002", "page_022", "page_034"} <= pages


def test_candidate_not_worse_is_page_local_and_rejects_new_errors() -> None:
    baseline = _page(tp=3, fn=1, mismatch=1, fp=0)
    assert candidate_not_worse(baseline, _page(tp=4, fn=0, mismatch=1, fp=0))
    assert not candidate_not_worse(baseline, _page(tp=3, fn=2, mismatch=1, fp=0))
    assert not candidate_not_worse(baseline, _page(tp=4, fn=0, mismatch=0, fp=1))


def test_candidate_row_start_gate_is_relative_to_production_residual() -> None:
    expected = [{"page": 0, "system": 0, "measure": 0, "skip": 6}]
    production_residual = [{"page": 0, "system": 0, "measure": 0, "skip": 36}]
    assert candidate_row_start_no_new_regression(
        _row_page(expected=expected, actual=production_residual),
        _row_page(expected=expected, actual=production_residual),
    )


def test_candidate_row_start_gate_allows_repairing_production_residual() -> None:
    expected = [{"page": 0, "system": 0, "measure": 0, "skip": 6}]
    production_residual = [{"page": 0, "system": 0, "measure": 0, "skip": 36}]
    assert candidate_row_start_no_new_regression(
        _row_page(expected=expected, actual=production_residual),
        _row_page(expected=expected, actual=expected),
    )


def test_candidate_row_start_gate_rejects_new_error_key() -> None:
    expected = [{"page": 0, "system": 0, "measure": 0, "skip": 6}]
    production_residual = [{"page": 0, "system": 0, "measure": 0, "skip": 36}]
    candidate_with_new_key = production_residual + [
        {"page": 0, "system": 1, "measure": 0, "skip": 12}
    ]
    assert not candidate_row_start_no_new_regression(
        _row_page(expected=expected, actual=production_residual),
        _row_page(expected=expected, actual=candidate_with_new_key),
    )


def test_candidate_row_start_gate_rejects_changed_actual_skip() -> None:
    expected = [{"page": 0, "system": 0, "measure": 0, "skip": 6}]
    production_residual = [{"page": 0, "system": 0, "measure": 0, "skip": 36}]
    candidate_changed_skip = [{"page": 0, "system": 0, "measure": 0, "skip": 99}]
    assert not candidate_row_start_no_new_regression(
        _row_page(expected=expected, actual=production_residual),
        _row_page(expected=expected, actual=candidate_changed_skip),
    )


def test_candidate_row_start_gate_rejects_missing_to_wrong_number_change() -> None:
    expected = [{"page": 0, "system": 0, "measure": 0, "skip": 6}]
    production_missing = []
    candidate_wrong_number = [{"page": 0, "system": 0, "measure": 0, "skip": 99}]
    assert not candidate_row_start_no_new_regression(
        _row_page(expected=expected, actual=production_missing),
        _row_page(expected=expected, actual=candidate_wrong_number),
    )


def test_candidate_row_start_gate_rejects_new_error_on_production_correct_page() -> None:
    expected = [{"page": 0, "system": 0, "measure": 0, "skip": 6}]
    production_exact = [{"page": 0, "system": 0, "measure": 0, "skip": 6}]
    candidate_residual = [{"page": 0, "system": 0, "measure": 0, "skip": 36}]
    assert not candidate_row_start_no_new_regression(
        _row_page(expected=expected, actual=production_exact),
        _row_page(expected=expected, actual=candidate_residual),
    )


def test_production_reference_gate_requires_exact_merged_277_totals() -> None:
    assert all(production_reference_gates(PRODUCTION_REFERENCE).values())
    changed = dict(PRODUCTION_REFERENCE)
    changed["skip_mismatch"] += 1
    gates = production_reference_gates(changed)
    assert not gates["skip_mismatch"]
    assert all(value for key, value in gates.items() if key != "skip_mismatch")


def _variant_totals() -> dict:
    return {
        "expected": 177,
        "detected": 174,
        "matched_tp": 170,
        "missed_fn": 3,
        "skip_mismatch": 4,
        "unexpected_fp": 0,
        "zero_expected_pages": 16,
        "zero_expected_page_detections": 0,
    }


def _variant() -> dict:
    return {
        "totals": _variant_totals(),
        "gates": {
            "page_033_one_bar_veto": True,
            "page_042_five_overrides": True,
        },
    }


def test_production_acceptance_allows_equal_severity_page_error_redistribution() -> None:
    baseline = {"totals": _variant_totals()}
    candidate = _variant()

    gates = production_acceptance_gates(
        baseline,
        candidate,
        full68=True,
        b_c_actual_exact=True,
        b_c_shape_exact=True,
        required_shape_controls={
            "page_052_B_C_shape_exact": True,
            "page_067_B_C_shape_exact": True,
        },
    )

    assert all(gates.values())


def test_production_acceptance_rejects_aggregate_fp_regression() -> None:
    baseline = {"totals": _variant_totals()}
    candidate = _variant()
    candidate["totals"]["unexpected_fp"] = 1

    gates = production_acceptance_gates(
        baseline,
        candidate,
        full68=True,
        b_c_actual_exact=True,
        b_c_shape_exact=True,
        required_shape_controls={"page_067_B_C_shape_exact": True},
    )

    assert gates["aggregate_fp_not_above_production"] is False
    assert gates["candidate_unexpected_fp_zero"] is False


def test_production_acceptance_rejects_zero_fixture_pollution() -> None:
    baseline = {"totals": _variant_totals()}
    candidate = _variant()
    candidate["totals"]["zero_expected_page_detections"] = 1

    gates = production_acceptance_gates(
        baseline,
        candidate,
        full68=True,
        b_c_actual_exact=True,
        b_c_shape_exact=True,
        required_shape_controls={"page_067_B_C_shape_exact": True},
    )

    assert gates["candidate_zero_expected_page_detections_zero"] is False


def test_production_acceptance_rejects_required_topology_control_failure() -> None:
    baseline = {"totals": _variant_totals()}
    candidate = _variant()

    gates = production_acceptance_gates(
        baseline,
        candidate,
        full68=True,
        b_c_actual_exact=True,
        b_c_shape_exact=True,
        required_shape_controls={"page_067_B_C_shape_exact": False},
    )

    assert gates["page_067_B_C_shape_exact"] is False
