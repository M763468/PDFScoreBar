#!/usr/bin/env python3
"""Compare current HOMR baseline routes with the retained historical baseline.

This Issue #245 investigation tool runs only against the canonical
Va_Prokofiev_Symphony1/page_001 image. The retained historical artifact is
read-only comparison evidence and is never used as a production detector input.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.issue245.homr_route_analysis import compare_record_sets, load_prediction_records
from tools.issue245.run_focused_homr_probe import (
    collect_provenance,
    detection_path,
    sha256_file,
    write_json,
)

DEFAULT_IMAGE = Path("data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png")
DEFAULT_HISTORICAL_ROOT = Path(
    "logs/hybrid_pipeline_bench/"
    "eval2_Va_Prokofiev_Symphony1_page_001_20260131_103421"
)
DEFAULT_OUTPUT_ROOT = Path(
    "logs/issue245_focused_homr_probe/canonical_va_prokofiev_symphony1_page001"
)
DEFAULT_RUN_ID = "issue245_canonical_baseline"
EXPECTED_CANONICAL_SHA256 = "48e073dd8184495b9751ad62e85a872bc93cce751ba0a8c988300f7c5ae444a6"


def run_logged(command: list[str], log_path: Path, *, cwd: Path) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as stream:
        stream.write("command: " + " ".join(command) + "\n\n")
        stream.flush()
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
        stream.write(f"\nexit_status={completed.returncode}\n")
    return {
        "command": command,
        "returncode": completed.returncode,
        "log": str(log_path),
    }


def resolve_inside_repo(repo_root: Path, value: Path, *, label: str) -> Path:
    path = (repo_root / value).resolve()
    try:
        path.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"{label} must be inside the repository: {path}") from exc
    return path


def discover_historical_detection(historical_root: Path) -> Path:
    expected = (
        historical_root
        / "baseline"
        / "page_001"
        / "page_001"
        / "page_001_detections.json"
    )
    if expected.is_file():
        return expected

    candidates = sorted(historical_root.glob("baseline/**/*_detections.json"))
    candidates = [path for path in candidates if path.is_file()]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            "Historical baseline detection JSON was not found under "
            f"{historical_root / 'baseline'}"
        )
    raise RuntimeError(
        "Historical baseline detection JSON is ambiguous: "
        + ", ".join(str(path) for path in candidates)
    )


def current_detection_paths(output_root: Path, run_id: str, image: Path) -> dict[str, Path]:
    return {
        "production_in_process": detection_path(
            output_root / "in_process", run_id, image, in_process=True
        ),
        "evaluator_default_thin": detection_path(
            output_root / "evaluator", run_id, image, in_process=False
        ),
        "in_process_no_thin": detection_path(
            output_root / "no_thin", run_id, image, in_process=True
        ),
    }


def build_comparison_report(
    historical_detection: Path,
    current_paths: dict[str, Path],
) -> dict[str, Any]:
    missing = [str(path) for path in current_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing current detection artifact(s): " + ", ".join(missing))

    historical = load_prediction_records(historical_detection)
    current = {
        name: load_prediction_records(path) for name, path in current_paths.items()
    }
    return {
        "historical_detection": str(historical_detection),
        "historical_count": len(historical),
        "current_detections": {name: str(path) for name, path in current_paths.items()},
        "comparisons": {
            name: compare_record_sets("historical", historical, name, records)
            for name, records in current.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--historical-root", type=Path, default=DEFAULT_HISTORICAL_ROOT)
    parser.add_argument("--historical-detection", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    image = resolve_inside_repo(repo_root, args.image, label="--image")
    historical_root = resolve_inside_repo(
        repo_root, args.historical_root, label="--historical-root"
    )
    output_root = resolve_inside_repo(repo_root, args.output_root, label="--output-root")

    if not image.is_file():
        raise FileNotFoundError(image)
    image_sha256 = sha256_file(image)
    if image_sha256 != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError(
            "Canonical image hash mismatch: "
            f"expected={EXPECTED_CANONICAL_SHA256} actual={image_sha256} path={image}"
        )

    if args.historical_detection is None:
        historical_detection = discover_historical_detection(historical_root)
    else:
        historical_detection = resolve_inside_repo(
            repo_root, args.historical_detection, label="--historical-detection"
        )
        if not historical_detection.is_file():
            raise FileNotFoundError(historical_detection)

    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; pass --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    write_json(output_root / "runtime_provenance.json", collect_provenance(repo_root, [image]))

    commands = {
        "production_in_process": [
            sys.executable,
            "tools/issue245/run_focused_homr_probe.py",
            "_run-in-process",
            "--output-root",
            str(output_root / "in_process"),
            "--run-id",
            args.run_id,
            "--image",
            str(image),
        ],
        "evaluator_default_thin": [
            sys.executable,
            "tools/issue245/run_homr_evaluator_compat.py",
            "--images",
            str(image),
            "--output-root",
            str(output_root / "evaluator"),
            "--force-run-id",
            args.run_id,
            "--enable-segnet-cache",
        ],
        "in_process_no_thin": [
            sys.executable,
            "tools/issue245/run_no_thin_variant.py",
            "--child",
            "--output-root",
            str(output_root),
            "--run-id",
            args.run_id,
            "--image",
            str(image),
        ],
    }
    runs: dict[str, Any] = {}
    for name, command in commands.items():
        runs[name] = run_logged(command, output_root / f"{name}.log", cwd=repo_root)
        if runs[name]["returncode"] != 0:
            report = {
                "schema_version": "issue245.canonical_historical_probe.v1",
                "status": "route_failed",
                "production_default_changed": False,
                "failed_route": name,
                "input": {
                    "path": str(image),
                    "sha256": image_sha256,
                    "expected_sha256": EXPECTED_CANONICAL_SHA256,
                },
                "historical_detection": str(historical_detection),
                "runs": runs,
            }
            write_json(output_root / "canonical_historical_probe_report.json", report)
            return int(runs[name]["returncode"])

    paths = current_detection_paths(output_root, args.run_id, image)
    comparison = build_comparison_report(historical_detection, paths)
    report = {
        "schema_version": "issue245.canonical_historical_probe.v1",
        "status": "compared",
        "purpose": (
            "Compare retained historical baseline HOMR with three freshly generated "
            "current routes on the exact canonical image."
        ),
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "input": {
            "path": str(image),
            "sha256": image_sha256,
            "expected_sha256": EXPECTED_CANONICAL_SHA256,
        },
        "historical_root": str(historical_root),
        "runs": runs,
        "comparison": comparison,
    }
    report_path = output_root / "canonical_historical_probe_report.json"
    write_json(report_path, report)

    print("Issue #245 canonical historical HOMR probe")
    print(f"Historical count: {comparison['historical_count']}")
    for name, result in comparison["comparisons"].items():
        print(
            f"{name}: current={result['right_summary']['count']} "
            f"matched={result['matched_count']} "
            f"historical_only={result['left_only_summary']['count']} "
            f"current_only={result['right_only_summary']['count']}"
        )
    print(f"Report: {report_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
