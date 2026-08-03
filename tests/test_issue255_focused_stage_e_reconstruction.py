from __future__ import annotations

import copy
from pathlib import Path

import yaml

from tools.issue255.run_focused_stage_e_reconstruction import (
    CONFIG,
    FRESH_CONTRACT,
    _effective,
    _first_loss,
    _fresh_sources,
    _layer,
)


def _trace(present: bool) -> dict[str, object]:
    return {"candidate_present": present}


def test_layer_reports_iou_and_x_distance() -> None:
    metrics = _layer(
        (100, 10, 104, 110),
        [(101, 10, 105, 110), (300, 10, 304, 110)],
    )

    assert metrics["candidate_present"] is True
    assert metrics["best_bbox"] == [101, 10, 105, 110]
    assert metrics["best_iou"] > 0.5
    assert metrics["x_center_distance"] == 1.0


def test_first_loss_follows_stage_e_order() -> None:
    layers = {
        "dense_raw_candidate": _trace(True),
        "clef_mask_filtering": _trace(True),
        "issue53_reconstruction": _trace(False),
        "cnn_scored": _trace(False),
        "cnn_accepted": _trace(False),
        "final_detector_output": _trace(False),
    }

    assert _first_loss(layers) == "issue53_reconstruction"


def test_first_loss_reports_recovered() -> None:
    layers = {
        "dense_raw_candidate": _trace(True),
        "clef_mask_filtering": _trace(True),
        "issue53_reconstruction": _trace(True),
        "cnn_scored": _trace(True),
        "cnn_accepted": _trace(True),
        "final_detector_output": _trace(True),
    }

    assert _first_loss(layers) == "recovered"


def test_effective_config_changes_only_run_fields(tmp_path) -> None:
    canonical = {
        "run": {"run_id": "canonical", "output_root": "logs/canonical"},
        "steps": {"detection": True},
        "detection": {"cnn_threshold": 0.1, "cnn_apply_nms": False},
    }
    before = copy.deepcopy(canonical)

    effective = _effective(canonical, "focused", tmp_path)

    assert canonical == before
    assert effective["detection"] == canonical["detection"]
    assert effective["steps"] == canonical["steps"]
    assert effective["run"]["run_id"] == "focused"
    assert effective["run"]["output_root"] == str(tmp_path.resolve())


def test_focused_config_enables_same_run_homr_debug_masks() -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    assert payload["detection"]["enable_debug"] is True


def test_fresh_sources_resolves_proxy_clef_debug_mask(tmp_path: Path) -> None:
    image = tmp_path / "page_004.png"
    image.touch()
    hybrid_root = tmp_path / "hybrid"
    baseline = hybrid_root / "baseline" / "batch" / image.stem
    sr = hybrid_root / "sr" / "batch" / image.stem
    omr = hybrid_root / "omr_sr" / image.stem
    consensus = hybrid_root / "hybrid_results"
    for directory in (baseline, sr, omr, consensus):
        directory.mkdir(parents=True, exist_ok=True)

    expected = {
        "baseline": baseline / f"{image.stem}_detections.json",
        "sr": sr / f"{image.stem}_detections.json",
        "omr": omr / "predictions.json",
        "hybrid": consensus / f"{image.stem}_hybrid.json",
        "staff_mask": baseline / f"{image.stem}_staff_mask.png",
        "clef_mask": baseline / f"{image.stem}_proxy_debug_7_clefs_keys.png",
    }
    for path in expected.values():
        path.touch()

    assert _fresh_sources(image, hybrid_root) == expected


def test_fresh_contract_has_no_candidate_override_keys() -> None:
    assert FRESH_CONTRACT == {
        "mode": "fresh_upstream",
        "fresh_upstream_authoritative": True,
        "override_keys": [],
    }
