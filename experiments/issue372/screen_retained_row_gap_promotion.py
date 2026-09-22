#!/usr/bin/env python3
"""Screen row-gap x4 promotion for Issue #372 using retained HOMR outputs.

The policy under test is generic:
- cluster current hybrid boxes and maintained-x4 boxes into horizontal system/staff rows;
- mark an x4 row as missing only when it has no substantial vertical overlap with
  any current-hybrid row;
- promote all x4 boxes belonging to missing rows.

No GT is used to decide which rows are promoted. GT is used only after the
policy is constructed to report recovery of the known 27 hybrid-loss residuals.

Sensitivity for min_row_count={1,2,3} is reported without selecting a winner.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.trace_retained_hybrid_components import (
    _inventory_records,
    _source_paths,
)
from src.common.barline_evaluation import is_barline_match
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

ROW_OVERLAP_THRESHOLD = 0.5


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


def _row_overlap(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    top = max(float(a["top"]), float(b["top"]))
    bottom = min(float(a["bottom"]), float(b["bottom"]))
    inter = max(0.0, bottom - top)
    ah = max(1.0, float(a["bottom"]) - float(a["top"]))
    bh = max(1.0, float(b["bottom"]) - float(b["top"]))
    return inter / min(ah, bh)


def _box_center_y(box: Sequence[int]) -> float:
    return (float(box[1]) + float(box[3])) / 2.0


def _boxes_in_row(
    boxes: Sequence[tuple[int, int, int, int]],
    row: Mapping[str, float],
) -> list[tuple[int, int, int, int]]:
    top = float(row["top"])
    bottom = float(row["bottom"])
    return [box for box in boxes if top <= _box_center_y(box) <= bottom]


def _target_rows(stage_trace: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in stage_trace.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        if row.get("current_first_loss_stage") != "hybrid":
            continue
        rows.append(
            {
                "score": str(row["score"]),
                "page": str(row["page"]),
                "gt_bbox": list(_norm(row["gt_bbox"])),
            }
        )
    if len(rows) != 27:
        raise RuntimeError(f"Expected 27 original hybrid-loss GTs, got {len(rows)}")
    return rows


def _policy_for_page(
    *,
    hybrid_boxes: list[tuple[int, int, int, int]],
    x4_boxes: list[tuple[int, int, int, int]],
    min_row_count: int,
) -> dict[str, Any]:
    hybrid_rows = build_row_stats(
        hybrid_boxes,
        cluster_max_dist=None,
        min_row_count=min_row_count,
    )
    x4_rows = build_row_stats(
        x4_boxes,
        cluster_max_dist=None,
        min_row_count=min_row_count,
    )

    missing_rows: list[dict[str, Any]] = []
    promoted: set[tuple[int, int, int, int]] = set()
    for x4_row in x4_rows:
        best_overlap = max(
            (_row_overlap(x4_row, current_row) for current_row in hybrid_rows),
            default=0.0,
        )
        if best_overlap >= ROW_OVERLAP_THRESHOLD:
            continue
        row_boxes = _boxes_in_row(x4_boxes, x4_row)
        promoted.update(row_boxes)
        missing_rows.append(
            {
                "row": {
                    "center": float(x4_row["center"]),
                    "top": float(x4_row["top"]),
                    "bottom": float(x4_row["bottom"]),
                },
                "best_current_row_overlap": best_overlap,
                "box_count": len(row_boxes),
                "boxes": [list(box) for box in sorted(row_boxes)],
            }
        )

    return {
        "hybrid_row_count": len(hybrid_rows),
        "x4_row_count": len(x4_rows),
        "missing_x4_row_count": len(missing_rows),
        "missing_x4_rows": missing_rows,
        "promoted_count": len(promoted),
        "promoted_boxes": [list(box) for box in sorted(promoted)],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    stage_trace_path = args.stage_trace.resolve()
    output = args.output.resolve()

    for required in (run_root, issue43_repo_root, stage_trace_path):
        if not required.exists():
            raise FileNotFoundError(required)

    stage_trace = _load_json(stage_trace_path)
    if not isinstance(stage_trace, Mapping):
        raise ValueError("stage trace must be a JSON object")
    targets = _target_rows(stage_trace)
    targets_by_page: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for target in targets:
        targets_by_page.setdefault((target["score"], target["page"]), []).append(target)

    configs = [1, 2, 3]
    inventories: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    page_rows: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {
        str(min_count): {
            "min_row_count": min_count,
            "pages_with_promotions": 0,
            "missing_x4_rows": 0,
            "promoted_boxes": 0,
            "target_count": len(targets),
            "target_recovered": 0,
            "target_still_missing": 0,
            "target_promoted_match_counts": Counter(),
        }
        for min_count in configs
    }

    for record in full68_eval.iter_manifest():
        score, page = record.score, record.page
        if score not in inventories:
            inventories[score] = _inventory_records(
                run_root / "inventories" / "control" / f"{score}.json"
            )
        inv = inventories[score][(score, page)]
        sources = _source_paths(
            inv,
            score=score,
            page=page,
            repo_root=issue43_repo_root,
        )
        hybrid_boxes = [_norm(box) for box in load_json_boxes(sources["hybrid"])]
        x4_boxes = [_norm(box) for box in load_json_boxes(sources["sr"])]

        configs_payload: dict[str, Any] = {}
        for min_count in configs:
            policy = _policy_for_page(
                hybrid_boxes=hybrid_boxes,
                x4_boxes=x4_boxes,
                min_row_count=min_count,
            )
            configs_payload[str(min_count)] = policy
            summary = summaries[str(min_count)]
            summary["pages_with_promotions"] += int(policy["promoted_count"] > 0)
            summary["missing_x4_rows"] += int(policy["missing_x4_row_count"])
            summary["promoted_boxes"] += int(policy["promoted_count"])

            promoted = [_norm(box) for box in policy["promoted_boxes"]]
            for target in targets_by_page.get((score, page), []):
                gt = _norm(target["gt_bbox"])
                count = sum(1 for box in promoted if _match(box, gt))
                if count:
                    summary["target_recovered"] += 1
                    summary["target_promoted_match_counts"][count] += 1
                else:
                    summary["target_still_missing"] += 1

        page_rows.append(
            {
                "score": score,
                "page": page,
                "configs": configs_payload,
            }
        )

    serializable_summaries: dict[str, Any] = {}
    for key, summary in summaries.items():
        serializable_summaries[key] = {
            name: (
                dict(sorted(value.items()))
                if isinstance(value, Counter)
                else value
            )
            for name, value in summary.items()
        }

    target_details: list[dict[str, Any]] = []
    pages_lookup = {
        (row["score"], row["page"]): row for row in page_rows
    }
    for target in targets:
        page_row = pages_lookup[(target["score"], target["page"])]
        gt = _norm(target["gt_bbox"])
        by_config = {}
        for min_count in configs:
            promoted = [
                _norm(box)
                for box in page_row["configs"][str(min_count)]["promoted_boxes"]
            ]
            matches = [list(box) for box in promoted if _match(box, gt)]
            by_config[str(min_count)] = {
                "recovered": bool(matches),
                "matching_promoted_boxes": matches,
            }
        target_details.append({**target, "configs": by_config})

    result = {
        "schema_version": "issue372.retained_row_gap_promotion.v1",
        "contract": {
            "promotion_uses_gt": False,
            "row_overlap_threshold": ROW_OVERLAP_THRESHOLD,
            "cluster_max_dist": "build_row_stats default = 0.5 * median bbox height",
            "min_row_count_sensitivity": configs,
            "target_gt_used_for_evaluation_only": True,
        },
        "summary": serializable_summaries,
        "target_details": target_details,
        "page_rows": page_rows,
    }
    _write_json(output, result)

    print("=== Issue #372 retained row-gap promotion screen ===")
    for key in map(str, configs):
        print(f"min_row_count={key}: {serializable_summaries[key]}")
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--stage-trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
