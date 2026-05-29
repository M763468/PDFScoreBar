#!/usr/bin/env python3
"""Run Issue #163 HOMR-only phase-mode experiments on a fixed page subset.

This script is scoped to HOMR baseline/SR timing. It reuses HybridDetector
helpers so that phase-split sequential and phase-split overlap differ only in
whether baseline and SR preparation are overlapped. The canonical Stage E path
is not changed by this script.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import yaml

from src.pipeline.detection.hybrid import HybridDetector
from src.pipeline.utils.io import ensure_dir
from tools.issue120.run_stage_e_full_pipeline import ResourceSampler


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected mapping YAML: {path}")
    return data


def _merge_mapping(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_mapping(base[key], value)
        else:
            base[key] = value
    return base


def _read_images(args: argparse.Namespace) -> list[Path]:
    images: list[str] = []
    if args.image_list is not None:
        images.extend(
            line.strip()
            for line in args.image_list.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    images.extend(args.images or [])
    if not images:
        raise ValueError("Provide --image-list or --images for the fixed page subset.")
    return [Path(image) for image in images]


def _phase_result(
    *,
    phase: str,
    route: str,
    status: str,
    started_at: float,
    image_count: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "phase": phase,
        "route": route,
        "status": status,
        "duration_sec": time.perf_counter() - started_at,
    }
    if image_count is not None:
        result["image_count"] = image_count
    return result


def _run_default_sequential(
    detector: HybridDetector,
    *,
    baseline_output: Path,
    sr_output: Path,
    sr_scale: int,
    stems: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": "tools.issue163.homr_phase_mode.summary.v1",
        "mode": "default_sequential",
        "phase_results": [],
    }
    started_at = time.perf_counter()

    phase_started_at = time.perf_counter()
    if detector.skip_existing and detector._all_stems_exist(baseline_output, stems, "batch/*/*.json"):
        baseline_status = "skipped_existing"
    else:
        detector._run_homr_in_process(baseline_output, enable_sr=False)
        baseline_status = "completed"
    summary["phase_results"].append(
        _phase_result(
            phase="homr_baseline_full",
            route="homr_baseline",
            status=baseline_status,
            started_at=phase_started_at,
        )
    )

    phase_started_at = time.perf_counter()
    if detector.skip_existing and detector._all_stems_exist(sr_output, stems, "batch/*/*.json"):
        sr_status = "skipped_existing"
    else:
        detector._run_homr_in_process(sr_output, enable_sr=True, sr_scale=sr_scale)
        sr_status = "completed"
    summary["phase_results"].append(
        _phase_result(
            phase="homr_sr_full",
            route="homr_sr",
            status=sr_status,
            started_at=phase_started_at,
        )
    )

    summary["duration_sec"] = time.perf_counter() - started_at
    summary["status"] = "completed"
    return summary


def _run_phase_split_sequential(
    detector: HybridDetector,
    *,
    baseline_output: Path,
    sr_output: Path,
    sr_scale: int,
    stems: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": "tools.issue163.homr_phase_mode.summary.v1",
        "mode": "phase_split_sequential",
        "phase_results": [],
    }
    started_at = time.perf_counter()

    phase_started_at = time.perf_counter()
    if detector.skip_existing and detector._all_stems_exist(baseline_output, stems, "batch/*/*.json"):
        baseline_status = "skipped_existing"
    else:
        detector._run_homr_in_process(baseline_output, enable_sr=False)
        baseline_status = "completed"
    summary["phase_results"].append(
        _phase_result(
            phase="homr_baseline_full",
            route="homr_baseline",
            status=baseline_status,
            started_at=phase_started_at,
        )
    )

    phase_started_at = time.perf_counter()
    if detector.skip_existing and detector._all_stems_exist(sr_output, stems, "batch/*/*.json"):
        sr_prep_status = "skipped_existing"
        working_images: list[tuple[Path, Path, int]] = []
    else:
        working_images = detector._prepare_homr_working_images_only(
            sr_output,
            enable_sr=True,
            sr_scale=sr_scale,
            phase_label="SR preparation phase-split sequential",
        )
        sr_prep_status = "completed"
    summary["phase_results"].append(
        _phase_result(
            phase="homr_sr_preparation",
            route="homr_sr",
            status=sr_prep_status,
            started_at=phase_started_at,
            image_count=len(working_images),
        )
    )

    phase_started_at = time.perf_counter()
    if sr_prep_status == "skipped_existing":
        sr_inference_status = "skipped_existing"
    else:
        detector._run_homr_inference_on_working_images(
            sr_output,
            working_images=working_images,
            sr_phase_label="SR inference phase-split sequential",
        )
        sr_inference_status = "completed"
    summary["phase_results"].append(
        _phase_result(
            phase="homr_sr_inference",
            route="homr_sr",
            status=sr_inference_status,
            started_at=phase_started_at,
            image_count=len(working_images),
        )
    )

    summary["duration_sec"] = time.perf_counter() - started_at
    summary["status"] = "completed"
    return summary


def _run_phase_split_overlap(
    detector: HybridDetector,
    *,
    hybrid_output_dir: Path,
    baseline_output: Path,
    sr_output: Path,
    stems: list[str],
) -> dict[str, Any]:
    result = detector._run_homr_inprocess_sr_prep_baseline_overlap_experiment(
        experiment_cfg={
            "enabled": True,
            "mode": "inprocess_sr_prep_baseline_overlap",
            "max_workers": 2,
        },
        hybrid_output_dir=hybrid_output_dir,
        baseline_output=baseline_output,
        sr_output=sr_output,
        stems=stems,
        enable_sr=True,
    )
    summary = dict(result.get("summary") or {})
    summary["schema_version"] = "tools.issue163.homr_phase_mode.summary.v1"
    summary["mode"] = "phase_split_overlap"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        required=True,
        choices=["default_sequential", "phase_split_sequential", "phase_split_overlap"],
    )
    parser.add_argument("--config", type=Path, default=Path("configs/issue120_stage_e_full_pipeline.yaml"))
    parser.add_argument("--config-override", type=Path)
    parser.add_argument("--image-list", type=Path)
    parser.add_argument("--images", nargs="*")
    parser.add_argument("--output-root", type=Path, default=Path("logs/issue163_homr_phase_abcs"))
    parser.add_argument("--run-id")
    parser.add_argument("--resource-sample-interval-sec", type=float, default=1.0)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = _load_yaml(args.config)
    if args.config_override is not None:
        _merge_mapping(config, _load_yaml(args.config_override))
    det_cfg = dict(config.get("detection") or {})
    det_cfg["enable_sr"] = True
    det_cfg["hybrid_output_root"] = str(args.output_root)

    images = _read_images(args)
    run_id = args.run_id or args.mode
    project_root = Path.cwd()
    hybrid_output_dir = args.output_root / run_id
    baseline_output = hybrid_output_dir / "baseline"
    sr_output = hybrid_output_dir / "sr"
    ensure_dir(hybrid_output_dir)
    stems = [path.stem for path in images]

    detector = HybridDetector(
        det_cfg=det_cfg,
        images=images,
        run_id=run_id,
        project_root=project_root,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
    )

    sampler = ResourceSampler(
        output_path=hybrid_output_dir / "resource_samples.jsonl",
        interval_sec=args.resource_sample_interval_sec,
    )
    started_at = time.perf_counter()
    sampler.start()
    try:
        if args.mode == "default_sequential":
            homr_summary = _run_default_sequential(
                detector,
                baseline_output=baseline_output,
                sr_output=sr_output,
                sr_scale=int(det_cfg.get("sr_scale", 2)),
                stems=stems,
            )
        elif args.mode == "phase_split_sequential":
            homr_summary = _run_phase_split_sequential(
                detector,
                baseline_output=baseline_output,
                sr_output=sr_output,
                sr_scale=int(det_cfg.get("sr_scale", 2)),
                stems=stems,
            )
        elif args.mode == "phase_split_overlap":
            homr_summary = _run_phase_split_overlap(
                detector,
                hybrid_output_dir=hybrid_output_dir,
                baseline_output=baseline_output,
                sr_output=sr_output,
                stems=stems,
            )
        else:  # pragma: no cover - argparse guards this.
            raise AssertionError(args.mode)
    finally:
        resource_summary = sampler.stop()

    homr_summary.update(
        {
            "image_count": len(images),
            "image_list": [str(path) for path in images],
            "config_path": str(args.config),
            "config_override_path": str(args.config_override) if args.config_override else None,
            "output_root": str(args.output_root),
            "run_id": run_id,
            "total_wall_duration_sec": time.perf_counter() - started_at,
        }
    )
    homr_summary_path = hybrid_output_dir / "homr_phase_mode_summary.json"
    homr_summary_path.write_text(json.dumps(homr_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    runtime_summary = {
        "schema_version": "tools.issue163.homr_phase_mode.runtime_summary.v1",
        "mode": args.mode,
        "run_id": run_id,
        "image_count": len(images),
        "duration_sec": time.perf_counter() - started_at,
        "homr_summary_path": str(homr_summary_path),
        "homr_summary": homr_summary,
        "resource_summary_path": str(sampler.summary_path),
        "resource_summary": resource_summary,
    }
    runtime_summary_path = hybrid_output_dir / "runtime_summary.json"
    runtime_summary_path.write_text(
        json.dumps(runtime_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(runtime_summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
