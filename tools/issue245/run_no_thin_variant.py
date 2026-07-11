#!/usr/bin/env python3
"""Run an Issue #245 in-process HOMR variant with thin-barline augmentation disabled."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.issue245.homr_route_analysis import compare_record_sets, load_prediction_records
from tools.issue245.run_focused_homr_probe import detection_path, write_json

DEFAULT_OUTPUT_ROOT = Path("logs/issue245_focused_homr_probe/page001")
DEFAULT_RUN_ID = "issue245_focused_baseline"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_images(provenance_path: Path) -> list[Path]:
    provenance = load_json(provenance_path)
    records = provenance.get("images", []) if isinstance(provenance, dict) else []
    images = [
        Path(record["path"]).resolve()
        for record in records
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    ]
    if not images:
        raise ValueError(f"No input images recorded in {provenance_path}")
    missing = [path for path in images if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing image(s): " + ", ".join(map(str, missing)))
    return images


def run_no_thin_child(
    repo_root: Path,
    images: list[Path],
    variant_root: Path,
    run_id: str,
) -> int:
    from src.homr_eval_scripts.core import predictor as predictor_module
    from src.pipeline.detection.hybrid import HybridDetector

    original_detector = predictor_module.detect_thin_vertical_runs
    predictor_module.detect_thin_vertical_runs = lambda *_args, **_kwargs: []
    try:
        detector = HybridDetector(
            det_cfg={
                "hybrid_output_root": str(variant_root),
                "enable_sr": False,
                "enable_cache": True,
                "write_staff_positions": True,
                "enable_debug": False,
            },
            images=images,
            run_id=run_id,
            project_root=repo_root,
            dry_run=False,
            skip_existing=False,
        )
        baseline_root = variant_root / run_id / "baseline"
        detector._run_homr_in_process(baseline_root, enable_sr=False)
    finally:
        predictor_module.detect_thin_vertical_runs = original_detector
    return 0


def run_logged(command: list[str], log_path: Path, *, cwd: Path) -> int:
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
    return completed.returncode


def build_page_report(
    output_root: Path,
    run_id: str,
    image: Path,
) -> dict[str, Any]:
    production_path = detection_path(
        output_root / "in_process", run_id, image, in_process=True
    )
    evaluator_path = detection_path(
        output_root / "evaluator", run_id, image, in_process=False
    )
    no_thin_path = detection_path(
        output_root / "no_thin", run_id, image, in_process=True
    )
    paths = {
        "production_in_process": production_path,
        "evaluator": evaluator_path,
        "in_process_no_thin": no_thin_path,
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        return {"status": "missing_detection_artifact", "paths": paths, "missing": missing}

    production = load_prediction_records(production_path)
    evaluator = load_prediction_records(evaluator_path)
    no_thin = load_prediction_records(no_thin_path)
    return {
        "status": "compared",
        "paths": {name: str(path) for name, path in paths.items()},
        "comparisons": {
            "production_vs_evaluator": compare_record_sets(
                "production_in_process", production, "evaluator", evaluator
            ),
            "no_thin_vs_evaluator": compare_record_sets(
                "in_process_no_thin", no_thin, "evaluator", evaluator
            ),
            "production_vs_no_thin": compare_record_sets(
                "production_in_process", production, "in_process_no_thin", no_thin
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--image", action="append", default=[], help=argparse.SUPPRESS)
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    output_root = (repo_root / args.output_root).resolve()
    try:
        output_root.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("--output-root must be inside the repository") from exc

    if args.child:
        images = [Path(value).resolve() for value in args.image]
        return run_no_thin_child(repo_root, images, output_root / "no_thin", args.run_id)

    provenance_path = output_root / "runtime_provenance.json"
    if not provenance_path.is_file():
        raise FileNotFoundError(provenance_path)
    images = load_images(provenance_path)

    variant_root = output_root / "no_thin"
    if variant_root.exists():
        if not args.force:
            raise FileExistsError(f"Variant output exists; pass --force: {variant_root}")
        shutil.rmtree(variant_root)

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--output-root",
        str(output_root),
        "--run-id",
        args.run_id,
    ]
    for image in images:
        command.extend(["--image", str(image)])
    returncode = run_logged(command, output_root / "no_thin.log", cwd=repo_root)

    report = {
        "schema_version": "issue245.homr_no_thin_variant.v1",
        "purpose": (
            "Test whether in-process thin-barline augmentation explains the current "
            "baseline HOMR divergence."
        ),
        "production_default_changed": False,
        "variant": {
            "name": "in_process_no_thin",
            "implementation": (
                "Temporarily replace predictor.detect_thin_vertical_runs with an empty "
                "result in the isolated child process."
            ),
            "returncode": returncode,
            "log": str(output_root / "no_thin.log"),
        },
        "pages": {
            image.stem: build_page_report(output_root, args.run_id, image)
            for image in images
        },
    }
    report_path = output_root / "focused_homr_no_thin_report.json"
    write_json(report_path, report)

    print("Issue #245 no-thin HOMR variant")
    print(f"Variant exit: {returncode}")
    for stem, page in report["pages"].items():
        print(f"Page {stem}: {page.get('status')}")
        if page.get("status") == "compared":
            for name, comparison in page["comparisons"].items():
                print(
                    f"  {name}: left={comparison['left_summary']['count']} "
                    f"right={comparison['right_summary']['count']} "
                    f"matched={comparison['matched_count']} "
                    f"left_only={comparison['left_only_summary']['count']} "
                    f"right_only={comparison['right_only_summary']['count']}"
                )
    print(f"Report: {report_path.relative_to(repo_root)}")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
