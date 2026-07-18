"""Classify whether detector candidates come from fresh upstream or overrides.

A run may execute HOMR/SR/OMR while still replacing the authoritative probe or
CNN inputs with precomputed artifacts.  Metrics from that route are useful as a
checkpoint, but they are not evidence that fresh upstream regeneration works.
This module keeps that distinction machine-readable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FRESH_UPSTREAM_MODE = "fresh_upstream"
PRECOMPUTED_CANDIDATE_MODE = "precomputed_candidate_route"
PRECOMPUTED_PROBE_KEY = "precomputed_probe_candidates_root"
CNN_BANDS_OVERRIDE_KEY = "cnn_bands_from"


def _configured(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def build_detector_input_contract(det_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Return the authoritative candidate-source contract for one detector run."""
    precomputed_probe = det_cfg.get(PRECOMPUTED_PROBE_KEY)
    cnn_bands_override = det_cfg.get(CNN_BANDS_OVERRIDE_KEY)
    uses_precomputed_probe = _configured(precomputed_probe)
    uses_cnn_bands_override = _configured(cnn_bands_override)
    fresh = not uses_precomputed_probe and not uses_cnn_bands_override

    return {
        "schema_version": "pipeline.detector_input_contract.v1",
        "mode": FRESH_UPSTREAM_MODE if fresh else PRECOMPUTED_CANDIDATE_MODE,
        "fresh_upstream_authoritative": fresh,
        "hybrid_detection_may_execute": True,
        "hybrid_output_authoritative_for_probe": not uses_precomputed_probe,
        "hybrid_output_authoritative_for_cnn_bands": not uses_cnn_bands_override,
        "precomputed_probe_candidates_root": (
            str(precomputed_probe) if uses_precomputed_probe else None
        ),
        "cnn_bands_from_override": (
            str(cnn_bands_override) if uses_cnn_bands_override else None
        ),
        "override_keys": [
            key
            for key, enabled in (
                (PRECOMPUTED_PROBE_KEY, uses_precomputed_probe),
                (CNN_BANDS_OVERRIDE_KEY, uses_cnn_bands_override),
            )
            if enabled
        ],
    }


def require_fresh_detector_input_contract(det_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Return the contract or reject a route that substitutes candidate inputs."""
    contract = build_detector_input_contract(det_cfg)
    if not contract["fresh_upstream_authoritative"]:
        keys = ", ".join(contract["override_keys"])
        raise ValueError(
            "Fresh detector validation rejects candidate-source overrides: "
            f"{keys}. A run that uses these keys is a checkpoint/precomputed route, "
            "even if HOMR/SR/OMR also execute."
        )
    return contract
