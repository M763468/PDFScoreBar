#!/usr/bin/env python3
"""Run a retained full68 x4-fallback counterfactual for Issue #372.

No HOMR, SR, or OMR-DLN inference is executed. The runner reuses the exact
Issue #43 retained current-production upstream inventories and varies only the
hybrid artifact handed to the dense detector route.

Control:
    current retained hybrid_predictions

Counterfactual:
    current hybrid_predictions
    + current-x4 HOMR boxes that have no baseline HOMR box with IoU > 0.5

The counterfactual deliberately mirrors the existing asymmetric hybrid
contract: it only fills baseline-authority gaps. It does not change CNN model,
threshold, NMS, candidate filters, staff/clef masks, images, or GT.

Dense/probe reconstruction and D27 CNN scoring are run fresh for both variants
so their delta is causal under one execution environment.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import time
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common import barline_iou
from src.pipeline.detection.restored_orchestrator import _resolve_verified_cnn_artifact
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

IOU_THRESHOLD = 0.5
EXPECTED_PAGES = 68


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _host_path(value: str | Path, repo_root: Path) -> Path:
    path = Path(value)
    try:
        return repo_root / path.relative_to("/workspace")
    except ValueError:
        return path


def _load_config(path: Path) -> dict[str, Any]:
    from src.pipeline.core.config import load_yaml

    config = load_yaml(path)
    if not isinstance(config, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    detection = config.get("detection")
    if not isinstance(detection, dict):
        raise ValueError(f"Config lacks detection mapping: {path}")
    if detection.get("detector_route") != "dense_full_pipeline":
        raise ValueError("Issue #372 counterfactual requires dense_full_pipeline")
    if detection.get("homr_profile") != "maintained_original":
        raise ValueError(
            "Issue #372 counterfactual requires current production "
            f"homr_profile=maintained_original, got {detection.get('homr_profile')!r}"
        )
    if detection.get("cnn_apply_nms") is not False:
        raise ValueError("Issue #372 counterfactual requires cnn_apply_nms=false")
    return config


def _source_worker_result(
    hybrid_path: Path,
    *,
    score: str,
    page: str,
) -> Path:
    if hybrid_path.parent.name != "hybrid_results":
        raise ValueError(f"Unexpected hybrid path: {hybrid_path}")
    root = hybrid_path.parent.parent / "source_page_workers"
    direct = root / score / page / "result.json"
    if direct.is_file():
        return direct
    hits = sorted(root.rglob(f"{score}/{page}/result.json")) if root.is_dir() else []
    if len(hits) == 1:
        return hits[0]
    raise FileNotFoundError(
        f"Unable to resolve source worker result for {score}/{page} under {root}; "
        f"matches={len(hits)}"
    )


def _baseline_detection(record: Mapping[str, Any], source_repo_root: Path) -> Path:
    run_dir_raw = record.get("run_dir")
    if not run_dir_raw:
        raise ValueError(f"Inventory record lacks run_dir: {record}")
    run_dir = _host_path(str(run_dir_raw), source_repo_root)
    image = Path(str(record.get("image", "")))
    expected = run_dir / f"{image.stem}_detections.json"
    if expected.is_file():
        return expected
    hits = sorted(run_dir.glob("*_detections.json")) if run_dir.is_dir() else []
    if len(hits) == 1:
        return hits[0]
    raise FileNotFoundError(
        f"Unable to resolve baseline detection under {run_dir}; matches={len(hits)}"
    )


def _x4_detection(
    record: Mapping[str, Any],
    *,
    score: str,
    page: str,
    source_repo_root: Path,
) -> Path:
    hybrid_raw = record.get("hybrid_predictions")
    if not hybrid_raw:
        raise ValueError(f"Inventory record lacks hybrid_predictions: {record}")
    hybrid = _host_path(str(hybrid_raw), source_repo_root)
    result_path = _source_worker_result(hybrid, score=score, page=page)
    payload = _load_json(result_path)
    if not isinstance(payload, Mapping) or not payload.get("current_sr_detection"):
        raise ValueError(f"Source worker lacks current_sr_detection: {result_path}")
    path = _host_path(str(payload["current_sr_detection"]), source_repo_root)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _current_hybrid(record: Mapping[str, Any], source_repo_root: Path) -> Path:
    raw = record.get("hybrid_predictions")
    if not raw:
        raise ValueError(f"Inventory record lacks hybrid_predictions: {record}")
    path = _host_path(str(raw), source_repo_root)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _dedup_boxes(boxes: Sequence[Sequence[int]]) -> list[list[int]]:
    seen: set[tuple[int, int, int, int]] = set()
    result: list[list[int]] = []
    for raw in boxes:
        box = tuple(int(v) for v in raw[:4])
        if box in seen:
            continue
        seen.add(box)
        result.append(list(box))
    return result


def build_x4_gap_fallback(
    *,
    baseline_boxes: Sequence[Sequence[int]],
    x4_boxes: Sequence[Sequence[int]],
    current_hybrid_boxes: Sequence[Sequence[int]],
    iou_threshold: float = IOU_THRESHOLD,
) -> tuple[list[list[int]], list[list[int]]]:
    """Promote only x4 boxes with no matching baseline-authority box."""

    promoted = [
        [int(v) for v in x4]
        for x4 in x4_boxes
        if not any(barline_iou(x4, baseline) > iou_threshold for baseline in baseline_boxes)
    ]
    fallback_hybrid = _dedup_boxes([*current_hybrid_boxes, *promoted])
    return fallback_hybrid, _dedup_boxes(promoted)


def _materialize_inventories(
    *,
    issue43_report: Mapping[str, Any],
    source_repo_root: Path,
    image_root: Path,
    output_root: Path,
) -> tuple[dict[str, Path], dict[str, Path], list[dict[str, Any]]]:
    provenance = issue43_report.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("Issue #43 report lacks provenance")
    groups = provenance.get("upstream_groups")
    if not isinstance(groups, list):
        raise ValueError("Issue #43 report lacks provenance.upstream_groups")

    control_paths: dict[str, Path] = {}
    fallback_paths: dict[str, Path] = {}
    promotion_rows: list[dict[str, Any]] = []
    page_count = 0

    for group in groups:
        if not isinstance(group, Mapping) or not group.get("inventory"):
            continue
        score = str(group.get("score"))
        source_inventory = _host_path(str(group["inventory"]), source_repo_root)
        payload = _load_json(source_inventory)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
            raise ValueError(f"Invalid inventory: {source_inventory}")

        control_records: list[dict[str, Any]] = []
        fallback_records: list[dict[str, Any]] = []

        for raw_record in payload["records"]:
            if not isinstance(raw_record, Mapping):
                raise ValueError(f"Invalid inventory record: {raw_record!r}")
            record = dict(raw_record)
            page = str(record["page"])
            canonical_image = image_root / score / f"{page}.png"
            if not canonical_image.is_file():
                raise FileNotFoundError(canonical_image)

            hybrid = _current_hybrid(record, source_repo_root)
            baseline = _baseline_detection(record, source_repo_root)
            x4 = _x4_detection(
                record,
                score=score,
                page=page,
                source_repo_root=source_repo_root,
            )
            staff_mask = _host_path(str(record["staff_mask"]), source_repo_root)
            clef_mask = _host_path(str(record["clef_mask"]), source_repo_root)
            run_dir = _host_path(str(record["run_dir"]), source_repo_root)
            for required in (staff_mask, clef_mask, run_dir):
                if not required.exists():
                    raise FileNotFoundError(required)

            baseline_boxes = load_json_boxes(baseline)
            x4_boxes = load_json_boxes(x4)
            current_hybrid_boxes = load_json_boxes(hybrid)
            fallback_boxes, promoted = build_x4_gap_fallback(
                baseline_boxes=baseline_boxes,
                x4_boxes=x4_boxes,
                current_hybrid_boxes=current_hybrid_boxes,
            )

            override = output_root / "hybrid_overrides" / score / f"{page}_hybrid.json"
            _write_json(override, fallback_boxes)

            common = {
                **record,
                "score": score,
                "page": page,
                "image": str(canonical_image.resolve()),
                "staff_mask": str(staff_mask.resolve()),
                "clef_mask": str(clef_mask.resolve()),
                "run_dir": str(run_dir.resolve()),
            }
            control_records.append(
                {
                    **common,
                    "hybrid_predictions": str(hybrid.resolve()),
                }
            )
            fallback_records.append(
                {
                    **common,
                    "hybrid_predictions": str(override.resolve()),
                }
            )
            promotion_rows.append(
                {
                    "score": score,
                    "page": page,
                    "baseline_count": len(baseline_boxes),
                    "x4_count": len(x4_boxes),
                    "current_hybrid_count": len(current_hybrid_boxes),
                    "promoted_x4_gap_count": len(promoted),
                    "fallback_hybrid_count": len(fallback_boxes),
                    "baseline": str(baseline),
                    "x4": str(x4),
                    "current_hybrid": str(hybrid),
                    "fallback_hybrid": str(override),
                }
            )
            page_count += 1

        control_inventory = output_root / "inventories" / "control" / f"{score}.json"
        fallback_inventory = output_root / "inventories" / "x4_gap_fallback" / f"{score}.json"
        _write_json(
            control_inventory,
            {
                "schema_version": "issue372.retained_inventory.v1",
                "records": control_records,
            },
        )
        _write_json(
            fallback_inventory,
            {
                "schema_version": "issue372.retained_inventory.v1",
                "records": fallback_records,
            },
        )
        control_paths[score] = control_inventory
        fallback_paths[score] = fallback_inventory

    if page_count != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} pages, materialized {page_count}")
    return control_paths, fallback_paths, promotion_rows


def _copy_tree(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _run_variant(
    *,
    name: str,
    inventory_paths: Mapping[str, Path],
    config: Mapping[str, Any],
    image_root: Path,
    output_root: Path,
    model_path: Path,
    threshold: float,
) -> dict[str, Any]:
    from src.pipeline.detector_routes.dense_full_pipeline import (
        reconstruct_dense_full_pipeline_route,
    )
    from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch

    detection = config["detection"]
    assert isinstance(detection, Mapping)

    aggregate_raw = output_root / name / "aggregate_raw_candidates"
    aggregate_filtered = output_root / name / "aggregate_filtered_candidates"
    aggregate_probe = output_root / name / "aggregate_probe_output"
    exclude = output_root / "exclude.json"
    if not exclude.is_file():
        _write_json(exclude, {"excluded_pages": []})

    groups: list[dict[str, Any]] = []
    started = time.perf_counter()

    for score, pages in full68_eval.SCORES.items():
        inventory = inventory_paths.get(score)
        if inventory is None:
            raise FileNotFoundError(f"Missing inventory for score {score}")
        images = [image_root / score / f"{page}.png" for page in pages]
        missing = [str(path) for path in images if not path.is_file()]
        if missing:
            raise FileNotFoundError("Missing images: " + ", ".join(missing))

        group_root = output_root / name / "groups" / score
        route_started = time.perf_counter()
        route = reconstruct_dense_full_pipeline_route(
            inventory=inventory,
            exclude=exclude,
            route_root=group_root / "route",
            expected_pages=len(images),
        )
        route_seconds = time.perf_counter() - route_started

        scoring_started = time.perf_counter()
        processed = run_cnn_scoring_batch(
            probe_output_root=route.probe_rescue_root,
            images=images,
            model_path=model_path,
            threshold=threshold,
            score_name=score,
            batch_size=int(detection.get("cnn_batch_size", 64)),
            bands_from=route.filtered_root,
            staff_vov_threshold=float(detection.get("staff_vov_threshold", 0.5)),
            crop_recenter_on_bbox_ink=bool(
                detection.get("crop_recenter_on_bbox_ink", False)
            ),
            crop_recenter_max_shift_unit_ratio=float(
                detection.get("crop_recenter_max_shift_unit_ratio", 0.35)
            ),
            input_image_scale=1.0,
            apply_nms_enabled=False,
        )
        scoring_seconds = time.perf_counter() - scoring_started
        if processed != len(images):
            raise RuntimeError(
                f"{name}/{score}: CNN scoring processed {processed}/{len(images)} pages"
            )

        dense_root = group_root / "route" / "dense_candidate_reconstruction"
        _copy_tree(dense_root / "probe_candidates_from_inventory", aggregate_raw)
        _copy_tree(dense_root / "probe_candidates_filtered", aggregate_filtered)
        _copy_tree(route.probe_rescue_root, aggregate_probe)
        groups.append(
            {
                "score": score,
                "page_count": len(images),
                "route_seconds": route_seconds,
                "scoring_seconds": scoring_seconds,
                "route_root": str(group_root / "route"),
            }
        )

    return {
        "name": name,
        "aggregate_raw": str(aggregate_raw),
        "aggregate_filtered": str(aggregate_filtered),
        "aggregate_probe": str(aggregate_probe),
        "groups": groups,
        "total_seconds": time.perf_counter() - started,
    }


def _evaluation_args(
    *,
    results_dir: Path,
    output_dir: Path,
    gt_root: Path,
    image_root: Path,
    staff_units: Path,
    threshold: float,
    legacy: bool,
) -> Namespace:
    return Namespace(
        results_dir=str(results_dir),
        gt_root=str(gt_root),
        output_dir=str(output_dir),
        scored_file="pipeline2_no_peak_filtered_cnn.json",
        candidates_file="pipeline2_no_peak_candidates.json",
        score_threshold=threshold,
        rule_name="center_anchor",
        vov_threshold=0.5,
        staff_units_json=str(staff_units),
        image_root=str(image_root),
        xdist_unit_ratio=full68_eval.CENTER_ANCHOR_XDIST_UNIT_RATIO,
        legacy_fixed_12px=legacy,
        allow_partial=False,
        measure_summary_json=None,
    )


def _evaluate_variant(
    *,
    variant: Mapping[str, Any],
    output_root: Path,
    gt_root: Path,
    image_root: Path,
    staff_units: Path,
    threshold: float,
) -> dict[str, Any]:
    results = Path(str(variant["aggregate_probe"]))
    name = str(variant["name"])
    legacy = full68_eval.evaluate(
        _evaluation_args(
            results_dir=results,
            output_dir=output_root / name / "eval_legacy_fixed12",
            gt_root=gt_root,
            image_root=image_root,
            staff_units=staff_units,
            threshold=threshold,
            legacy=True,
        )
    )
    unit = full68_eval.evaluate(
        _evaluation_args(
            results_dir=results,
            output_dir=output_root / name / "eval_current_unit",
            gt_root=gt_root,
            image_root=image_root,
            staff_units=staff_units,
            threshold=threshold,
            legacy=False,
        )
    )
    return {
        "legacy_fixed12": asdict(legacy.detector_summary),
        "current_unit": asdict(unit.detector_summary),
    }


def _metric_delta(candidate: Mapping[str, Any], control: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("pred", "candidate_count", "tp", "fp", "fn", "fn_det", "fn_cnn")
    result: dict[str, Any] = {}
    for field in fields:
        a = candidate.get(field)
        b = control.get(field)
        result[field] = None if a is None or b is None else int(a) - int(b)
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    report_path = args.issue43_report.resolve()
    source_repo_root = args.issue43_repo_root.resolve()
    config_path = args.config.resolve()
    image_root = args.image_root.resolve()
    gt_root = args.gt_root.resolve()
    staff_units = args.staff_units_json.resolve()
    output_root = args.output_root.resolve()

    for path in (report_path, config_path, image_root, gt_root, staff_units):
        if not path.exists():
            raise FileNotFoundError(path)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(
            f"Counterfactual output root must be new/empty: {output_root}"
        )
    output_root.mkdir(parents=True, exist_ok=True)

    issue43_report = _load_json(report_path)
    if not isinstance(issue43_report, Mapping):
        raise ValueError("Issue #43 report must be a JSON object")
    config = _load_config(config_path)
    detection = config["detection"]
    assert isinstance(detection, Mapping)

    manifest = detection.get("cnn_model_manifest")
    threshold_raw = detection.get("cnn_threshold")
    if not manifest or threshold_raw is None:
        raise ValueError("Canonical config lacks CNN manifest/threshold")
    threshold = float(threshold_raw)
    model_path = _resolve_verified_cnn_artifact(
        str(manifest),
        cnn_threshold=threshold,
    )

    control_inv, fallback_inv, promotions = _materialize_inventories(
        issue43_report=issue43_report,
        source_repo_root=source_repo_root,
        image_root=image_root,
        output_root=output_root,
    )

    control = _run_variant(
        name="control",
        inventory_paths=control_inv,
        config=config,
        image_root=image_root,
        output_root=output_root,
        model_path=model_path,
        threshold=threshold,
    )
    fallback = _run_variant(
        name="x4_gap_fallback",
        inventory_paths=fallback_inv,
        config=config,
        image_root=image_root,
        output_root=output_root,
        model_path=model_path,
        threshold=threshold,
    )

    control_eval = _evaluate_variant(
        variant=control,
        output_root=output_root,
        gt_root=gt_root,
        image_root=image_root,
        staff_units=staff_units,
        threshold=threshold,
    )
    fallback_eval = _evaluate_variant(
        variant=fallback,
        output_root=output_root,
        gt_root=gt_root,
        image_root=image_root,
        staff_units=staff_units,
        threshold=threshold,
    )

    expected_reconstruction = issue43_report.get("variants", {}).get(
        "full_width", {}
    )
    expected_summary = (
        expected_reconstruction.get("detector_summary")
        if isinstance(expected_reconstruction, Mapping)
        else None
    )
    control_reproduces_issue43 = (
        isinstance(expected_summary, Mapping)
        and dict(expected_summary) == control_eval["current_unit"]
    )

    report = {
        "schema_version": "issue372.retained_x4_gap_counterfactual.v1",
        "contract": {
            "homr_sr_omr_inference_rerun": False,
            "hybrid_change_only": True,
            "fallback_rule": (
                "current hybrid plus current-x4 HOMR boxes with no baseline HOMR "
                "box at barline_iou > 0.5"
            ),
            "iou_threshold": IOU_THRESHOLD,
            "cnn_model": str(model_path),
            "cnn_threshold": threshold,
            "cnn_apply_nms": False,
            "config": str(config_path),
            "issue43_report": str(report_path),
        },
        "promotion_summary": {
            "page_count": len(promotions),
            "total_promoted_x4_gap_boxes": sum(
                int(row["promoted_x4_gap_count"]) for row in promotions
            ),
            "pages_with_promotions": sum(
                int(row["promoted_x4_gap_count"]) > 0 for row in promotions
            ),
            "per_page": promotions,
        },
        "control": {
            **control,
            "evaluation": control_eval,
            "issue43_expected_current_unit": dict(expected_summary)
            if isinstance(expected_summary, Mapping)
            else None,
            "reproduces_issue43_full_width_summary": control_reproduces_issue43,
        },
        "x4_gap_fallback": {
            **fallback,
            "evaluation": fallback_eval,
            "delta_vs_control": {
                mode: _metric_delta(fallback_eval[mode], control_eval[mode])
                for mode in ("legacy_fixed12", "current_unit")
            },
        },
    }
    report_out = output_root / "counterfactual_report.json"
    _write_json(report_out, report)

    print("=== Issue #372 retained x4-gap fallback counterfactual ===")
    print(
        "promotions="
        f"{report['promotion_summary']['total_promoted_x4_gap_boxes']} "
        f"pages={report['promotion_summary']['pages_with_promotions']}"
    )
    print(
        "control_reproduces_issue43_full_width_summary="
        f"{control_reproduces_issue43}"
    )
    for mode in ("legacy_fixed12", "current_unit"):
        print(f"{mode} control={control_eval[mode]}")
        print(f"{mode} fallback={fallback_eval[mode]}")
        print(
            f"{mode} delta="
            f"{report['x4_gap_fallback']['delta_vs_control'][mode]}"
        )
    print(f"OUTPUT={report_out}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue43-report", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/dense_full_pipeline.yaml",
    )
    parser.add_argument(
        "--image-root",
        type=Path,
        default=ROOT / "data/evaluation2/images",
    )
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=ROOT / "data/evaluation2/annotations",
    )
    parser.add_argument(
        "--staff-units-json",
        type=Path,
        default=ROOT / "data/evaluation2/staff_units.json",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
