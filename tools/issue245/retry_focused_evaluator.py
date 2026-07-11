#!/usr/bin/env python3
"""Retry only the failed evaluator side of the Issue #245 focused A/B probe."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.issue245.run_focused_homr_probe import compare_routes, write_json

DEFAULT_OUTPUT_ROOT = Path("logs/issue245_focused_homr_probe/page001")
DEFAULT_RUN_ID = "issue245_focused_baseline"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_child(command: list[str], log_path: Path, *, cwd: Path) -> dict[str, Any]:
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
        "compatibility_shim": "tools/issue245/run_homr_evaluator_compat.py",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    output_root = (repo_root / args.output_root).resolve()
    try:
        output_root.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("--output-root must be inside the repository") from exc

    report_path = output_root / "focused_homr_probe_report.json"
    provenance_path = output_root / "runtime_provenance.json"
    if not report_path.is_file():
        raise FileNotFoundError(report_path)
    if not provenance_path.is_file():
        raise FileNotFoundError(provenance_path)

    report = load_json(report_path)
    provenance = load_json(provenance_path)
    image_records = provenance.get("images", []) if isinstance(provenance, dict) else []
    images = [
        Path(record["path"]).resolve()
        for record in image_records
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    ]
    missing = [path for path in images if not path.is_file()]
    if not images:
        raise ValueError(f"No input images recorded in {provenance_path}")
    if missing:
        raise FileNotFoundError("Missing image(s): " + ", ".join(map(str, missing)))

    evaluator_root = output_root / "evaluator"
    if evaluator_root.exists():
        if not args.force:
            raise FileExistsError(
                f"Evaluator output exists; pass --force to replace it: {evaluator_root}"
            )
        shutil.rmtree(evaluator_root)

    command = [
        sys.executable,
        "tools/issue245/run_homr_evaluator_compat.py",
        "--images",
        *[str(path) for path in images],
        "--output-root",
        str(evaluator_root),
        "--force-run-id",
        args.run_id,
        "--enable-segnet-cache",
    ]
    evaluator_result = run_child(
        command,
        output_root / "evaluator.log",
        cwd=repo_root,
    )

    report.setdefault("runs", {})["evaluator"] = evaluator_result
    report["comparison"] = compare_routes(
        images,
        output_root / "in_process",
        evaluator_root,
        args.run_id,
    )
    report["evaluator_retry"] = {
        "reason": (
            "Current HOMR download_weights requires use_gpu_inference, while the "
            "legacy evaluator still calls it with no arguments."
        ),
        "production_default_changed": False,
    }
    write_json(report_path, report)

    print("Issue #245 evaluator retry")
    print(f"Evaluator exit: {evaluator_result['returncode']}")
    print("Comparison:", report["comparison"]["aggregate"])
    print(f"Report: {report_path.relative_to(repo_root)}")
    return evaluator_result["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
