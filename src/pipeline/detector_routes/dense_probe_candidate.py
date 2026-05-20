"""Dense probe-candidate route implementation for Issue #120.

This module contains the reusable orchestration used by the detector-level
dense probe-candidate route. It intentionally does not change the general
detection pipeline defaults; route configs must explicitly set ``cnn_apply_nms``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.pipeline.core.config import get_nested, load_yaml
from src.pipeline.steps.probe_scan import run_probe_scan_batch
from tools.issue120.eval_full68_from_intermediates import iter_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_MODEL = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
)
DEFAULT_OUTPUT_ROOT = Path("logs/issue120_e2e_recovery/dense_probe_candidate_route")
DEFAULT_HISTORICAL_RAW = Path("logs/issue36_prep/probe_candidates_from_bench_v12")
DEFAULT_HISTORICAL_FILTERED = Path("logs/issue36_prep/probe_candidates_filtered_v12")
DEFAULT_HISTORICAL_SCORING_INPUT = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
)
TARGET_DETECTOR = {"tp": 3580, "fp": 0, "fn": 1}

GENERATION_PARAMS: dict[str, str] = {
    "band_source": "row_stats",
    "band_cluster_max_dist": "25.0",
    "ink_threshold": "240",
    "min_ratio": "0.6",
    "min_height_ratio": "0.006",
    "min_width_ratio": "0.0",
    "probe_width": "4",
    "max_per_band": "80",
    "band_scan_line_ratio": "0.6",
    "band_scan_min_lines": "5",
}

FILTER_PARAMS: dict[str, str] = {
    "left_margin_ratio": "0.12",
    "clef_left_ratio": "0.25",
    "min_height_median_ratio": "0.6",
    "ink_threshold": "180",
    "min_ink_ratio": "0.18",
    "paper_threshold": "200",
    "min_paper_overlap_ratio": "0.6",
    "min_staff_overlap_ratio": "0.02",
}

CommandRunner = Callable[[list[str]], None]


@dataclass(frozen=True)
class DenseProbeCandidateConfig:
    inventory: Path = Path("logs/issue36_prep/20260208_bench_inventory.json")
    exclude: Path = Path("logs/issue36_prep/excluded_pages_for_gt_prep.json")
    image_root: Path = Path("data/evaluation2/images")
    gt_root: Path = Path("data/evaluation2/annotations")
    model_path: Path = DEFAULT_MODEL
    baseline_dir: Path = Path("data/evaluation2/golden_baseline_eval2_bc23deb")
    output_root: Path = DEFAULT_OUTPUT_ROOT
    historical_raw_candidates_root: Path = DEFAULT_HISTORICAL_RAW
    historical_filtered_candidates_root: Path = DEFAULT_HISTORICAL_FILTERED
    historical_scoring_input_root: Path = DEFAULT_HISTORICAL_SCORING_INPUT
    raw_candidates_root: Path | None = None
    filtered_candidates_root: Path | None = None
    suggestions_root: Path | None = None
    generation_summary: Path | None = None
    filter_summary: Path | None = None
    raw_compare_output_dir: Path | None = None
    filtered_compare_output_dir: Path | None = None
    scoring_input_compare_output_dir: Path | None = None
    probe_rescue_candidates_root: Path | None = None
    scoring_output_dir: Path | None = None
    eval_output_dir: Path | None = None
    route_provenance: Path | None = None
    scorer: str = "pipeline"
    cnn_apply_nms: bool = False
    score_threshold: float = 0.1
    xdist_threshold: float = 12.0
    no_clean_output: bool = False
    skip_issue36_regeneration: bool = False
    skip_probe_rescue_regeneration: bool = False
    skip_existing_probe_rescue: bool = False
    require_candidate_match: bool = True
    require_detector_target: bool = False
    disable_seed_splitting: bool = False


@dataclass(frozen=True)
class DenseProbeCandidatePaths:
    raw_candidates_root: Path
    filtered_candidates_root: Path
    suggestions_root: Path
    generation_summary: Path
    filter_summary: Path
    raw_compare_output_dir: Path
    filtered_compare_output_dir: Path
    scoring_input_compare_output_dir: Path
    probe_rescue_candidates_root: Path
    scoring_output_dir: Path
    eval_output_dir: Path
    issue36_route_provenance: Path
    route_provenance: Path


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _command_log_name(cmd: list[str], index: int) -> str:
    script = next((Path(part).stem for part in cmd if part.endswith(".py")), "command")
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in script)
    return f"{index:02d}_{safe}.log"


def run_command(cmd: list[str]) -> None:
    print("+ " + " ".join(str(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True)


def make_logged_command_runner(log_dir: Path) -> CommandRunner:
    log_dir.mkdir(parents=True, exist_ok=True)
    counter = 0

    def _run(cmd: list[str]) -> None:
        nonlocal counter
        counter += 1
        log_path = log_dir / _command_log_name(cmd, counter)
        print("+ " + " ".join(str(part) for part in cmd) + f" > {log_path}", flush=True)
        with log_path.open("w", encoding="utf-8") as log_file:
            subprocess.run(cmd, check=True, stdout=log_file, stderr=subprocess.STDOUT)

    return _run


def add_param_args(cmd: list[str], params: dict[str, str]) -> None:
    for name, value in params.items():
        cmd.extend([f"--{name.replace('_', '-')}", value])


def require_under_logs(path: Path, *, label: str) -> None:
    logs_root = PROJECT_ROOT.resolve() / "logs"
    try:
        path.resolve().relative_to(logs_root)
    except ValueError as exc:
        raise ValueError(
            f"{label} must be under logs/ per repository log-management policy. Got: {path}"
        ) from exc


def resolve_paths(config: DenseProbeCandidateConfig) -> DenseProbeCandidatePaths:
    root = config.output_root
    return DenseProbeCandidatePaths(
        raw_candidates_root=config.raw_candidates_root or root / "probe_candidates_from_bench_v12",
        filtered_candidates_root=(
            config.filtered_candidates_root or root / "probe_candidates_filtered_v12"
        ),
        suggestions_root=config.suggestions_root or root / "filter_suggestions_v12",
        generation_summary=(
            config.generation_summary or root / "probe_generation_summary_v12_current.json"
        ),
        filter_summary=config.filter_summary or root / "filter_apply_summary_v12_current.json",
        raw_compare_output_dir=config.raw_compare_output_dir or root / "raw_delta",
        filtered_compare_output_dir=config.filtered_compare_output_dir or root / "filtered_delta",
        scoring_input_compare_output_dir=(
            config.scoring_input_compare_output_dir or root / "scoring_input_delta"
        ),
        probe_rescue_candidates_root=(
            config.probe_rescue_candidates_root or root / "probe_rescue_candidates"
        ),
        scoring_output_dir=config.scoring_output_dir or root / "scoring",
        eval_output_dir=config.eval_output_dir or root / "eval",
        issue36_route_provenance=root / "issue36_dense_candidate_route_provenance.json",
        route_provenance=config.route_provenance
        or root / "dense_probe_candidate_route_provenance.json",
    )


def validate_output_paths(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> None:
    output_paths = {
        "output_root": config.output_root,
        **{field: getattr(paths, field) for field in paths.__dataclass_fields__},
    }
    for label, path in output_paths.items():
        require_under_logs(path, label=label)


def validate_workflow_config(config: DenseProbeCandidateConfig) -> None:
    if config.skip_probe_rescue_regeneration and not config.skip_issue36_regeneration:
        raise ValueError(
            "skip_probe_rescue_regeneration requires skip_issue36_regeneration. "
            "Reusing probe-rescue candidates while regenerating Issue36 bands would mix "
            "stale candidate inputs with newly generated bands."
        )


def validate_inputs(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> None:
    validate_workflow_config(config)
    required = [
        config.inventory,
        config.exclude,
        config.image_root,
        config.gt_root,
        config.model_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required inputs:\n" + "\n".join(missing))
    validate_output_paths(config, paths)


def cleanup_targets(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> list[Path]:
    if config.no_clean_output:
        return []

    targets = [paths.scoring_output_dir, paths.eval_output_dir]
    if not config.skip_probe_rescue_regeneration:
        targets.append(paths.probe_rescue_candidates_root)
    if not config.skip_issue36_regeneration:
        targets.extend(
            [
                paths.raw_candidates_root,
                paths.filtered_candidates_root,
                paths.suggestions_root,
                paths.raw_compare_output_dir,
                paths.filtered_compare_output_dir,
                paths.scoring_input_compare_output_dir,
            ]
        )
    return targets


def clean_outputs(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> None:
    for target in cleanup_targets(config, paths):
        shutil.rmtree(target, ignore_errors=True)


def candidate_root_summary(root: Path) -> dict[str, int | str | bool]:
    files = sorted(root.rglob("pipeline2_no_peak_candidates.json")) if root.exists() else []
    total = 0
    unreadable = 0
    for path in files:
        try:
            payload = load_json(path)
        except (json.JSONDecodeError, OSError):
            unreadable += 1
            continue
        if isinstance(payload, list):
            total += len(payload)
    return {
        "root": str(root),
        "exists": root.exists(),
        "files": len(files),
        "total_candidates": total,
        "unreadable": unreadable,
    }


def load_optional_json(path: Path) -> Any | None:
    return load_json(path) if path.exists() else None


def detector_summary(eval_output_dir: Path) -> dict[str, Any] | None:
    metrics_path = eval_output_dir / "detector_metrics.json"
    if metrics_path.exists():
        payload = load_json(metrics_path)
        if isinstance(payload, dict):
            return payload
    contract_path = eval_output_dir / "evaluation_contract.json"
    if contract_path.exists():
        payload = load_json(contract_path)
        if isinstance(payload, dict):
            summary = payload.get("detector_summary")
            if isinstance(summary, dict):
                return summary
    return None


def validate_complete_contract(eval_output_dir: Path) -> None:
    contract_path = eval_output_dir / "evaluation_contract.json"
    if not contract_path.exists():
        raise FileNotFoundError(f"evaluation_contract.json not found: {contract_path}")
    contract = load_json(contract_path)
    expected = contract.get("expected_pages")
    evaluated = contract.get("evaluated_pages")
    missing = contract.get("missing_pages", [])
    expected_count = len(iter_manifest())
    if expected != expected_count or evaluated != expected_count or missing:
        raise RuntimeError(
            "Incomplete Issue #120 full-68 evaluation contract: "
            f"expected_pages={expected} evaluated_pages={evaluated} "
            f"expected_count={expected_count} missing_pages={len(missing)}"
        )


def validate_detector_target(eval_output_dir: Path) -> None:
    summary = detector_summary(eval_output_dir)
    if summary is None:
        raise FileNotFoundError(f"Detector metrics not found under {eval_output_dir}")
    observed = {"tp": summary.get("tp"), "fp": summary.get("fp"), "fn": summary.get("fn")}
    if observed != TARGET_DETECTOR:
        raise RuntimeError(
            f"Detector target mismatch: observed={observed} target={TARGET_DETECTOR}"
        )


def comparison_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = load_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        return payload["summary"]
    return None


def assert_candidate_match(summary: dict[str, Any] | None, *, label: str) -> None:
    if summary is None:
        raise RuntimeError(f"{label} comparison summary is missing")
    checks = {
        "missing_historical_pages": summary.get("missing_historical_pages"),
        "missing_repro_pages": summary.get("missing_repro_pages"),
        "mismatch_pages": summary.get("mismatch_pages"),
        "total_extra_in_repro": summary.get("total_extra_in_repro"),
        "total_missing_from_repro": summary.get("total_missing_from_repro"),
    }
    if any(value != 0 for value in checks.values()):
        raise RuntimeError(f"{label} candidate-root mismatch: {checks}")


def build_generation_command(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> list[str]:
    cmd = [
        sys.executable,
        "tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py",
        "--inventory",
        str(config.inventory),
        "--exclude",
        str(config.exclude),
        "--output-root",
        str(paths.raw_candidates_root),
        "--summary-out",
        str(paths.generation_summary),
    ]
    add_param_args(cmd, GENERATION_PARAMS)
    return cmd


def build_filter_command(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> list[str]:
    cmd = [
        sys.executable,
        "tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py",
        "--inventory",
        str(config.inventory),
        "--exclude",
        str(config.exclude),
        "--candidates-root",
        str(paths.raw_candidates_root),
        "--output-root",
        str(paths.filtered_candidates_root),
        "--suggestions-root",
        str(paths.suggestions_root),
        "--summary-out",
        str(paths.filter_summary),
    ]
    add_param_args(cmd, FILTER_PARAMS)
    return cmd


def build_compare_command(*, left: Path, right: Path, output_dir: Path) -> list[str]:
    return [
        sys.executable,
        "tools/issue120/compare_filter_candidate_deltas.py",
        "--historical-dir",
        str(left),
        "--repro-dir",
        str(right),
        "--output-dir",
        str(output_dir),
    ]


def build_coverage_command(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> list[str]:
    return [
        sys.executable,
        "tools/issue120/compare_candidate_coverage.py",
        "--baseline-dir",
        str(config.baseline_dir),
        "--candidate-dir",
        str(paths.probe_rescue_candidates_root),
        "--output-dir",
        str(paths.eval_output_dir),
    ]


def build_score_eval_command(config: DenseProbeCandidateConfig, paths: DenseProbeCandidatePaths) -> list[str]:
    cmd = [
        sys.executable,
        "tools/issue120/score_candidates_then_eval_full68.py",
        "--scorer",
        config.scorer,
        "--candidates-dir",
        str(paths.probe_rescue_candidates_root),
        "--image-root",
        str(config.image_root),
        "--gt-root",
        str(config.gt_root),
        "--model-path",
        str(config.model_path),
        "--scoring-output-dir",
        str(paths.scoring_output_dir),
        "--eval-output-dir",
        str(paths.eval_output_dir),
        "--score-threshold",
        str(config.score_threshold),
        "--xdist-threshold",
        str(config.xdist_threshold),
        "--bands-from",
        str(paths.filtered_candidates_root),
    ]
    if not config.no_clean_output:
        cmd.append("--clean-output")
    if config.scorer == "pipeline" and not config.cnn_apply_nms:
        cmd.append("--disable-pipeline-nms")
    return cmd


def build_attach_provenance_command(paths: DenseProbeCandidatePaths) -> list[str]:
    return [
        sys.executable,
        "tools/issue120/attach_eval_provenance.py",
        "--output-dir",
        str(paths.eval_output_dir),
        "--results-dir",
        str(paths.scoring_output_dir),
        "--provenance-json",
        str(paths.route_provenance),
    ]


def run_issue36_generation_filter_compare(
    config: DenseProbeCandidateConfig,
    paths: DenseProbeCandidatePaths,
    *,
    command_runner: CommandRunner = run_command,
) -> dict[str, Any]:
    command_runner(build_generation_command(config, paths))
    command_runner(build_filter_command(config, paths))

    comparisons = {
        "raw": run_candidate_comparison(
            left=config.historical_raw_candidates_root,
            right=paths.raw_candidates_root,
            output_dir=paths.raw_compare_output_dir,
            label="raw",
            command_runner=command_runner,
        ),
        "filtered": run_candidate_comparison(
            left=config.historical_filtered_candidates_root,
            right=paths.filtered_candidates_root,
            output_dir=paths.filtered_compare_output_dir,
            label="filtered",
            command_runner=command_runner,
        ),
        "historical_scoring_input": run_candidate_comparison(
            left=config.historical_scoring_input_root,
            right=paths.filtered_candidates_root,
            output_dir=paths.scoring_input_compare_output_dir,
            label="historical scoring input",
            command_runner=command_runner,
        ),
    }
    if config.require_candidate_match:
        assert_candidate_match(comparisons.get("raw"), label="raw")
        assert_candidate_match(comparisons.get("filtered"), label="filtered")
        assert_candidate_match(
            comparisons.get("historical_scoring_input"),
            label="historical scoring input",
        )
    return comparisons


def run_candidate_comparison(
    *,
    left: Path,
    right: Path,
    output_dir: Path,
    label: str,
    command_runner: CommandRunner = run_command,
) -> dict[str, Any] | None:
    if not left.exists():
        print(f"Skipping {label} comparison: historical root not found: {left}", flush=True)
        return None
    command_runner(build_compare_command(left=left, right=right, output_dir=output_dir))
    return comparison_summary(output_dir / "filter_candidate_delta_summary.json")


def canonical_images(image_root: Path) -> list[Path]:
    images: list[Path] = []
    missing: list[str] = []
    for record in iter_manifest():
        path = image_root / record.score / f"{record.page}.png"
        if path.exists():
            images.append(path)
        else:
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing canonical images:\n" + "\n".join(missing))
    return images


def run_probe_rescue_candidate_generation(
    config: DenseProbeCandidateConfig,
    paths: DenseProbeCandidatePaths,
) -> int:
    detect_probe_kwargs = {
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.5,
        "scan_gap_rescue_min_ratio": 0.3,
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "divisi_rescue": True,
        "scan_center_on_peak": True,
        "max_per_band": 100,
    }
    return run_probe_scan_batch(
        images=canonical_images(config.image_root),
        output_root=paths.probe_rescue_candidates_root,
        bands_from=paths.filtered_candidates_root,
        staff_mask_dir=None,
        clef_mask_dir=None,
        ink_threshold=180,
        min_ratio=0.85,
        min_height_ratio=0.012,
        min_width_ratio=0.0001,
        detect_probe_kwargs=detect_probe_kwargs,
        skip_existing=config.skip_existing_probe_rescue,
        enable_heuristic_filters=False,
        disable_seed_splitting=config.disable_seed_splitting,
    )


def run_scoring_eval_and_coverage(
    config: DenseProbeCandidateConfig,
    paths: DenseProbeCandidatePaths,
    *,
    command_runner: CommandRunner = run_command,
) -> None:
    command_runner(build_score_eval_command(config, paths))
    command_runner(build_coverage_command(config, paths))


def build_route_provenance(
    config: DenseProbeCandidateConfig,
    paths: DenseProbeCandidatePaths,
    *,
    comparisons: dict[str, Any] | None,
) -> dict[str, Any]:
    generation_summary = load_optional_json(paths.generation_summary)
    filter_summary = load_optional_json(paths.filter_summary)
    issue36_provenance = load_optional_json(paths.issue36_route_provenance)
    stage_b_provenance = load_optional_json(paths.eval_output_dir / "stage_b_provenance.json")
    coverage_summary = load_optional_json(paths.eval_output_dir / "candidate_coverage_summary.json")

    clef_mask_resolution = None
    reason_counts = None
    if isinstance(filter_summary, dict):
        clef_mask_resolution = filter_summary.get("clef_mask_resolution")
        reason_counts = filter_summary.get("reason_counts")

    return {
        "schema_version": "pipeline.detector_routes.dense_probe_candidate.v1",
        "status": "detector_level_dense_probe_candidate_route",
        "entrypoint": "python -m src.pipeline.detector_routes.dense_probe_candidate_route",
        "issue": 151,
        "parent_issue": 120,
        "compatibility_origin": "#149 / PR #150",
        "evaluated_stage": "post_cnn_scoring_detector_intermediate",
        "pipeline_scope": {
            "level": "detector_level_partial_route",
            "includes": [
                "dense candidate/bands generation",
                "clef-mask-aware filtering",
                "probe-rescue candidate generation",
                "CNN scoring",
                "canonical detector evaluation",
            ],
            "excludes": [
                "slow HOMR/SR/OMR upstream generation",
                "full end-to-end PDF pipeline execution",
                "downstream measure numbering and measure-count evaluation",
            ],
        },
        "route": [
            "Issue #36 v12 bench inventory",
            "generate dense raw candidates with band_cluster_max_dist=25.0",
            "apply clef-mask-aware filtering",
            "verify raw/filtered/scoring-input candidate roots when references are supplied",
            "use regenerated filtered root as probe-rescue bands_from",
            "score regenerated probe-rescue candidates with current CNN scoring",
            "#134 full-68 detector evaluator",
        ],
        "inputs": {
            "inventory": str(config.inventory),
            "exclude": str(config.exclude),
            "image_root": str(config.image_root),
            "gt_root": str(config.gt_root),
            "model_path": str(config.model_path),
            "baseline_dir": str(config.baseline_dir),
            "historical_raw_candidates_root": str(config.historical_raw_candidates_root),
            "historical_filtered_candidates_root": str(config.historical_filtered_candidates_root),
            "historical_scoring_input_root": str(config.historical_scoring_input_root),
        },
        "outputs": {
            "output_root": str(config.output_root),
            "raw_candidates_root": str(paths.raw_candidates_root),
            "filtered_candidates_root": str(paths.filtered_candidates_root),
            "filter_suggestions_root": str(paths.suggestions_root),
            "probe_rescue_candidates_root": str(paths.probe_rescue_candidates_root),
            "scoring_output_dir": str(paths.scoring_output_dir),
            "eval_output_dir": str(paths.eval_output_dir),
            "route_provenance": str(paths.route_provenance),
        },
        "candidate_root_summary": {
            "issue36_raw": candidate_root_summary(paths.raw_candidates_root),
            "issue36_filtered_bands_from": candidate_root_summary(paths.filtered_candidates_root),
            "probe_rescue_regenerated_candidates": candidate_root_summary(
                paths.probe_rescue_candidates_root
            ),
            "scoring_input": candidate_root_summary(paths.scoring_output_dir),
        },
        "candidate_root_comparisons": comparisons or {},
        "issue36_provenance": issue36_provenance,
        "generation_params": GENERATION_PARAMS,
        "filter_params": FILTER_PARAMS,
        "clef_mask_filtering": {
            "enabled": True,
            "resolution": clef_mask_resolution,
            "reason_counts": reason_counts,
            "summary_path": str(paths.filter_summary),
        },
        "probe_rescue": {
            "bands_from": str(paths.filtered_candidates_root),
            "candidate_coverage_summary": coverage_summary,
        },
        "cnn_scoring": {
            "scorer": config.scorer,
            "cnn_apply_nms": config.cnn_apply_nms,
            "model_path": str(config.model_path),
            "score_threshold": config.score_threshold,
            "xdist_threshold": config.xdist_threshold,
            "stage_b_provenance": stage_b_provenance,
        },
        "detector_target": TARGET_DETECTOR,
        "detector_summary": detector_summary(paths.eval_output_dir),
        "measure_count_summary": {
            "status": "not_run_in_dense_probe_candidate_route",
            "note": (
                "Detector metrics are evaluated here. Downstream measure-count "
                "validation remains a separate artifact/provenance stream."
            ),
        },
        "scope_guards": {
            "general_pipeline_defaults_changed": False,
            "nms_policy_owner": "#142",
            "full_slow_pipeline_owner": "#141",
            "generated_outputs_under_ignored_logs": True,
            "direct_scoring_of_issue36_filtered_root_is_acceptance_route": False,
        },
        "incremental_debug": {
            "no_clean_output": config.no_clean_output,
            "skip_issue36_regeneration": config.skip_issue36_regeneration,
            "skip_probe_rescue_regeneration": config.skip_probe_rescue_regeneration,
            "skip_existing_probe_rescue": config.skip_existing_probe_rescue,
        },
        "generation_summary": generation_summary,
        "filter_summary": filter_summary,
    }


def attach_route_provenance(
    config: DenseProbeCandidateConfig,
    paths: DenseProbeCandidatePaths,
    *,
    comparisons: dict[str, Any] | None,
    command_runner: CommandRunner = run_command,
) -> None:
    provenance = build_route_provenance(config, paths, comparisons=comparisons)
    write_json(paths.route_provenance, provenance)
    command_runner(build_attach_provenance_command(paths))


def run_dense_probe_candidate_route(
    config: DenseProbeCandidateConfig,
    *,
    command_runner: CommandRunner = run_command,
) -> dict[str, Any] | None:
    paths = resolve_paths(config)
    validate_inputs(config, paths)
    clean_outputs(config, paths)
    config.output_root.mkdir(parents=True, exist_ok=True)
    effective_runner = (
        make_logged_command_runner(config.output_root / "command_logs")
        if command_runner is run_command
        else command_runner
    )

    comparisons: dict[str, Any] | None = None
    if not config.skip_issue36_regeneration:
        comparisons = run_issue36_generation_filter_compare(
            config,
            paths,
            command_runner=effective_runner,
        )

    if not config.skip_probe_rescue_regeneration:
        processed = run_probe_rescue_candidate_generation(config, paths)
        print(f"Probe-rescue regeneration processed pages: {processed}")

    run_scoring_eval_and_coverage(config, paths, command_runner=effective_runner)
    validate_complete_contract(paths.eval_output_dir)
    attach_route_provenance(config, paths, comparisons=comparisons, command_runner=effective_runner)

    if config.require_detector_target:
        validate_detector_target(paths.eval_output_dir)

    return detector_summary(paths.eval_output_dir)


def _path_from_config(config: dict[str, Any], *keys: str, default: Path | None) -> Path | None:
    value = get_nested(config, *keys, default=default)
    if value is None:
        return default
    return Path(value)


def config_from_yaml(path: Path) -> DenseProbeCandidateConfig:
    data = load_yaml(path) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config at {path} must be a mapping, got {type(data)}")
    route = data.get("dense_probe_candidate_route", data.get("reconstruction", data))
    if not isinstance(route, dict):
        raise ValueError("Dense probe-candidate route config must be a mapping.")

    scoring = route.get("scoring", {}) or {}
    if not isinstance(scoring, dict):
        raise ValueError("dense_probe_candidate_route.scoring must be a mapping.")
    workflow = route.get("workflow", {}) or {}
    if not isinstance(workflow, dict):
        raise ValueError("dense_probe_candidate_route.workflow must be a mapping.")

    return DenseProbeCandidateConfig(
        inventory=_path_from_config(route, "inventory", default=DenseProbeCandidateConfig.inventory),
        exclude=_path_from_config(route, "exclude", default=DenseProbeCandidateConfig.exclude),
        image_root=_path_from_config(route, "image_root", default=DenseProbeCandidateConfig.image_root),
        gt_root=_path_from_config(route, "gt_root", default=DenseProbeCandidateConfig.gt_root),
        model_path=_path_from_config(route, "model_path", default=DenseProbeCandidateConfig.model_path),
        baseline_dir=_path_from_config(route, "baseline_dir", default=DenseProbeCandidateConfig.baseline_dir),
        output_root=_path_from_config(route, "output_root", default=DenseProbeCandidateConfig.output_root),
        historical_raw_candidates_root=_path_from_config(
            route,
            "historical_raw_candidates_root",
            default=DenseProbeCandidateConfig.historical_raw_candidates_root,
        ),
        historical_filtered_candidates_root=_path_from_config(
            route,
            "historical_filtered_candidates_root",
            default=DenseProbeCandidateConfig.historical_filtered_candidates_root,
        ),
        historical_scoring_input_root=_path_from_config(
            route,
            "historical_scoring_input_root",
            default=DenseProbeCandidateConfig.historical_scoring_input_root,
        ),
        probe_rescue_candidates_root=_path_from_config(
            route,
            "probe_rescue_candidates_root",
            default=DenseProbeCandidateConfig.probe_rescue_candidates_root,
        ),
        scorer=str(scoring.get("scorer", DenseProbeCandidateConfig.scorer)),
        cnn_apply_nms=bool(scoring.get("cnn_apply_nms", DenseProbeCandidateConfig.cnn_apply_nms)),
        score_threshold=float(scoring.get("score_threshold", DenseProbeCandidateConfig.score_threshold)),
        xdist_threshold=float(scoring.get("xdist_threshold", DenseProbeCandidateConfig.xdist_threshold)),
        no_clean_output=bool(workflow.get("no_clean_output", DenseProbeCandidateConfig.no_clean_output)),
        skip_issue36_regeneration=bool(
            workflow.get("skip_issue36_regeneration", DenseProbeCandidateConfig.skip_issue36_regeneration)
        ),
        skip_probe_rescue_regeneration=bool(
            workflow.get(
                "skip_probe_rescue_regeneration",
                DenseProbeCandidateConfig.skip_probe_rescue_regeneration,
            )
        ),
        skip_existing_probe_rescue=bool(
            workflow.get("skip_existing_probe_rescue", DenseProbeCandidateConfig.skip_existing_probe_rescue)
        ),
        require_candidate_match=bool(
            workflow.get("require_candidate_match", DenseProbeCandidateConfig.require_candidate_match)
        ),
        require_detector_target=bool(
            workflow.get("require_detector_target", DenseProbeCandidateConfig.require_detector_target)
        ),
        disable_seed_splitting=bool(
            workflow.get("disable_seed_splitting", DenseProbeCandidateConfig.disable_seed_splitting)
        ),
    )


def config_from_args(args: argparse.Namespace) -> DenseProbeCandidateConfig:
    config = config_from_yaml(args.config) if args.config else DenseProbeCandidateConfig()
    values = config.__dict__.copy()

    overrides = {
        "inventory": args.inventory,
        "exclude": args.exclude,
        "image_root": args.image_root,
        "gt_root": args.gt_root,
        "model_path": args.model_path,
        "baseline_dir": args.baseline_dir,
        "output_root": args.output_root,
        "historical_raw_candidates_root": args.historical_raw_candidates_root,
        "historical_filtered_candidates_root": args.historical_filtered_candidates_root,
        "historical_scoring_input_root": args.historical_scoring_input_root,
        "raw_candidates_root": args.raw_candidates_root,
        "filtered_candidates_root": args.filtered_candidates_root,
        "suggestions_root": args.suggestions_root,
        "generation_summary": args.generation_summary,
        "filter_summary": args.filter_summary,
        "raw_compare_output_dir": args.raw_compare_output_dir,
        "filtered_compare_output_dir": args.filtered_compare_output_dir,
        "scoring_input_compare_output_dir": args.scoring_input_compare_output_dir,
        "probe_rescue_candidates_root": args.probe_rescue_candidates_root,
        "scoring_output_dir": args.scoring_output_dir,
        "eval_output_dir": args.eval_output_dir,
        "route_provenance": args.route_provenance,
        "scorer": args.scorer,
        "score_threshold": args.score_threshold,
        "xdist_threshold": args.xdist_threshold,
    }
    for key, value in overrides.items():
        if value is not None:
            values[key] = value

    if args.pipeline_nms is not None:
        values["cnn_apply_nms"] = args.pipeline_nms
    if args.no_clean_output:
        values["no_clean_output"] = True
    if args.skip_issue36_regeneration:
        values["skip_issue36_regeneration"] = True
    if args.skip_probe_rescue_regeneration:
        values["skip_probe_rescue_regeneration"] = True
    if args.skip_existing_probe_rescue:
        values["skip_existing_probe_rescue"] = True
    if args.require_candidate_match:
        values["require_candidate_match"] = True
    if args.no_require_candidate_match:
        values["require_candidate_match"] = False
    if args.require_detector_target:
        values["require_detector_target"] = True
    if args.disable_seed_splitting:
        values["disable_seed_splitting"] = True

    return DenseProbeCandidateConfig(**values)


def build_arg_parser(description: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description or __doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument("--exclude", type=Path, default=None)
    parser.add_argument("--image-root", type=Path, default=None)
    parser.add_argument("--gt-root", type=Path, default=None)
    parser.add_argument("--model-path", type=Path, default=None)
    parser.add_argument("--baseline-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--historical-raw-candidates-root", type=Path, default=None)
    parser.add_argument("--historical-filtered-candidates-root", type=Path, default=None)
    parser.add_argument("--historical-scoring-input-root", type=Path, default=None)
    parser.add_argument("--raw-candidates-root", type=Path, default=None)
    parser.add_argument("--filtered-candidates-root", type=Path, default=None)
    parser.add_argument("--suggestions-root", type=Path, default=None)
    parser.add_argument("--generation-summary", type=Path, default=None)
    parser.add_argument("--filter-summary", type=Path, default=None)
    parser.add_argument("--raw-compare-output-dir", type=Path, default=None)
    parser.add_argument("--filtered-compare-output-dir", type=Path, default=None)
    parser.add_argument("--scoring-input-compare-output-dir", type=Path, default=None)
    parser.add_argument("--probe-rescue-candidates-root", type=Path, default=None)
    parser.add_argument("--scoring-output-dir", type=Path, default=None)
    parser.add_argument("--eval-output-dir", type=Path, default=None)
    parser.add_argument("--route-provenance", type=Path, default=None)
    parser.add_argument("--scorer", choices=["pipeline", "legacy"], default=None)
    parser.add_argument(
        "--pipeline-nms",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Explicit CNN NMS setting. Issue #120 dense route uses --no-pipeline-nms.",
    )
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument("--xdist-threshold", type=float, default=None)
    parser.add_argument("--no-clean-output", action="store_true")
    parser.add_argument("--skip-issue36-regeneration", action="store_true")
    parser.add_argument("--skip-probe-rescue-regeneration", action="store_true")
    parser.add_argument("--skip-existing-probe-rescue", action="store_true")
    parser.add_argument("--require-candidate-match", action="store_true")
    parser.add_argument("--no-require-candidate-match", action="store_true")
    parser.add_argument("--require-detector-target", action="store_true")
    parser.add_argument("--disable-seed-splitting", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    config = config_from_args(args)
    summary = run_dense_probe_candidate_route(config)
    paths = resolve_paths(config)
    print(f"Dense probe-candidate route complete: {paths.eval_output_dir}")
    if summary:
        print(
            "Detector: "
            f"TP={summary.get('tp')} FP={summary.get('fp')} FN={summary.get('fn')} "
            f"Pred={summary.get('pred')} GT={summary.get('gt')}"
        )


if __name__ == "__main__":
    main()
