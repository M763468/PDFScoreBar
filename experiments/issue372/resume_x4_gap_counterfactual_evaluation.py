#!/usr/bin/env python3
"""Finish Issue #372 x4-gap counterfactual evaluation from completed outputs.

Use this only when control and x4-gap dense/CNN outputs already completed but
the original runner stopped during evaluation. No detector inference, dense
reconstruction, CNN scoring, HOMR, SR, or OMR-DLN work is rerun.

The source run is treated read-only. Evaluation artifacts and the completed
comparison report are written to a separate output directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _evaluate_variant,
    _metric_delta,
)
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

EXPECTED_PAGES = 68


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _box_set(path: Path) -> set[tuple[int, int, int, int]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {tuple(int(v) for v in box) for box in load_json_boxes(path)}


def _promotion_summary(run_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for score, pages in full68_eval.SCORES.items():
        control_inventory = run_root / "inventories" / "control" / f"{score}.json"
        fallback_inventory = (
            run_root / "inventories" / "x4_gap_fallback" / f"{score}.json"
        )
        control_payload = _load_json(control_inventory)
        fallback_payload = _load_json(fallback_inventory)
        control_records = control_payload.get("records", [])
        fallback_records = fallback_payload.get("records", [])
        if not isinstance(control_records, list) or not isinstance(fallback_records, list):
            raise ValueError(f"Invalid retained inventories for {score}")

        control_by_page = {
            str(record["page"]): record
            for record in control_records
            if isinstance(record, Mapping)
        }
        fallback_by_page = {
            str(record["page"]): record
            for record in fallback_records
            if isinstance(record, Mapping)
        }
        if set(control_by_page) != set(pages) or set(fallback_by_page) != set(pages):
            raise ValueError(
                f"Retained inventory page set mismatch for {score}: "
                f"control={sorted(control_by_page)} fallback={sorted(fallback_by_page)}"
            )

        for page in pages:
            control_record = control_by_page[page]
            fallback_record = fallback_by_page[page]
            control_hybrid = Path(str(control_record["hybrid_predictions"]))
            fallback_hybrid = Path(str(fallback_record["hybrid_predictions"]))
            control_boxes = _box_set(control_hybrid)
            fallback_boxes = _box_set(fallback_hybrid)
            promoted = fallback_boxes - control_boxes
            removed = control_boxes - fallback_boxes
            if removed:
                raise RuntimeError(
                    f"Fallback unexpectedly removed current hybrid boxes for "
                    f"{score}/{page}: {len(removed)}"
                )
            rows.append(
                {
                    "score": score,
                    "page": page,
                    "current_hybrid_count": len(control_boxes),
                    "fallback_hybrid_count": len(fallback_boxes),
                    "promoted_x4_gap_count": len(promoted),
                    "promoted_boxes": [list(box) for box in sorted(promoted)],
                    "current_hybrid": str(control_hybrid),
                    "fallback_hybrid": str(fallback_hybrid),
                }
            )

    if len(rows) != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} pages, got {len(rows)}")
    return {
        "page_count": len(rows),
        "pages_with_promotions": sum(row["promoted_x4_gap_count"] > 0 for row in rows),
        "total_promoted_x4_gap_boxes": sum(
            int(row["promoted_x4_gap_count"]) for row in rows
        ),
        "per_page": rows,
    }


def _require_completed_outputs(run_root: Path) -> tuple[Path, Path]:
    control = run_root / "control" / "aggregate_probe_output"
    fallback = run_root / "x4_gap_fallback" / "aggregate_probe_output"
    for root in (control, fallback):
        if not root.is_dir():
            raise FileNotFoundError(root)
        finals = list(root.rglob("pipeline2_no_peak_filtered_cnn.json"))
        candidates = list(root.rglob("pipeline2_no_peak_candidates.json"))
        if len(finals) != EXPECTED_PAGES or len(candidates) != EXPECTED_PAGES:
            raise RuntimeError(
                f"Incomplete retained output under {root}: "
                f"finals={len(finals)} candidates={len(candidates)}"
            )
    return control, fallback


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.resolve()
    report_path = args.issue43_report.resolve()
    output_root = args.output_root.resolve()
    gt_root = args.gt_root.resolve()
    image_root = args.image_root.resolve()
    staff_units = args.staff_units_json.resolve()

    if not run_root.is_dir():
        raise FileNotFoundError(run_root)
    for path in (report_path, gt_root, image_root, staff_units):
        if not path.exists():
            raise FileNotFoundError(path)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Resume output root must be new/empty: {output_root}")

    control_probe, fallback_probe = _require_completed_outputs(run_root)
    issue43_report = _load_json(report_path)
    if not isinstance(issue43_report, Mapping):
        raise ValueError("Issue #43 report must be a JSON object")
    provenance = issue43_report.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("cnn_threshold") is None:
        raise ValueError("Issue #43 report lacks provenance.cnn_threshold")
    threshold = float(provenance["cnn_threshold"])

    # Create the resume output only after all source/preflight checks pass.
    output_root.mkdir(parents=True, exist_ok=True)

    control = {
        "name": "control",
        "aggregate_probe": str(control_probe),
    }
    fallback = {
        "name": "x4_gap_fallback",
        "aggregate_probe": str(fallback_probe),
    }

    control_eval = _evaluate_variant(
        variant=control,
        output_root=output_root,
        gt_root=gt_root,
        image_root=image_root,
        staff_units=staff_units,
        threshold=threshold,
    )
    fallback_eval = _evaluate_variant(
        variant=fallback,
        output_root=output_root,
        gt_root=gt_root,
        image_root=image_root,
        staff_units=staff_units,
        threshold=threshold,
    )

    variants = issue43_report.get("variants")
    full_width = variants.get("full_width") if isinstance(variants, Mapping) else None
    expected_summary = (
        full_width.get("detector_summary")
        if isinstance(full_width, Mapping)
        else None
    )
    control_reproduces = (
        isinstance(expected_summary, Mapping)
        and dict(expected_summary) == control_eval["current_unit"]
    )

    promotions = _promotion_summary(run_root)
    report = {
        "schema_version": "issue372.retained_x4_gap_counterfactual_resume.v1",
        "source_run_root": str(run_root),
        "resume_scope": {
            "reran_homr": False,
            "reran_sr": False,
            "reran_omr_dln": False,
            "reran_dense_reconstruction": False,
            "reran_cnn_scoring": False,
            "evaluation_only": True,
            "legacy_matcher": "center_anchor, vov>=0.5, fixed xdist<=12px",
            "current_matcher": "center_anchor, vov>=0.5, xdist<=0.5*unit_size",
            "cnn_threshold": threshold,
        },
        "promotion_summary": promotions,
        "control": {
            "evaluation": control_eval,
            "issue43_expected_current_unit": dict(expected_summary)
            if isinstance(expected_summary, Mapping)
            else None,
            "reproduces_issue43_full_width_summary": control_reproduces,
        },
        "x4_gap_fallback": {
            "evaluation": fallback_eval,
            "delta_vs_control": {
                mode: _metric_delta(fallback_eval[mode], control_eval[mode])
                for mode in ("legacy_fixed12", "current_unit")
            },
        },
    }
    output = output_root / "counterfactual_resume_report.json"
    _write_json(output, report)

    print("=== Issue #372 x4-gap evaluation resume ===")
    print(f"source_run_root={run_root}")
    print(
        "promotions="
        f"{promotions['total_promoted_x4_gap_boxes']} "
        f"pages={promotions['pages_with_promotions']}"
    )
    print(f"control_reproduces_issue43_full_width_summary={control_reproduces}")
    for mode in ("legacy_fixed12", "current_unit"):
        print(f"{mode} control={control_eval[mode]}")
        print(f"{mode} fallback={fallback_eval[mode]}")
        print(
            f"{mode} delta="
            f"{report['x4_gap_fallback']['delta_vs_control'][mode]}"
        )
    print(f"OUTPUT={output}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--issue43-report", type=Path, required=True)
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=ROOT / "data/evaluation2/annotations",
    )
    parser.add_argument(
        "--image-root",
        type=Path,
        default=ROOT / "data/evaluation2/images",
    )
    parser.add_argument(
        "--staff-units-json",
        type=Path,
        default=ROOT / "data/evaluation2/staff_units.json",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
