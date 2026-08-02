from tools.issue255.first_loss_boundary import classify_first_loss_boundary


def _layer(accepted: bool):
    return {"accepted": accepted}


def _probe(**overrides):
    result = {
        "row_bands": [[10, 100]],
        "raw": _layer(True),
        "size_filtered": _layer(True),
        "heuristic_filtered": _layer(True),
        "trimmed": _layer(True),
        "final": _layer(True),
    }
    result.update(overrides)
    return result


def _classify(source, *, probe=None, scored=True, kept=True, final=False):
    return classify_first_loss_boundary(
        source_trace=source,
        probe_trace=probe or _probe(),
        cnn_scored=_layer(scored),
        cnn_accepted=_layer(kept),
        accepted_final=final,
    )


def test_classifies_absence_from_all_upstream_detectors_when_probe_does_not_recover() -> None:
    source = {
        "fresh_baseline": _layer(False),
        "current_sr": _layer(False),
        "current_omr": _layer(False),
        "hybrid": _layer(False),
    }

    assert _classify(source, probe=_probe(raw=_layer(False))) == (
        "absent_from_all_upstream_detectors"
    )


def test_classifies_hybrid_consensus_loss_when_probe_does_not_recover() -> None:
    source = {
        "fresh_baseline": _layer(True),
        "current_sr": _layer(False),
        "current_omr": _layer(False),
        "hybrid": _layer(False),
    }

    assert _classify(source, probe=_probe(raw=_layer(False))) == "hybrid_consensus"


def test_probe_recovery_moves_effective_loss_to_candidate_filter() -> None:
    source = {
        "fresh_baseline": _layer(False),
        "current_sr": _layer(False),
        "current_omr": _layer(False),
        "hybrid": _layer(False),
    }

    assert _classify(source, probe=_probe(heuristic_filtered=_layer(False))) == "candidate_filter"


def test_classifies_candidate_filter_and_cnn_filtering() -> None:
    source = {
        "fresh_baseline": _layer(True),
        "current_sr": _layer(True),
        "current_omr": _layer(False),
        "hybrid": _layer(True),
    }

    assert _classify(source, probe=_probe(heuristic_filtered=_layer(False))) == "candidate_filter"
    assert _classify(source, kept=False) == "cnn_filtering"


def test_inventory_entrypoint_installs_corrected_classifier() -> None:
    from tools.issue255 import run_focused_detector_inventory as entrypoint

    assert entrypoint.implementation._first_loss_boundary is classify_first_loss_boundary
