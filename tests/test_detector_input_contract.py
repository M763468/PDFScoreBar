import pytest

from src.pipeline.detection.input_contract import (
    FRESH_UPSTREAM_MODE,
    PRECOMPUTED_CANDIDATE_MODE,
    build_detector_input_contract,
    require_fresh_detector_input_contract,
)

OVERRIDE_KEYS = ("precomputed_probe_candidates_root", "cnn_bands_from")


def test_empty_detection_config_is_fresh_upstream() -> None:
    contract = build_detector_input_contract({})

    assert contract["mode"] == FRESH_UPSTREAM_MODE
    assert contract["fresh_upstream_authoritative"] is True
    assert contract["override_keys"] == []
    assert contract["hybrid_output_authoritative_for_probe"] is True
    assert contract["hybrid_output_authoritative_for_cnn_bands"] is True


@pytest.mark.parametrize("key", OVERRIDE_KEYS)
@pytest.mark.parametrize("value", [None, "", False])
def test_falsey_override_values_are_unset(key: str, value: object) -> None:
    contract = build_detector_input_contract({key: value})

    assert contract["mode"] == FRESH_UPSTREAM_MODE
    assert contract["fresh_upstream_authoritative"] is True
    assert contract["override_keys"] == []


@pytest.mark.parametrize("key", OVERRIDE_KEYS)
@pytest.mark.parametrize("value", ["   ", "logs/checkpoint/input"])
def test_truthy_path_strings_select_precomputed_route(key: str, value: str) -> None:
    contract = build_detector_input_contract({key: value})

    assert contract["mode"] == PRECOMPUTED_CANDIDATE_MODE
    assert contract["fresh_upstream_authoritative"] is False
    assert contract["override_keys"] == [key]


def test_precomputed_probe_candidates_make_route_checkpoint_only() -> None:
    contract = build_detector_input_contract(
        {"precomputed_probe_candidates_root": "logs/checkpoint/probe"}
    )

    assert contract["mode"] == PRECOMPUTED_CANDIDATE_MODE
    assert contract["fresh_upstream_authoritative"] is False
    assert contract["hybrid_output_authoritative_for_probe"] is False
    assert contract["override_keys"] == ["precomputed_probe_candidates_root"]


def test_cnn_bands_override_makes_route_checkpoint_only() -> None:
    contract = build_detector_input_contract({"cnn_bands_from": "logs/checkpoint/bands"})

    assert contract["mode"] == PRECOMPUTED_CANDIDATE_MODE
    assert contract["fresh_upstream_authoritative"] is False
    assert contract["hybrid_output_authoritative_for_cnn_bands"] is False
    assert contract["override_keys"] == ["cnn_bands_from"]


def test_fresh_guard_names_all_candidate_source_overrides() -> None:
    with pytest.raises(
        ValueError,
        match="precomputed_probe_candidates_root, cnn_bands_from",
    ):
        require_fresh_detector_input_contract(
            {
                "precomputed_probe_candidates_root": "logs/checkpoint/probe",
                "cnn_bands_from": "logs/checkpoint/bands",
            }
        )
