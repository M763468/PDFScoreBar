#!/usr/bin/env python3
"""Inspect x4 support geometry for the three merged-double residuals in Issue #372."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.trace_retained_hybrid_components import (
    _inventory_records,
    _source_paths,
)
from src.common import barline_iou
from src.common.barline_evaluation import is_barline_match
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _match(box: Sequence[int], gt: Sequence[int]) -> bool:
    return is_barline_match(
        box,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _page_file(root: Path, score: str, page: str, filename: str) -> Path:
    record = full68_eval.PageRecord(score=score, page=page)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{score}/{page}: {filename} under {root}")
    return path


def _candidate_boxes(root: Path, score: str, page: str) -> list[tuple[int, int, int, int]]:
    path = _page_file(root, score, page, "pipeline2_no_peak_candidates.json")
    return [_norm(box) for box in full68_eval.boxes_from_candidates(_load_json(path))]


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    residual_path = args.residual_details.resolve()
    output = args.output.resolve()

    for required in (run_root, issue43_repo_root, residual_path):
        if not required.exists():
            raise FileNotFoundError(required)

    residual = _load_json(residual_path)
    if not isinstance(residual, Mapping):
        raise ValueError("Residual report must be a JSON object")

    targets = [
        row
        for row in residual.get("fallback_fn_rows", [])
        if isinstance(row, Mapping)
        and row.get("also_d27_fn") is False
        and row.get("classification") == "greedy_competition_merged_multi_gt_final"
    ]
    if len(targets) != 3:
        raise RuntimeError(f"Expected 3 new merged-double residuals, got {len(targets)}")

    control_raw = run_root / "control" / "aggregate_raw_candidates"
    control_filtered = run_root / "control" / "aggregate_filtered_candidates"
    control_rescue = run_root / "control" / "aggregate_probe_output"
    for root in (control_raw, control_filtered, control_rescue):
        if not root.is_dir():
            raise FileNotFoundError(root)

    inventories: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    rows: list[dict[str, Any]] = []

    for target in targets:
        score = str(target["score"])
        page = str(target["page"])
        gt = _norm(target["gt_bbox"])

        if score not in inventories:
            inventories[score] = _inventory_records(
                run_root / "inventories" / "control" / f"{score}.json"
            )
        record = inventories[score][(score, page)]
        sources = _source_paths(
            record,
            score=score,
            page=page,
            repo_root=issue43_repo_root,
        )
        x4 = [_norm(box) for box in load_json_boxes(sources["sr"])]

        stage_payload: dict[str, Any] = {}
        for name, root in (
            ("raw", control_raw),
            ("filtered", control_filtered),
            ("rescue", control_rescue),
        ):
            current = _candidate_boxes(root, score, page)
            matching_current = [box for box in current if _match(box, gt)]
            x4_matches = [box for box in x4 if _match(box, gt)]
            details = []
            for xb in x4_matches:
                related = [
                    {
                        "current_bbox": list(cb),
                        "iou": float(barline_iou(xb, cb)),
                        "current_width": abs(cb[2] - cb[0]),
                        "x4_width": abs(xb[2] - xb[0]),
                    }
                    for cb in current
                    if barline_iou(xb, cb) > 0
                ]
                related.sort(key=lambda item: item["iou"], reverse=True)
                details.append(
                    {
                        "x4_bbox": list(xb),
                        "x4_width": abs(xb[2] - xb[0]),
                        "represented_iou_gt_0p5": any(
                            item["iou"] > 0.5 for item in related
                        ),
                        "related_current": related[:10],
                    }
                )
            stage_payload[name] = {
                "matching_current": [list(box) for box in matching_current],
                "matching_x4": [list(box) for box in x4_matches],
                "x4_details": details,
            }

        rows.append(
            {
                "score": score,
                "page": page,
                "gt_bbox": list(gt),
                "x4_source": str(sources["sr"]),
                "stages": stage_payload,
            }
        )

    result = {
        "schema_version": "issue372.merged_double_x4_geometry.v1",
        "target_count": len(rows),
        "rows": rows,
    }
    _write_json(output, result)
    print("=== Issue #372 merged-double x4 geometry ===")
    for row in rows:
        print(f"{row['score']}/{row['page']} GT={row['gt_bbox']}")
        for stage in ("raw", "filtered", "rescue"):
            p = row["stages"][stage]
            print(
                f"  {stage}: current={p['matching_current']} x4={p['matching_x4']}"
            )
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--residual-details", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
