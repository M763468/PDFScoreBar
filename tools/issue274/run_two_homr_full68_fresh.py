#!/usr/bin/env python3
"""Run the Issue #274 two-HOMR candidate on canonical evaluation2 full68.

Each score is executed as an independent production pipeline run so page IDs,
score boundaries, numbering state, and retained-control comparison semantics are
preserved. No retained/precomputed dense candidates are injected.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from src.pipeline.core.config import load_yaml
from src.pipeline.main import run_pipeline
from tools.issue120.eval_full68_from_intermediates import SCORES
from tools.issue120.run_stage_e_full_pipeline import ResourceSampler

DEFAULT_CONFIG = Path("configs/dense_full_pipeline.yaml")
DEFAULT_SOURCE_ROOT = Path("data/evaluation2/images")
DEFAULT_LOG_ROOT = Path("logs/issue274_homr_unification_analysis")
DEFAULT_AUDIT = Path(
    "logs/issue274_homr_unification_analysis/evaluation2_gt_near_duplicate_audit_01/"
    "issue274_evaluation2_gt_near_duplicate_audit.json"
)
DEFAULT_CONTROL_ROOT = Path(
    "logs/verification/detector_full68/"
    "issue255_production_restore_full68_top_level_worker_01/production_runs"
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def canonical_pages() -> list[tuple[str, str]]:
    return [(score, page) for score, pages in SCORES.items() for page in pages]


def control_accepted_path(control_root: Path, score: str, page: str) -> Path:
    return (
        control_root
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_filtered_cnn.json"
    )


def validate_production_config(config: dict[str, Any]) -> None:
    detection = config.get("detection") or {}
    steps = config.get("steps") or {}
    required_detection = {
        "enable_sr": True,
        "sr_scale": 4,
        "homr_profile": "stage_e_verified",
        "detector_route": "dense_full_pipeline",
        "probe_use_original_images": True,
    }
    mismatches = {
        key: {"expected": expected, "actual": detection.get(key)}
        for key, expected in required_detection.items()
        if detection.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"Production detection config mismatch: {mismatches}")
    for step in (
        "detection",
        "filter_pages",
        "numbering_base",
        "mmr_overrides",
        "apply_measure_overrides",
    ):
        if steps.get(step) is not True:
            raise ValueError(f"Production config requires steps.{step}=true")


def preflight(
    *,
    source_root: Path,
    audit: Path,
    control_root: Path,
    expected_pages: int,
) -> dict[str, Any]:
    pages = canonical_pages()
    if len(pages) != expected_pages:
        raise ValueError(f"Canonical page count is {len(pages)}, expected {expected_pages}")
    missing_images = [
        str(source_root / score / f"{page}.png")
        for score, page in pages
        if not (source_root / score / f"{page}.png").is_file()
    ]
    missing_control = [
        str(control_accepted_path(control_root, score, page))
        for score, page in pages
        if not control_accepted_path(control_root, score, page).is_file()
    ]
    if missing_images:
        raise FileNotFoundError(
            f"Missing {len(missing_images)} canonical images; first={missing_images[0]}"
        )
    if not audit.is_file():
        raise FileNotFoundError(audit)
    if missing_control:
        raise FileNotFoundError(
            f"Missing {len(missing_control)} retained control outputs; first={missing_control[0]}"
        )
    return {
        "canonical_page_count": len(pages),
        "score_count": len(SCORES),
        "source_root": str(source_root),
        "audit": str(audit),
        "control_root": str(control_root),
        "ok": True,
    }


def stage_inputs(source_root: Path, inputs_root: Path) -> list[dict[str, str]]:
    inventory: list[dict[str, str]] = []
    for score, pages in SCORES.items():
        score_root = inputs_root / score
        score_root.mkdir(parents=True, exist_ok=False)
        for page in pages:
            source = source_root / score / f"{page}.png"
            destination = score_root / f"{page}.png"
            shutil.copy2(source, destination)
            inventory.append(
                {
                    "score": score,
                    "page": page,
                    "source": str(source),
                    "staged": str(destination),
                }
            )
    return inventory


def build_score_config(
    *,
    base_config: Path,
    run_root: Path,
    score: str,
) -> Path:
    config = load_yaml(base_config)
    validate_production_config(config)
    config.setdefault("run", {})
    config.setdefault("inputs", {}).setdefault("pdf_to_images", {})
    config.setdefault("detection", {})

    config["run"]["run_id"] = score
    config["run"]["output_root"] = str(run_root / "runs")
    config["inputs"]["pdf_to_images"]["output_dir"] = str(run_root / "inputs" / score)
    config["inputs"]["pdf_to_images"]["image_glob"] = "page_*.png"
    config["detection"]["hybrid_output_root"] = str(run_root / "hybrid")

    # This gate must exercise the current production dense route itself.
    config["detection"].pop("precomputed_probe_candidates_root", None)
    config["detection"].pop("cnn_bands_from", None)

    path = run_root / "configs" / f"{score}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--control-root", type=Path, default=DEFAULT_CONTROL_ROOT)
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--expected-pages", type=int, default=68)
    parser.add_argument("--resource-sample-interval-sec", type=float, default=5.0)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    if args.resource_sample_interval_sec <= 0:
        parser.error("--resource-sample-interval-sec must be positive")

    run_started = time.perf_counter()
    run_root = (args.log_root / args.run_tag).resolve()
    if run_root.exists():
        if not args.replace:
            raise FileExistsError(
                f"Fresh run root already exists: {run_root}. Use a new --run-tag or --replace."
            )
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=False)

    base_config = args.config.resolve()
    validate_production_config(load_yaml(base_config))
    preflight_summary = preflight(
        source_root=args.source_root.resolve(),
        audit=args.audit.resolve(),
        control_root=args.control_root.resolve(),
        expected_pages=args.expected_pages,
    )
    inventory = stage_inputs(args.source_root.resolve(), run_root / "inputs")
    write_json(run_root / "input_inventory.json", inventory)
    write_json(run_root / "preflight.json", preflight_summary)

    sampler = ResourceSampler(
        output_path=run_root / "resource_samples.jsonl",
        interval_sec=args.resource_sample_interval_sec,
    )
    pipeline_started = time.perf_counter()
    completed_scores: list[str] = []
    score_runs: list[dict[str, str]] = []
    pipeline_error: dict[str, str] | None = None
    try:
        sampler.start()
        for score in SCORES:
            config_path = build_score_config(
                base_config=base_config,
                run_root=run_root,
                score=score,
            )
            run_dir = run_pipeline(
                config_path=config_path,
                run_id=score,
                output_root=run_root / "runs",
                dry_run=False,
                validate_only=False,
                skip_existing=False,
                page_limit=None,
            )
            manifest = run_dir / "manifest.json"
            if not manifest.is_file():
                raise FileNotFoundError(manifest)
            completed_scores.append(score)
            score_runs.append(
                {
                    "score": score,
                    "config": str(config_path),
                    "run_dir": str(run_dir),
                    "manifest": str(manifest),
                }
            )
    except Exception as error:  # noqa: BLE001
        pipeline_error = {"error_type": type(error).__name__, "error": str(error)}
        raise
    finally:
        resource_summary = sampler.stop()
        write_json(
            run_root / "two_homr_full68_runtime_summary.json",
            {
                "schema_version": "issue274.two_homr_full68_fresh_runtime.v2",
                "run_tag": args.run_tag,
                "run_root": str(run_root),
                "completed_scores": completed_scores,
                "score_runs": score_runs,
                "pipeline_duration_sec": time.perf_counter() - pipeline_started,
                "total_duration_sec": time.perf_counter() - run_started,
                "pipeline_error": pipeline_error,
                "resource_monitor": resource_summary,
            },
        )

    verify_command = [
        sys.executable,
        "tools/issue274/verify_two_homr_full68_fresh.py",
        "--workspace",
        str(Path.cwd()),
        "--run-root",
        str(run_root),
        "--expected-pages",
        str(args.expected_pages),
        "--audit",
        str(args.audit.resolve()),
        "--control-root",
        str(args.control_root.resolve()),
        "--gt-root",
        str(args.gt_root.resolve()),
    ]
    result = subprocess.run(verify_command, cwd=Path.cwd(), check=False)
    final_summary = {
        "schema_version": "issue274.two_homr_full68_fresh_run.v2",
        "status": "completed" if result.returncode == 0 else "gate_failed",
        "run_tag": args.run_tag,
        "run_root": str(run_root),
        "runtime_summary": str(run_root / "two_homr_full68_runtime_summary.json"),
        "gate_summary": str(run_root / "two_homr_full68_fresh_summary.json"),
        "gate_returncode": result.returncode,
    }
    write_json(run_root / "run_summary.json", final_summary)
    print(json.dumps(final_summary, indent=2, ensure_ascii=False))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
