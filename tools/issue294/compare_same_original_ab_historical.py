#!/usr/bin/env python3
"""Compare Issue #294 A/B outputs when pinned A has no raw mask artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.issue294.compare_same_original_ab import (
    box_comparison,
    load_boxes,
    load_json,
    maintained_runtime_contract,
    mask_iou,
)


def _optional_mask_comparison(
    a_artifacts: dict[str, Any],
    b_artifacts: dict[str, Any],
    key: str,
    overlay_key: str,
) -> dict[str, Any]:
    a_value = a_artifacts.get(key)
    b_value = b_artifacts.get(key)
    if a_value and b_value:
        return {
            "available": True,
            "source": "raw_mask_artifacts",
            **mask_iou(Path(str(a_value)), Path(str(b_value))),
        }
    overlay = a_artifacts.get(overlay_key)
    return {
        "available": False,
        "reason": "historical_pinned_evaluator_does_not_materialize_raw_mask_artifact",
        "A_diagnostic_overlay": str(overlay) if overlay else None,
        "B_raw_mask": str(b_value) if b_value else None,
    }


def compare_page(page: dict[str, Any]) -> dict[str, Any]:
    a = page.get("A_pinned")
    b = page.get("B_maintained")
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError("Page summary lacks A/B payloads")
    a_artifacts = a.get("artifacts")
    worker = b.get("worker")
    if not isinstance(a_artifacts, dict) or not isinstance(worker, dict):
        raise ValueError("Page summary lacks A/B artifact payloads")
    b_artifacts = worker.get("artifacts")
    if not isinstance(b_artifacts, dict):
        raise ValueError("Maintained worker lacks artifacts")

    a_boxes = load_boxes(Path(str(a_artifacts["detections"])))
    b_boxes = load_boxes(Path(str(b_artifacts["detections"])))
    return {
        "image": page.get("image"),
        "boxes": box_comparison(a_boxes, b_boxes),
        "staff_mask": _optional_mask_comparison(
            a_artifacts, b_artifacts, "staff_mask", "staff_overlay"
        ),
        "notehead_mask": _optional_mask_comparison(
            a_artifacts, b_artifacts, "notehead_mask", "notehead_overlay"
        ),
        "maintained_runtime_contract": maintained_runtime_contract(worker),
        "timing": page.get("timing"),
    }


def run(summary_path: Path, output: Path) -> dict[str, Any]:
    summary = load_json(summary_path)
    if not isinstance(summary, dict) or summary.get("status") != "completed":
        raise ValueError(f"Invalid A/B summary: {summary_path}")
    pages_payload = summary.get("pages")
    if not isinstance(pages_payload, list) or not pages_payload:
        raise ValueError("A/B summary has no pages")
    pages = [compare_page(page) for page in pages_payload if isinstance(page, dict)]
    if len(pages) != len(pages_payload):
        raise ValueError("A/B summary contains invalid page entries")

    aggregate_timing = summary.get("aggregate_timing")
    timing_gate = bool(
        isinstance(aggregate_timing, dict)
        and aggregate_timing.get("material_speed_gate_15pct") is True
    )
    hard_contracts = all(
        page["maintained_runtime_contract"]["hard_contract_pass"] for page in pages
    )
    raw_masks_complete = all(
        page["staff_mask"].get("available") is True
        and page["notehead_mask"].get("available") is True
        for page in pages
    )
    report = {
        "schema_version": "issue294.same_original_comparison.v2",
        "status": "completed",
        "summary": str(summary_path.resolve()),
        "aggregate_timing": aggregate_timing,
        "pages": pages,
        "gates": {
            "material_speed_gate_15pct": timing_gate,
            "maintained_runtime_hard_contracts": hard_contracts,
            "eligible_for_box_geometry_review": timing_gate and hard_contracts,
            "raw_mask_comparison_complete": raw_masks_complete,
            "eligible_for_full_geometry_review": timing_gate
            and hard_contracts
            and raw_masks_complete,
        },
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.summary, args.output)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output.resolve()),
                "gates": report["gates"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
