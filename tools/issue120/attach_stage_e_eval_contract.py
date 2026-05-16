#!/usr/bin/env python3
"""Attach a machine-readable Issue #141 Stage E evaluation contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TARGET = {"tp": 3580, "fp": 0, "fn": 1}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def get_nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def infer_numbering_output(manifest: dict[str, Any], manifest_path: Path) -> Path:
    run_dir = manifest.get("run_dir")
    if isinstance(run_dir, str) and run_dir:
        return Path(run_dir) / "outputs" / "numbering_final.json"
    return manifest_path.parent / "outputs" / "numbering_final.json"


def build_contract(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_json(args.manifest)
    detector = load_json(args.eval_dir / "detector_metrics.json")
    missing_path = args.eval_dir / "missing_pages.json"
    missing_pages = load_json(missing_path) if missing_path.exists() else []
    numbering_output = args.numbering_output or infer_numbering_output(manifest, args.manifest)
    target_met = (
        detector.get("tp") == TARGET["tp"]
        and detector.get("fp") == TARGET["fp"]
        and detector.get("fn") == TARGET["fn"]
    )
    return {
        "schema_version": "issue141.stage_e_full_pipeline.v1",
        "mode": "manifest_full_pipeline_detector_eval",
        "issue": 141,
        "parent_issue": 120,
        "manifest": str(args.manifest),
        "run_id": manifest.get("run_id"),
        "run_dir": manifest.get("run_dir"),
        "eval_dir": str(args.eval_dir),
        "expected_pages": detector.get("expected_page_count"),
        "evaluated_pages": detector.get("page_count"),
        "missing_pages": missing_pages,
        "score_threshold": args.score_threshold,
        "xdist_threshold": args.xdist_threshold,
        "canonical_detector_target": TARGET,
        "target_met": {"detector": target_met},
        "cnn_apply_nms": get_nested(manifest, "config", "detection", "cnn_apply_nms"),
        "detector_summary": detector,
        "measure_count_summary": {
            "status": "not_provided",
            "note": "No canonical downstream measure-count comparator was attached.",
            "numbering_output": str(numbering_output),
            "numbering_output_exists": numbering_output.exists(),
            "net_delta": None,
            "abs_delta_sum": None,
            "delta_pages": None,
        },
        "scope_note": "Real full-pipeline Stage E run; distinct from the #151 detector-level dense route.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--numbering-output", type=Path)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    args = parser.parse_args()

    output = args.output or args.eval_dir / "evaluation_contract.json"
    write_json(output, build_contract(args))
    print(f"Wrote: {output}")


if __name__ == "__main__":
    main()
