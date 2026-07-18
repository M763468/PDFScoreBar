import json
from argparse import Namespace
from pathlib import Path

from tools.issue245.trace_fresh_detector_layers import build_report, classify, layer_paths


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_layer_paths_resolves_score_scoped_probe_layout(tmp_path: Path) -> None:
    hybrid = tmp_path / "hybrid"
    probe = tmp_path / "probe"
    _write(
        hybrid / "baseline" / "batch" / "page_004" / "page_004_detections.json",
        [[10, 20, 14, 120]],
    )
    _write(
        probe
        / "eval2_Score_page_004"
        / "pipeline2_no_peak_candidates.json",
        [[10, 20, 14, 120]],
    )

    paths = layer_paths(
        hybrid_output_dir=hybrid,
        probe_output_root=probe,
        score="Score",
        page="page_004",
    )

    assert paths["baseline_homr"].name == "page_004_detections.json"
    assert paths["probe_candidates"].name == "pipeline2_no_peak_candidates.json"


def test_classify_identifies_hybrid_consensus_loss() -> None:
    layers = {
        "baseline_homr": {"accepted": True},
        "sr_homr": {"accepted": False},
        "omr_dln": {"accepted": False},
        "hybrid": {"accepted": False},
        "probe_candidates": {"accepted": False},
        "cnn_scored": {"accepted": False, "cnn_accepted": False},
    }

    assert classify(layers) == "lost_in_hybrid_consensus"


def test_build_report_tracks_target_through_saved_layers(tmp_path: Path) -> None:
    hybrid = tmp_path / "hybrid"
    probe = tmp_path / "probe"
    reference = [10, 20, 14, 120]
    for path in (
        hybrid / "baseline" / "batch" / "page_004" / "page_004_detections.json",
        hybrid / "sr" / "batch" / "page_004" / "page_004_detections.json",
        hybrid / "omr_sr" / "page_004" / "predictions.json",
        hybrid / "hybrid_results" / "page_004_hybrid.json",
        probe / "eval2_Score_page_004" / "pipeline2_no_peak_candidates.json",
    ):
        _write(path, [reference])
    _write(
        probe / "eval2_Score_page_004" / "pipeline2_no_peak_scored.json",
        [{"bbox": reference, "score": 0.9}],
    )
    args = Namespace(
        hybrid_output_dir=hybrid,
        probe_output_root=probe,
        score="Score",
        page="page_004",
        reference=reference,
        accepted_iou=0.5,
        x_tolerance=12.0,
        score_threshold=0.1,
    )

    report = build_report(args)

    assert report["classification"] == "accepted"
    assert report["layers"]["baseline_homr"]["best_match"]["iou"] == 1.0
    assert report["layers"]["cnn_scored"]["cnn_accepted"] is True
