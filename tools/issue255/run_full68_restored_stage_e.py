#!/usr/bin/env python3
"""Run Stage E lower-route reconstruction from the restored Issue #255 full-68 upstream.

This phase does not run baseline HOMR, SR generation, SR HOMR, OMR-DLN, or
consensus. It consumes only the fresh upstream report produced by
``run_full68_restored_upstream.py``, reconstructs dense/filter/Issue53 candidates,
runs the canonical CNN with NMS disabled, and evaluates the current-GT full-68
contract.
"""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.pipeline.core.config import load_yaml
from src.pipeline.detector_routes.dense_full_pipeline import (
    FILTER_PARAMS,
    GENERATION_PARAMS,
    reconstruct_dense_full_pipeline_route,
)
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from tools.issue120 import eval_full68_from_intermediates as full68_eval
from tools.issue252.probe_boundary import write_json
from tools.issue255.full68_restoration import (
    EXPECTED_CURRENT_GT_METRICS,
    inventory_from_upstream_report,
    metric_mismatches,
)
from tools.issue255.run_focused_stage_e_reconstruction import _record, _tree_record
from tools.issue255.run_public_baseline_ab import EXPECTED_BRANCH
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    ROOT,
    _git,
    _resolve_repo_artifact,
)

CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "logs/issue255_full68_restoration"
CANDIDATES = "pipeline2_no_peak_candidates.json"
SCORED = "pipeline2_no_peak_scored.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluation_args(
    *,
    results_dir: Path,
    gt_root: Path,
    output_dir: Path,
    score_threshold: float,
) -> Namespace:
    return Namespace(
        results_dir=str(results_dir),
        gt_root=str(gt_root),
        output_dir=str(output_dir),
        scored_file=SCORED,
        candidates_file=CANDIDATES,
        score_threshold=score_threshold,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
        allow_partial=False,
        measure_summary_json=None,
    )


def _validate_upstream_execution_identity(
    upstream: Mapping[str, Any],
    *,
    commit: str,
    canonical_config_record: Mapping[str, Any],
) -> None:
    upstream_commit = upstream.get("repository_commit")
    if upstream_commit != commit:
        raise ValueError(
            "Upstream replay commit differs from current checkout: "
            f"upstream={upstream_commit} current={commit}"
        )
    upstream_config = upstream.get("canonical_config")
    if not isinstance(upstream_config, Mapping):
        raise ValueError("Upstream report lacks canonical config provenance")
    expected_hash = canonical_config_record.get("sha256")
    actual_hash = upstream_config.get("sha256")
    if not isinstance(expected_hash, str) or actual_hash != expected_hash:
        raise ValueError(
            "Upstream replay canonical config differs from current config: "
            f"upstream={actual_hash} current={expected_hash}"
        )


def run(args: argparse.Namespace) -> Path:
    if args.config.resolve() != CANONICAL_CONFIG.resolve():
        raise ValueError(f"Canonical config required: {CANONICAL_CONFIG}")
    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise RuntimeError(f"Expected branch {EXPECTED_BRANCH}; found {branch}")
    if _git("status", "--short", "--untracked-files=no"):
        raise RuntimeError("Tracked working tree must be clean before authoritative replay")
    commit = _git("rev-parse", "HEAD")
    canonical_config_record = _record(args.config.resolve())

    upstream_path = args.upstream_report.resolve()
    upstream = _load(upstream_path)
    if not isinstance(upstream, Mapping):
        raise ValueError("Upstream report must be a JSON object")
    _validate_upstream_execution_identity(
        upstream,
        commit=commit,
        canonical_config_record=canonical_config_record,
    )
    inventory = inventory_from_upstream_report(upstream)

    run_root = args.output_root.resolve() / args.run_tag
    if run_root.exists() and any(run_root.iterdir()):
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    inventory_path = run_root / "restored_upstream_inventory.json"
    exclude_path = run_root / "exclude.json"
    write_json(
        inventory_path,
        {
            "schema_version": "issue255.full68_restored_stage_e_inventory.v1",
            "historical_runtime_input": False,
            "source_upstream_report": str(upstream_path),
            "records": inventory,
        },
    )
    write_json(exclude_path, {"excluded_pages": []})

    config = load_yaml(args.config)
    detection = config.get("detection") if isinstance(config, Mapping) else None
    if not isinstance(detection, Mapping):
        raise ValueError("Canonical config lacks detection settings")
    forbidden = [
        key for key in ("precomputed_probe_candidates_root", "cnn_bands_from") if detection.get(key)
    ]
    if forbidden:
        raise ValueError(f"Canonical fresh route contains runtime overrides: {forbidden}")

    stage_e_root = run_root / "stage_e"
    dense = reconstruct_dense_full_pipeline_route(
        inventory=inventory_path,
        exclude=exclude_path,
        route_root=stage_e_root,
        expected_pages=68,
        verbose_logs=args.verbose_dense_logs,
    )
    images = [Path(row["image"]).resolve() for row in inventory]
    missing_images = [str(path) for path in images if not path.is_file()]
    if missing_images:
        raise FileNotFoundError(f"Missing Stage E input images: {missing_images}")

    cnn_model = _resolve_repo_artifact(str(detection["cnn_model_path"]))
    if not cnn_model.is_file():
        raise FileNotFoundError(cnn_model)
    score_threshold = float(detection.get("cnn_threshold", 0.1))
    run_cnn_scoring_batch(
        probe_output_root=dense.probe_rescue_root,
        images=images,
        model_path=cnn_model,
        threshold=score_threshold,
        score_name=(
            str(detection["probe_score_name"]) if detection.get("probe_score_name") else None
        ),
        crop_recenter_on_bbox_ink=bool(detection.get("crop_recenter_on_bbox_ink", False)),
        crop_recenter_max_shift_unit_ratio=float(
            detection.get("crop_recenter_max_shift_unit_ratio", 0.35)
        ),
        input_image_scale=1.0,
        bands_from=dense.filtered_root,
        staff_vov_threshold=float(detection.get("staff_vov_threshold", 0.5)),
        apply_nms_enabled=False,
        in_memory_images=None,
    )

    eval_output = run_root / "eval_detector"
    contract = full68_eval.evaluate(
        _evaluation_args(
            results_dir=dense.probe_rescue_root,
            gt_root=args.gt_root.resolve(),
            output_dir=eval_output,
            score_threshold=score_threshold,
        )
    )
    summary = asdict(contract.detector_summary)
    mismatches = metric_mismatches(summary)

    report = {
        "schema_version": "issue255.full68_restored_stage_e.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "run_tag": args.run_tag,
        "repository_commit": commit,
        "source_upstream_report": _record(upstream_path),
        "historical_artifact_used_as_runtime_input": False,
        "canonical_config": canonical_config_record,
        "route": {
            "dense_generation_params": GENERATION_PARAMS,
            "clef_filter_params": FILTER_PARAMS,
            "cnn_model": str(cnn_model),
            "cnn_threshold": score_threshold,
            "cnn_apply_nms": False,
            "probe_use_original_images": True,
            "production_orchestrator_connection": False,
        },
        "artifacts": {
            "inventory": _record(inventory_path),
            "dense_raw_tree": _tree_record(
                stage_e_root / "dense_candidate_reconstruction/probe_candidates_from_inventory"
            ),
            "filtered_tree": _tree_record(dense.filtered_root),
            "issue53_and_cnn_tree": _tree_record(dense.probe_rescue_root),
            "evaluation_contract": _record(eval_output / "evaluation_contract.json"),
            "detector_metrics": _record(eval_output / "detector_metrics.json"),
            "detector_page_metrics": _record(eval_output / "detector_page_metrics.csv"),
        },
        "detector_summary": summary,
        "expected_current_gt_metrics": EXPECTED_CURRENT_GT_METRICS,
        "metric_mismatches": mismatches,
        "gates": {
            "page_count_68": summary.get("page_count") == 68,
            "same_commit_as_upstream": True,
            "same_canonical_config_as_upstream": True,
            "historical_runtime_artifact_dependency_absent": True,
            "cnn_apply_nms_false": True,
            "current_gt_historical_target_met": not mismatches,
        },
        "next_action": (
            "full68_restoration_confirmed"
            if not mismatches
            else "inspect_page_level_residuals_before_any_production_change"
        ),
    }
    report_path = run_root / "full68_restored_stage_e_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--upstream-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--config", type=Path, default=CANONICAL_CONFIG)
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=ROOT / "data/evaluation2/annotations",
    )
    parser.add_argument("--verbose-dense-logs", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {"status": "completed", "report": str(report)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
