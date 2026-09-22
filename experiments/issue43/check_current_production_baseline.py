#!/usr/bin/env python3
"""Compare saved current-production full68 outputs with Issue #43 full-width reconstruction."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _host_path(value: str | Path) -> Path:
    path = Path(value)
    try:
        return ROOT / path.relative_to("/workspace")
    except ValueError:
        return path


def _load_json(path: str | Path) -> Any:
    return json.loads(_host_path(path).read_text(encoding="utf-8"))


def _box_set(path: Path) -> set[tuple[int, int, int, int]]:
    payload = _load_json(path)
    if isinstance(payload, Mapping):
        payload = payload.get("predictions", payload.get("boxes", payload))
    if not isinstance(payload, list):
        return set()
    result: set[tuple[int, int, int, int]] = set()
    for item in payload:
        box: Any = item
        if isinstance(item, Mapping):
            box = (
                item.get("barline_location")
                or item.get("orig_bbox")
                or item.get("pred_bbox")
                or item.get("bbox")
            )
        if isinstance(box, list) and len(box) == 4:
            result.add(tuple(int(round(float(value))) for value in box))
    return result


def _evaluation_args(
    results_dir: Path,
    output_dir: Path,
    threshold: float,
    image_root: Path,
) -> Namespace:
    from tools.issue120 import eval_full68_from_intermediates as full68_eval

    return Namespace(
        results_dir=str(results_dir),
        gt_root=str(ROOT / "data/evaluation2/annotations"),
        output_dir=str(output_dir),
        scored_file="pipeline2_no_peak_filtered_cnn.json",
        candidates_file="pipeline2_no_peak_candidates.json",
        score_threshold=threshold,
        rule_name="center_anchor",
        vov_threshold=0.5,
        staff_units_json=str(ROOT / "data/evaluation2/staff_units.json"),
        image_root=str(image_root),
        xdist_unit_ratio=full68_eval.CENTER_ANCHOR_XDIST_UNIT_RATIO,
        legacy_fixed_12px=False,
        allow_partial=False,
        measure_summary_json=None,
    )


def _collect_production_outputs(report: Mapping[str, Any], destination: Path) -> int:
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)

    copied = 0
    production_runs = report["provenance"].get("production_runs", [])
    if not production_runs:
        raise ValueError(
            "Report has no fresh production_runs; this check requires the original full68 run."
        )

    for run in production_runs:
        source = _host_path(run["probe_output_dir"])
        if not source.is_dir():
            raise FileNotFoundError(source)
        for filtered in sorted(source.rglob("pipeline2_no_peak_filtered_cnn.json")):
            page_dir = filtered.parent
            target = destination / page_dir.name
            if target.exists():
                raise RuntimeError(f"Duplicate production page directory: {page_dir.name}")
            target.mkdir(parents=True)
            for filename in (
                "pipeline2_no_peak_candidates.json",
                "pipeline2_no_peak_scored.json",
                "pipeline2_no_peak_filtered_cnn.json",
            ):
                src = page_dir / filename
                if src.is_file():
                    shutil.copy2(src, target / filename)
            copied += 1
    return copied


def run(report_path: Path, *, image_root: Path) -> dict[str, Any]:
    from tools.issue120 import eval_full68_from_intermediates as full68_eval

    report = _load_json(report_path)
    threshold = float(report["provenance"]["cnn_threshold"])
    run_root = report_path.parent
    production_root = run_root / "production_baseline_probe_output"
    copied = _collect_production_outputs(report, production_root)
    if copied != 68:
        raise RuntimeError(f"Expected 68 production output pages, copied {copied}")

    evaluation = full68_eval.evaluate(
        _evaluation_args(
            production_root,
            run_root / "production_baseline_eval",
            threshold,
            image_root,
        )
    )
    production_summary = asdict(evaluation.detector_summary)

    full_width_root = _host_path(report["variants"]["full_width"]["probe_rescue_root"])
    production_files = {
        path.parent.name: path
        for path in production_root.rglob("pipeline2_no_peak_filtered_cnn.json")
    }
    full_width_files = {
        path.parent.name: path
        for path in full_width_root.rglob("pipeline2_no_peak_filtered_cnn.json")
    }
    all_keys = sorted(set(production_files) | set(full_width_files))
    changes = []
    for key in all_keys:
        production_boxes = (
            _box_set(production_files[key]) if key in production_files else set()
        )
        full_width_boxes = (
            _box_set(full_width_files[key]) if key in full_width_files else set()
        )
        if production_boxes != full_width_boxes:
            changes.append(
                {
                    "page_dir": key,
                    "production_count": len(production_boxes),
                    "full_width_count": len(full_width_boxes),
                    "removed_in_full_width": len(production_boxes - full_width_boxes),
                    "added_in_full_width": len(full_width_boxes - production_boxes),
                }
            )

    result = {
        "production_summary": production_summary,
        "full_width_summary": report["variants"]["full_width"]["detector_summary"],
        "final_boxes_exact": not changes,
        "changed_pages": len(changes),
        "changes": changes,
    }
    output = run_root / "production_vs_full_width_check.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("=== CURRENT PRODUCTION SAVED OUTPUT ===")
    print(json.dumps(production_summary, indent=2))
    print()
    print("=== ISSUE43 FULL_WIDTH RECONSTRUCTION ===")
    print(json.dumps(result["full_width_summary"], indent=2))
    print()
    print(f"final_boxes_exact={result['final_boxes_exact']}")
    print(f"changed_pages={result['changed_pages']}")
    print(f"report={output}")
    if changes:
        for change in changes:
            print(change)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--image-root",
        type=Path,
        default=ROOT / "data/evaluation2/images",
        help="Canonical evaluation2 image root used for coordinate validation.",
    )
    args = parser.parse_args()
    run(args.report.resolve(), image_root=args.image_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
