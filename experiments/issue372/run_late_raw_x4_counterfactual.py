#!/usr/bin/env python3
"""Run Issue #372 late-raw maintained-x4 injection counterfactual.

This experiment keeps current production hybrid/raw generation frozen.

Starting point:
    retained current-control raw candidates from x4_gap_counterfactual_v2

Counterfactual:
    current raw candidates
    + maintained-x4 HOMR boxes not represented by any current raw candidate at
      barline_iou > 0.5

Then run the existing production candidate filter, probe rescue, and immutable
D27 CNN scorer. HOMR, SR, OMR-DLN, and initial probe/raw generation are not
rerun.

The purpose is to test whether moving maintained-x4 compatibility support after
raw generation recovers the main #372 regression without the hybrid-seed
side-effects observed in the broad hybrid fallback.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    IOU_THRESHOLD,
    _evaluate_variant,
    _host_path,
    _load_config,
    _load_json,
    _metric_delta,
    _resolve_verified_cnn_artifact,
    _source_worker_result,
    _write_json,
)
from src.common import barline_iou
from src.pipeline.detector_routes.dense_full_pipeline import (
    regenerate_probe_rescue_candidates,
)
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

EXPECTED_PAGES = 68


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _dedup_preserve(
    boxes: Sequence[Sequence[Any]],
) -> list[list[int]]:
    seen: set[tuple[int, int, int, int]] = set()
    out: list[list[int]] = []
    for raw in boxes:
        box = _norm(raw)
        if box in seen:
            continue
        seen.add(box)
        out.append(list(box))
    return out


def build_late_raw_x4_union(
    *,
    raw_boxes: Sequence[Sequence[Any]],
    x4_boxes: Sequence[Sequence[Any]],
    iou_threshold: float = IOU_THRESHOLD,
) -> tuple[list[list[int]], list[list[int]]]:
    """Add only x4 boxes unrepresented by the frozen current raw set."""
    raw_norm = [_norm(box) for box in raw_boxes]
    promoted = [
        list(_norm(x4))
        for x4 in x4_boxes
        if not any(barline_iou(x4, raw) > iou_threshold for raw in raw_norm)
    ]
    return _dedup_preserve([*raw_boxes, *promoted]), _dedup_preserve(promoted)


def _inventory_records(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError(f"Invalid inventory: {path}")
    records = []
    for raw in payload["records"]:
        if not isinstance(raw, Mapping):
            raise ValueError(f"Invalid inventory record in {path}: {raw!r}")
        records.append(dict(raw))
    return records


def _x4_detection(
    record: Mapping[str, Any],
    *,
    score: str,
    page: str,
    issue43_repo_root: Path,
) -> Path:
    hybrid_raw = record.get("hybrid_predictions")
    if not hybrid_raw:
        raise ValueError(f"Inventory record lacks hybrid_predictions: {record}")
    hybrid = _host_path(str(hybrid_raw), issue43_repo_root)
    result_path = _source_worker_result(hybrid, score=score, page=page)
    payload = _load_json(result_path)
    if not isinstance(payload, Mapping) or not payload.get("current_sr_detection"):
        raise ValueError(f"Source worker lacks current_sr_detection: {result_path}")
    path = _host_path(str(payload["current_sr_detection"]), issue43_repo_root)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _current_raw_path(
    control_raw_root: Path,
    *,
    score: str,
    page: str,
) -> Path:
    direct = control_raw_root / score / page / "pipeline2_no_peak_candidates.json"
    if direct.is_file():
        return direct
    record = full68_eval.PageRecord(score=score, page=page)
    resolved = full68_eval.find_page_file(
        control_raw_root,
        record,
        "pipeline2_no_peak_candidates.json",
    )
    if resolved is None or not resolved.is_file():
        raise FileNotFoundError(
            f"Missing retained current raw candidates for {score}/{page}"
        )
    return resolved


def _materialize_late_raw(
    *,
    run_root: Path,
    issue43_repo_root: Path,
    output_root: Path,
) -> tuple[Path, dict[str, Path], list[dict[str, Any]]]:
    control_raw_root = run_root / "control" / "aggregate_raw_candidates"
    if not control_raw_root.is_dir():
        raise FileNotFoundError(control_raw_root)

    raw_out = output_root / "raw_x4_injected"
    inventory_paths: dict[str, Path] = {}
    rows: list[dict[str, Any]] = []
    page_count = 0

    for score, pages in full68_eval.SCORES.items():
        inventory = run_root / "inventories" / "control" / f"{score}.json"
        if not inventory.is_file():
            raise FileNotFoundError(inventory)
        inventory_paths[score] = inventory

        by_page = {
            str(record["page"]): record
            for record in _inventory_records(inventory)
        }
        if set(by_page) != set(pages):
            raise ValueError(
                f"Control inventory page mismatch for {score}: "
                f"{sorted(by_page)} != {sorted(pages)}"
            )

        for page in pages:
            record = by_page[page]
            raw_path = _current_raw_path(
                control_raw_root,
                score=score,
                page=page,
            )
            x4_path = _x4_detection(
                record,
                score=score,
                page=page,
                issue43_repo_root=issue43_repo_root,
            )
            raw_boxes = load_json_boxes(raw_path)
            x4_boxes = load_json_boxes(x4_path)
            union_boxes, promoted = build_late_raw_x4_union(
                raw_boxes=raw_boxes,
                x4_boxes=x4_boxes,
            )
            target = raw_out / score / page / "pipeline2_no_peak_candidates.json"
            _write_json(target, union_boxes)
            rows.append(
                {
                    "score": score,
                    "page": page,
                    "current_raw_count": len(raw_boxes),
                    "x4_count": len(x4_boxes),
                    "promoted_x4_count": len(promoted),
                    "late_raw_count": len(union_boxes),
                    "current_raw": str(raw_path),
                    "x4": str(x4_path),
                    "late_raw": str(target),
                    "promoted_boxes": promoted,
                }
            )
            page_count += 1

    if page_count != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} pages, materialized {page_count}")
    return raw_out, inventory_paths, rows


def _run_filter(
    *,
    raw_root: Path,
    inventory_paths: Mapping[str, Path],
    output_root: Path,
) -> Path:
    filtered = output_root / "filtered"
    suggestions = output_root / "filter_suggestions"
    exclude = output_root / "exclude.json"
    _write_json(exclude, {"excluded_pages": []})

    tool = ROOT / "tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py"
    for score, pages in full68_eval.SCORES.items():
        inventory = inventory_paths[score]
        summary = output_root / "filter_summaries" / f"{score}.json"
        cmd = [
            sys.executable,
            str(tool),
            "--inventory",
            str(inventory),
            "--exclude",
            str(exclude),
            "--candidates-root",
            str(raw_root),
            "--output-root",
            str(filtered),
            "--suggestions-root",
            str(suggestions),
            "--summary-out",
            str(summary),
            "--left-margin-ratio",
            "0.12",
            "--clef-left-ratio",
            "0.25",
            "--min-height-median-ratio",
            "0.6",
            "--ink-threshold",
            "180",
            "--min-ink-ratio",
            "0.18",
            "--paper-threshold",
            "200",
            "--min-paper-overlap-ratio",
            "0.6",
            "--min-staff-overlap-ratio",
            "0.02",
        ]
        subprocess.run(cmd, cwd=ROOT, check=True)
        payload = _load_json(summary)
        if (
            int(payload.get("processed", -1)) != len(pages)
            or int(payload.get("errors", -1)) != 0
        ):
            raise RuntimeError(
                f"{score}: filter incomplete: "
                f"processed={payload.get('processed')} errors={payload.get('errors')}"
            )
    return filtered


def _canonical_images(image_root: Path) -> list[Path]:
    paths = [
        image_root / score / f"{page}.png"
        for score, pages in full68_eval.SCORES.items()
        for page in pages
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing canonical images: " + ", ".join(missing))
    return paths


def _run_cnn(
    *,
    probe_root: Path,
    filtered_root: Path,
    image_root: Path,
    config: Mapping[str, Any],
    model_path: Path,
    threshold: float,
) -> None:
    detection = config["detection"]
    assert isinstance(detection, Mapping)

    for score, pages in full68_eval.SCORES.items():
        images = [image_root / score / f"{page}.png" for page in pages]
        processed = run_cnn_scoring_batch(
            probe_output_root=probe_root,
            images=images,
            model_path=model_path,
            threshold=threshold,
            score_name=score,
            batch_size=int(detection.get("cnn_batch_size", 64)),
            bands_from=filtered_root,
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
        if processed != len(images):
            raise RuntimeError(
                f"{score}: CNN scoring processed {processed}/{len(images)} pages"
            )


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    issue43_report_path = args.issue43_report.resolve()
    config_path = args.config.resolve()
    image_root = args.image_root.resolve()
    gt_root = args.gt_root.resolve()
    staff_units = args.staff_units_json.resolve()
    output_root = args.output_root.resolve()

    for required in (
        run_root,
        issue43_repo_root,
        issue43_report_path,
        config_path,
        image_root,
        gt_root,
        staff_units,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root must be new/empty: {output_root}")

    config = _load_config(config_path)
    detection = config["detection"]
    assert isinstance(detection, Mapping)
    manifest = detection.get("cnn_model_manifest")
    threshold_raw = detection.get("cnn_threshold")
    if not manifest or threshold_raw is None:
        raise ValueError("Canonical config lacks D27 manifest/threshold")
    threshold = float(threshold_raw)

    # Immutable model integrity is an environment preflight. Do this before
    # creating output so a missing cache artifact leaves no partial run.
    model_path = _resolve_verified_cnn_artifact(
        str(manifest),
        cnn_threshold=threshold,
    )

    control_probe = run_root / "control" / "aggregate_probe_output"
    if not control_probe.is_dir():
        raise FileNotFoundError(control_probe)

    issue43_report = _load_json(issue43_report_path)
    expected_summary = (
        issue43_report.get("variants", {})
        .get("full_width", {})
        .get("detector_summary")
        if isinstance(issue43_report, Mapping)
        else None
    )

    output_root.mkdir(parents=True, exist_ok=True)
    raw_root, inventory_paths, promotion_rows = _materialize_late_raw(
        run_root=run_root,
        issue43_repo_root=issue43_repo_root,
        output_root=output_root,
    )
    filtered_root = _run_filter(
        raw_root=raw_root,
        inventory_paths=inventory_paths,
        output_root=output_root,
    )

    images = _canonical_images(image_root)
    rescue_route_root = output_root / "late_raw_route"
    probe_root = regenerate_probe_rescue_candidates(
        image_paths=images,
        filtered_root=filtered_root,
        route_root=rescue_route_root,
    )
    _run_cnn(
        probe_root=probe_root,
        filtered_root=filtered_root,
        image_root=image_root,
        config=config,
        model_path=model_path,
        threshold=threshold,
    )

    control = {
        "name": "control",
        "aggregate_probe": str(control_probe),
    }
    late = {
        "name": "late_raw_x4",
        "aggregate_probe": str(probe_root),
    }
    control_eval = _evaluate_variant(
        variant=control,
        output_root=output_root,
        gt_root=gt_root,
        image_root=image_root,
        staff_units=staff_units,
        threshold=threshold,
    )
    late_eval = _evaluate_variant(
        variant=late,
        output_root=output_root,
        gt_root=gt_root,
        image_root=image_root,
        staff_units=staff_units,
        threshold=threshold,
    )
    reproduces_issue43 = (
        isinstance(expected_summary, Mapping)
        and dict(expected_summary) == control_eval["current_unit"]
    )

    report = {
        "schema_version": "issue372.late_raw_x4_counterfactual.v1",
        "contract": {
            "homr_sr_omr_rerun": False,
            "initial_raw_generation_rerun": False,
            "current_raw_frozen": True,
            "injection_boundary": "after current raw, before candidate filter",
            "promotion_rule": "x4 box not represented by current raw at barline_iou > 0.5",
            "iou_threshold": IOU_THRESHOLD,
            "candidate_filter": "current dense_full_pipeline production filter",
            "probe_rescue": "current dense_full_pipeline production rescue",
            "cnn_model": str(model_path),
            "cnn_threshold": threshold,
            "cnn_apply_nms": False,
        },
        "promotion_summary": {
            "page_count": len(promotion_rows),
            "pages_with_promotions": sum(
                int(row["promoted_x4_count"]) > 0 for row in promotion_rows
            ),
            "total_promoted_x4_boxes": sum(
                int(row["promoted_x4_count"]) for row in promotion_rows
            ),
            "per_page": promotion_rows,
        },
        "control": {
            "evaluation": control_eval,
            "issue43_expected_current_unit": (
                dict(expected_summary) if isinstance(expected_summary, Mapping) else None
            ),
            "reproduces_issue43_full_width_summary": reproduces_issue43,
        },
        "late_raw_x4": {
            "raw_root": str(raw_root),
            "filtered_root": str(filtered_root),
            "aggregate_probe": str(probe_root),
            "evaluation": late_eval,
            "delta_vs_control": {
                mode: _metric_delta(late_eval[mode], control_eval[mode])
                for mode in ("legacy_fixed12", "current_unit")
            },
        },
    }
    report_path = output_root / "late_raw_x4_counterfactual_report.json"
    _write_json(report_path, report)

    print("=== Issue #372 late-raw x4 counterfactual ===")
    print(
        f"promotions={report['promotion_summary']['total_promoted_x4_boxes']} "
        f"pages={report['promotion_summary']['pages_with_promotions']}"
    )
    print(f"control_reproduces_issue43={reproduces_issue43}")
    for mode in ("legacy_fixed12", "current_unit"):
        print(f"{mode} control={control_eval[mode]}")
        print(f"{mode} late_raw_x4={late_eval[mode]}")
        print(
            f"{mode} delta="
            f"{report['late_raw_x4']['delta_vs_control'][mode]}"
        )
    print(f"OUTPUT={report_path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--issue43-report", type=Path, required=True)
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
