from tools.issue294.run_mapping_guarded_mmr_visual_stability_probe import (
    SWEEP_FRACTIONS,
    primary_measure_causal,
    x1_offsets,
)


def test_primary_measure_causal_accepts_revert_evidence():
    record = {
        "classification": {
            "frozen_final_skip": 5,
            "native_final_skip": None,
            "reverting_primary_measure_restores_frozen": True,
            "primary_component_results": {},
        }
    }
    assert primary_measure_causal(record) is True


def test_primary_measure_causal_accepts_forward_component_isolation():
    record = {
        "classification": {
            "frozen_final_skip": 2,
            "native_final_skip": 10,
            "reverting_primary_measure_restores_frozen": False,
            "primary_component_results": {
                "primary_measure_native_only": 10,
                "primary_staff_native_only": 2,
            },
        }
    }
    assert primary_measure_causal(record) is True


def test_primary_measure_causal_rejects_fallback_only_delta():
    record = {
        "classification": {
            "frozen_final_skip": None,
            "native_final_skip": 6,
            "reverting_primary_measure_restores_frozen": False,
            "primary_component_results": {
                "primary_measure_native_only": None,
                "primary_staff_native_only": None,
            },
        }
    }
    assert primary_measure_causal(record) is False


def test_x1_offsets_are_symmetric_native_relative_and_width_scaled():
    offsets = x1_offsets(500)
    assert [item["fraction"] for item in offsets] == list(SWEEP_FRACTIONS)
    assert [item["dx1"] for item in offsets] == [-20, -10, -5, 0, 5, 10, 20]
    assert offsets[len(offsets) // 2] == {"fraction": 0.0, "dx1": 0}


def test_x1_offsets_reject_nonpositive_width():
    try:
        x1_offsets(0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
