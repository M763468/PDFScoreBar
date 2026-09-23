#!/usr/bin/env python3
"""Run retained late-raw + frozen-hybrid-band counterfactual for Issue #372.

No HOMR, SR, OMR-DLN, dense candidate generation, or probe-scan regeneration.

Starting point:
- retained late-raw x4 aggregate probe candidates.

Counterfactual:
- copy those exact retained probe candidates;
- rerun only CNN scoring;
- use pre-expansion current hybrid predictions as the staff-band authority
  instead of post-expansion filtered candidates.

This directly tests the combined design:
1. late x4 injection recovers missing candidates;
2. probe-generated candidates cannot redefine the geometry used to
   geometrically filter themselves.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _evaluate_variant,
    _host_path,
    _load_config,
    _load_json,
    _write_json,
)
from src.pipeline.detection.restored_orchestrator import _resolve_verified_cnn_artifact
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

TARGET_SCORE = "Shostakovich-Sym5-Va"
TARGET_PAGE = "page_021"
TARGET_BOXES = {
    (1333, 798, 1340, 894),
    (1769, 798, 1778, 896),
    (2749, 802, 2756, 900),
}


def _inventory_record(path: Path, page: str) -> Mapping[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError(f"Invalid inventory: {path}")
    rows = [
        row for row in payload["records"]
        if isinstance(row, Mapping) and str(row.get("page")) == page
    ]
    if len(rows) != 1:
        raise ValueError(f"Expected one {page} record in {path}, got {len(rows)}")
    return rows[0]


def _materialize_frozen_bands(
    *,
    x4_run_root: Path,
    issue43_repo_root: Path,
    output_root: Path,
) -> Path:
    bands_root = output_root / "frozen_hybrid_bands"
    page_count = 0
    for score, pages in full68_eval.SCORES.items():
        inventory = x4_run_root / "inventories" / "control" / f"{score}.json"
        if not inventory.is_file():
            raise FileNotFoundError(inventory)
        score_root = bands_root / score
        score_root.mkdir(parents=True, exist_ok=True)
        for page in pages:
            record = _inventory_record(inventory, page)
            raw = Path(str(record["hybrid_predictions"]))
            source = raw if raw.is_file() else _host_path(raw, issue43_repo_root)
            if not source.is_file():
                raise FileNotFoundError(source)
            boxes = load_json_boxes(source)
            _write_json(score_root / f"{page}.json", boxes)
            page_count += 1
    if page_count != 68:
        raise RuntimeError(f"Expected 68 frozen-band pages, got {page_count}")
    return bands_root


def _find_page(root: Path, score: str, page: str, filename: str) -> Path:
    record = full68_eval.PageRecord(score=score, page=page)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{score}/{page}: {filename} under {root}")
    return path


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run_root = args.x4_run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    late_report_path = args.late_report.resolve()
    config_path = args.config.resolve()
    image_root = args.image_root.resolve()
    gt_root = args.gt_root.resolve()
    staff_units = args.staff_units_json.resolve()
    output_root = args.output_root.resolve()

    for path in (
        x4_run_root,
        issue43_repo_root,
        late_report_path,
        config_path,
        image_root,
        gt_root,
        staff_units,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root must be new/empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    late_report = _load_json(late_report_path)
    if not isinstance(late_report, Mapping):
        raise ValueError(f"Invalid late report: {late_report_path}")
    late = late_report.get("late_raw_x4")
    if not isinstance(late, Mapping):
        raise ValueError("late report lacks late_raw_x4")
    late_probe = Path(str(late["aggregate_probe"]))
    if not late_probe.is_dir():
        raise FileNotFoundError(late_probe)

    config = _load_config(config_path)
    detection = config["detection"]
    assert isinstance(detection, Mapping)

    manifest = detection.get("cnn_model_manifest")
    if not manifest:
        raise ValueError("config lacks detection.cnn_model_manifest")
    threshold = float(detection["cnn_threshold"])
    model_path = _resolve_verified_cnn_artifact(
        str(manifest),
        cnn_threshold=threshold,
    )

    frozen_root = _materialize_frozen_bands(
        x4_run_root=x4_run_root,
        issue43_repo_root=issue43_repo_root,
        output_root=output_root,
    )

    probe_root = output_root / "late_probe_frozen_band_cnn"
    shutil.copytree(late_probe, probe_root)

    for score, pages in full68_eval.SCORES.items():
        images = [image_root / score / f"{page}.png" for page in pages]
        missing = [str(path) for path in images if not path.is_file()]
        if missing:
            raise FileNotFoundError("Missing images: " + ", ".join(missing))
        processed = run_cnn_scoring_batch(
            probe_output_root=probe_root,
            images=images,
            model_path=model_path,
            threshold=threshold,
            score_name=score,
            batch_size=int(detection.get("cnn_batch_size", 64)),
            bands_from=frozen_root / score,
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
            raise RuntimeError(f"{score}: CNN processed {processed}/{len(images)}")

    variant = {
        "name": "late_raw_x4_frozen_hybrid_bands",
        "aggregate_probe": str(probe_root),
    }
    evaluation = _evaluate_variant(
        variant=variant,
        output_root=output_root,
        gt_root=gt_root,
        image_root=image_root,
        staff_units=staff_units,
        threshold=threshold,
    )

    target_file = _find_page(
        probe_root,
        TARGET_SCORE,
        TARGET_PAGE,
        "pipeline2_no_peak_filtered_cnn.json",
    )
    target_payload = _load_json(target_file)
    target_final = {
        tuple(int(round(float(v))) for v in item["bbox"])
        for item in target_payload
        if isinstance(item, Mapping)
        and isinstance(item.get("bbox"), list)
        and float(item.get("score", 0.0)) >= threshold
    }
    target_presence = {
        str(list(box)): box in target_final
        for box in sorted(TARGET_BOXES)
    }

    late_eval = late.get("evaluation") if isinstance(late, Mapping) else None
    report = {
        "schema_version": "issue372.late_raw_frozen_hybrid_bands_counterfactual.v1",
        "contract": {
            "homr_sr_omr_rerun": False,
            "candidate_generation_rerun": False,
            "probe_scan_rerun": False,
            "retained_late_probe_candidates_frozen": True,
            "cnn_rerun_only": True,
            "cnn_model": str(model_path),
            "cnn_threshold": threshold,
            "cnn_apply_nms": False,
            "geometric_band_source": "pre-expansion current hybrid predictions",
            "config": str(config_path),
        },
        "inputs": {
            "late_report": str(late_report_path),
            "late_probe": str(late_probe),
            "x4_run_root": str(x4_run_root),
        },
        "frozen_bands_root": str(frozen_root),
        "aggregate_probe": str(probe_root),
        "evaluation": evaluation,
        "late_raw_reference_evaluation": late_eval,
        "page021": {
            "final_file": str(target_file),
            "target_presence": target_presence,
        },
    }
    report_path = output_root / "counterfactual_report.json"
    _write_json(report_path, report)

    print("=== Issue #372 late-raw + frozen-hybrid-band counterfactual ===")
    for mode in ("legacy_fixed12", "current_unit"):
        print(f"{mode}: {evaluation[mode]}")
    print("page_021 targets:")
    for box, present in target_presence.items():
        print(f"  {box}: {present}")
    print(f"OUTPUT={report_path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--late-report", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "dense_full_pipeline.yaml",
    )
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--staff-units-json", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return run(parser.parse_args()) and 0


if __name__ == "__main__":
    raise SystemExit(main())
