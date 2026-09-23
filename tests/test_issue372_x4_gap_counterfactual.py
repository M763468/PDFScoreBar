"""Focused tests for the Issue #372 retained x4-gap counterfactual policy."""

from argparse import Namespace
from pathlib import Path

import pytest

from experiments.issue372 import run_retained_x4_gap_counterfactual as counterfactual
from experiments.issue372.run_retained_x4_gap_counterfactual import (
    build_x4_gap_fallback,
)


def test_promotes_only_x4_boxes_without_baseline_iou_support() -> None:
    baseline = [
        [100, 100, 110, 200],
        [300, 100, 310, 200],
    ]
    x4 = [
        [101, 100, 111, 200],  # overlaps baseline[0], should not promote
        [200, 100, 210, 200],  # no baseline overlap, should promote
        [301, 100, 311, 200],  # overlaps baseline[1], should not promote
    ]
    current_hybrid = [[100, 100, 110, 200]]

    fallback, promoted = build_x4_gap_fallback(
        baseline_boxes=baseline,
        x4_boxes=x4,
        current_hybrid_boxes=current_hybrid,
    )

    assert promoted == [[200, 100, 210, 200]]
    assert fallback == [
        [100, 100, 110, 200],
        [200, 100, 210, 200],
    ]


def test_deduplicates_promoted_x4_boxes() -> None:
    fallback, promoted = build_x4_gap_fallback(
        baseline_boxes=[],
        x4_boxes=[
            [200, 100, 210, 200],
            [200, 100, 210, 200],
        ],
        current_hybrid_boxes=[],
    )

    assert promoted == [[200, 100, 210, 200]]
    assert fallback == [[200, 100, 210, 200]]


def test_missing_model_fails_before_output_root_is_created(
    tmp_path,
    monkeypatch,
) -> None:
    report = tmp_path / "report.json"
    report.write_text("{}")
    config = tmp_path / "config.yaml"
    config.write_text("placeholder")
    image_root = tmp_path / "images"
    gt_root = tmp_path / "gt"
    image_root.mkdir()
    gt_root.mkdir()
    staff_units = tmp_path / "staff_units.json"
    staff_units.write_text("{}")
    output_root = tmp_path / "run"

    monkeypatch.setattr(
        counterfactual,
        "_load_config",
        lambda _path: {
            "detection": {
                "detector_route": "dense_full_pipeline",
                "homr_profile": "maintained_original",
                "cnn_apply_nms": False,
                "cnn_model_manifest": "models/barline_cnn/manifest.json",
                "cnn_threshold": 0.4965248107910156,
            }
        },
    )

    class MissingModel(RuntimeError):
        pass

    def raise_missing(*_args, **_kwargs):
        raise MissingModel("model unavailable")

    monkeypatch.setattr(
        counterfactual,
        "_resolve_verified_cnn_artifact",
        raise_missing,
    )

    args = Namespace(
        issue43_report=report,
        issue43_repo_root=tmp_path,
        config=config,
        image_root=image_root,
        gt_root=gt_root,
        staff_units_json=staff_units,
        output_root=output_root,
    )

    with pytest.raises(MissingModel, match="model unavailable"):
        counterfactual.run(args)

    assert not output_root.exists()


def test_legacy_evaluation_args_do_not_mix_staff_units_with_fixed_xdist(
    tmp_path,
) -> None:
    args = counterfactual._evaluation_args(
        results_dir=tmp_path / "results",
        output_dir=tmp_path / "out",
        gt_root=tmp_path / "gt",
        image_root=tmp_path / "images",
        staff_units=tmp_path / "staff_units.json",
        threshold=0.4965248107910156,
        legacy=True,
    )

    assert args.legacy_fixed_12px is True
    assert args.staff_units_json is None


def test_current_evaluation_args_keep_staff_units(
    tmp_path,
) -> None:
    staff_units = tmp_path / "staff_units.json"
    args = counterfactual._evaluation_args(
        results_dir=tmp_path / "results",
        output_dir=tmp_path / "out",
        gt_root=tmp_path / "gt",
        image_root=tmp_path / "images",
        staff_units=staff_units,
        threshold=0.4965248107910156,
        legacy=False,
    )

    assert args.legacy_fixed_12px is False
    assert args.staff_units_json == str(staff_units)


def test_late_raw_x4_union_promotes_only_unrepresented_x4() -> None:
    from experiments.issue372.run_late_raw_x4_counterfactual import (
        build_late_raw_x4_union,
    )

    raw = [[10, 10, 14, 110], [100, 10, 104, 110]]
    x4 = [[10, 10, 14, 110], [200, 10, 204, 110]]

    union, promoted = build_late_raw_x4_union(
        raw_boxes=raw,
        x4_boxes=x4,
    )

    assert promoted == [[200, 10, 204, 110]]
    assert union == [
        [10, 10, 14, 110],
        [100, 10, 104, 110],
        [200, 10, 204, 110],
    ]


def test_late_raw_x4_union_deduplicates_promotions() -> None:
    from experiments.issue372.run_late_raw_x4_counterfactual import (
        build_late_raw_x4_union,
    )

    union, promoted = build_late_raw_x4_union(
        raw_boxes=[],
        x4_boxes=[[20, 10, 24, 110], [20, 10, 24, 110]],
    )

    assert promoted == [[20, 10, 24, 110]]
    assert union == [[20, 10, 24, 110]]


def test_page021_source_attribution_resolves_late_roots_from_retained_report(
    tmp_path: Path,
) -> None:
    import json

    from experiments.issue372.diagnose_page021_row_source_attribution import (
        _late_artifact_roots,
    )

    late_run = tmp_path / "late"
    raw = late_run / "raw_x4_injected"
    filtered = late_run / "filtered"
    probe = (
        late_run
        / "late_raw_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
    )
    for path in (raw, filtered, probe):
        path.mkdir(parents=True, exist_ok=True)

    report = {
        "late_raw_x4": {
            "raw_root": str(raw),
            "filtered_root": str(filtered),
            "aggregate_probe": str(probe),
        }
    }
    (late_run / "late_raw_x4_counterfactual_report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )

    roots = _late_artifact_roots(late_run)

    assert roots == {
        "raw": raw,
        "filtered": filtered,
        "probe": probe,
    }
