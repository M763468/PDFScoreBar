#!/usr/bin/env python3
"""Screen late x4 injection boundaries for Issue #372 using retained artifacts.

No inference is run. For each current control stage (raw, filtered, rescue), this
tool asks:

  If current-x4 HOMR boxes that are not represented at IoU > 0.5 were added
  *after* this stage's existing generation, how many x4 boxes would be added,
  and which known Issue #372 residual GTs would gain a matching x4 box?

This separates hybrid-seed side effects from direct x4 candidate value and helps
choose the narrowest candidate-boundary counterfactual.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
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

IOU_THRESHOLD = 0.5


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


def _legacy_match(box: Sequence[int], gt: Sequence[int]) -> bool:
    return is_barline_match(
        box,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _represented(
    query: Sequence[int],
    boxes: Sequence[Sequence[int]],
    *,
    iou_threshold: float = IOU_THRESHOLD,
) -> bool:
    return any(barline_iou(query, box) > iou_threshold for box in boxes)


def _page_file(root: Path, record: full68_eval.PageRecord) -> Path:
    path = full68_eval.find_page_file(
        root,
        record,
        "pipeline2_no_peak_candidates.json",
    )
    if path is None or not path.is_file():
        raise FileNotFoundError(
            f"Missing candidates for {record.score}/{record.page} under {root}"
        )
    return path


def _stage_boxes(root: Path, record: full68_eval.PageRecord) -> list[tuple[int, int, int, int]]:
    path = _page_file(root, record)
    return [
        _norm(box)
        for box in full68_eval.boxes_from_candidates(_load_json(path))
    ]


def _targets(stage_trace: Mapping[str, Any], residual_details: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[int, int, int, int]]] = set()

    for row in stage_trace.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        if row.get("current_first_loss_stage") != "hybrid":
            continue
        key = (
            str(row["score"]),
            str(row["page"]),
            _norm(row["gt_bbox"]),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "score": key[0],
                "page": key[1],
                "gt_bbox": list(key[2]),
                "kind": "original_hybrid_loss",
            }
        )

    for row in residual_details.get("fallback_fn_rows", []):
        if not isinstance(row, Mapping):
            continue
        if row.get("also_d27_fn") is True:
            continue
        if row.get("classification") != "greedy_competition_merged_multi_gt_final":
            continue
        key = (
            str(row["score"]),
            str(row["page"]),
            _norm(row["gt_bbox"]),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "score": key[0],
                "page": key[1],
                "gt_bbox": list(key[2]),
                "kind": "new_merged_double_fn",
            }
        )

    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    stage_trace_path = args.stage_trace.resolve()
    residual_details_path = args.residual_details.resolve()
    output = args.output.resolve()

    for path in (
        run_root,
        issue43_repo_root,
        stage_trace_path,
        residual_details_path,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    stage_roots = {
        "raw": run_root / "control" / "aggregate_raw_candidates",
        "filtered": run_root / "control" / "aggregate_filtered_candidates",
        "rescue": run_root / "control" / "aggregate_probe_output",
    }
    for root in stage_roots.values():
        if not root.is_dir():
            raise FileNotFoundError(root)

    stage_trace = _load_json(stage_trace_path)
    residual_details = _load_json(residual_details_path)
    if not isinstance(stage_trace, Mapping) or not isinstance(residual_details, Mapping):
        raise ValueError("Input reports must be JSON objects")
    targets = _targets(stage_trace, residual_details)
    target_map = {
        (str(row["score"]), str(row["page"]), _norm(row["gt_bbox"])): row
        for row in targets
    }

    inventories: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    page_rows: list[dict[str, Any]] = []
    stage_totals = {
        stage: {
            "injected_box_count": 0,
            "pages_with_injection": 0,
            "target_current_covered": 0,
            "target_union_covered": 0,
            "target_recovered_by_injected_x4": 0,
            "target_still_uncovered": 0,
            "target_recovery_by_kind": Counter(),
        }
        for stage in stage_roots
    }
    target_rows: list[dict[str, Any]] = []

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
        x4_boxes = [_norm(box) for box in load_json_boxes(sources["sr"])]

        stage_page: dict[str, Any] = {}
        for stage, root in stage_roots.items():
            current = _stage_boxes(root, record)
            injected = [
                x4
                for x4 in x4_boxes
                if not _represented(x4, current)
            ]
            stage_page[stage] = {
                "current_count": len(current),
                "x4_count": len(x4_boxes),
                "injected_count": len(injected),
                "injected_boxes": [list(box) for box in injected],
            }
            total = stage_totals[stage]
            total["injected_box_count"] += len(injected)
            total["pages_with_injection"] += int(bool(injected))

        page_rows.append(
            {
                "score": score,
                "page": page,
                "stages": stage_page,
            }
        )

        page_targets = [
            (key, target)
            for key, target in target_map.items()
            if key[0] == score and key[1] == page
        ]
        for key, target in page_targets:
            gt = key[2]
            target_result = {
                **target,
                "stages": {},
            }
            for stage, root in stage_roots.items():
                current = _stage_boxes(root, record)
                injected = [
                    x4
                    for x4 in x4_boxes
                    if not _represented(x4, current)
                ]
                current_covered = any(_legacy_match(box, gt) for box in current)
                injected_matches = [
                    box for box in injected if _legacy_match(box, gt)
                ]
                union_covered = current_covered or bool(injected_matches)
                recovered = (not current_covered) and bool(injected_matches)

                target_result["stages"][stage] = {
                    "current_covered": current_covered,
                    "injected_match_count": len(injected_matches),
                    "injected_matching_boxes": [list(box) for box in injected_matches],
                    "union_covered": union_covered,
                    "recovered_by_injected_x4": recovered,
                }

                total = stage_totals[stage]
                total["target_current_covered"] += int(current_covered)
                total["target_union_covered"] += int(union_covered)
                total["target_recovered_by_injected_x4"] += int(recovered)
                total["target_still_uncovered"] += int(not union_covered)
                if recovered:
                    total["target_recovery_by_kind"][str(target["kind"])] += 1

            target_rows.append(target_result)

    serializable_totals: dict[str, Any] = {}
    for stage, total in stage_totals.items():
        serializable_totals[stage] = {
            key: (
                dict(sorted(value.items()))
                if isinstance(value, Counter)
                else value
            )
            for key, value in total.items()
        }

    result = {
        "schema_version": "issue372.retained_x4_injection_screen.v1",
        "contract": {
            "retained_only": True,
            "x4_representation_rule": "not represented by current stage at barline_iou > 0.5",
            "matcher_for_target_coverage": "center_anchor, vov>=0.5, fixed xdist<=12px",
            "target_count": len(targets),
            "target_kinds": dict(
                sorted(Counter(row["kind"] for row in targets).items())
            ),
        },
        "stage_summary": serializable_totals,
        "target_rows": target_rows,
        "page_rows": page_rows,
    }
    _write_json(output, result)

    print("=== Issue #372 retained x4 injection boundary screen ===")
    print(f"targets={len(targets)} kinds={result['contract']['target_kinds']}")
    for stage, summary in serializable_totals.items():
        print(f"{stage}={summary}")
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--stage-trace", type=Path, required=True)
    parser.add_argument("--residual-details", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
