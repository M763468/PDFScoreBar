#!/usr/bin/env python3
"""Compare historical D27-producer and current geometry for merged-double residuals."""

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
    _d27_inventory,
    _inventory_records,
    _source_paths,
)
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


def _matching(path: Path, gt: tuple[int, int, int, int]) -> list[list[int]]:
    return [
        list(_norm(box))
        for box in load_json_boxes(path)
        if _match(_norm(box), gt)
    ]


def _page_file(root: Path, score: str, page: str, filename: str) -> Path:
    record = full68_eval.PageRecord(score=score, page=page)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{score}/{page}: {filename} under {root}")
    return path


def _matching_candidates(
    root: Path,
    score: str,
    page: str,
    gt: tuple[int, int, int, int],
) -> list[list[int]]:
    path = _page_file(root, score, page, "pipeline2_no_peak_candidates.json")
    payload = _load_json(path)
    return [
        list(_norm(box))
        for box in full68_eval.boxes_from_candidates(payload)
        if _match(_norm(box), gt)
    ]


def _d27_stage_roots(d27_run_root: Path, score: str) -> dict[str, Path]:
    dense = (
        d27_run_root
        / "runs"
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
    )
    roots = {
        "raw": dense / "probe_candidates_from_inventory",
        "filtered": dense / "probe_candidates_filtered",
        "rescue": dense / "probe_rescue_candidates",
    }
    for root in roots.values():
        if not root.is_dir():
            raise FileNotFoundError(root)
    return roots


def run(args: argparse.Namespace) -> dict[str, Any]:
    d27_run_root = args.d27_run_root.resolve()
    d27_repo_root = args.d27_repo_root.resolve()
    current_run_root = args.current_run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    residual_path = args.residual_details.resolve()
    output = args.output.resolve()

    for required in (
        d27_run_root,
        d27_repo_root,
        current_run_root,
        issue43_repo_root,
        residual_path,
    ):
        if not required.exists():
            raise FileNotFoundError(required)

    residual = _load_json(residual_path)
    targets = [
        row
        for row in residual.get("fallback_fn_rows", [])
        if isinstance(row, Mapping)
        and row.get("also_d27_fn") is False
        and row.get("classification") == "greedy_competition_merged_multi_gt_final"
    ]
    if len(targets) != 3:
        raise RuntimeError(f"Expected 3 merged-double residuals, got {len(targets)}")

    d27_inv_cache: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    cur_inv_cache: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    rows: list[dict[str, Any]] = []

    current_stage_roots = {
        "raw": current_run_root / "control" / "aggregate_raw_candidates",
        "filtered": current_run_root / "control" / "aggregate_filtered_candidates",
        "rescue": current_run_root / "control" / "aggregate_probe_output",
    }
    for root in current_stage_roots.values():
        if not root.is_dir():
            raise FileNotFoundError(root)

    for target in targets:
        score = str(target["score"])
        page = str(target["page"])
        gt = _norm(target["gt_bbox"])

        if score not in d27_inv_cache:
            d27_inv_cache[score] = _inventory_records(
                _d27_inventory(d27_run_root, score)
            )
            cur_inv_cache[score] = _inventory_records(
                current_run_root / "inventories" / "control" / f"{score}.json"
            )

        d27_rec = d27_inv_cache[score][(score, page)]
        cur_rec = cur_inv_cache[score][(score, page)]
        d27_sources = _source_paths(
            d27_rec,
            score=score,
            page=page,
            repo_root=d27_repo_root,
        )
        cur_sources = _source_paths(
            cur_rec,
            score=score,
            page=page,
            repo_root=issue43_repo_root,
        )
        d27_stages = _d27_stage_roots(d27_run_root, score)

        rows.append(
            {
                "score": score,
                "page": page,
                "gt_bbox": list(gt),
                "d27": {
                    "baseline": _matching(d27_sources["baseline"], gt),
                    "x4": _matching(d27_sources["sr"], gt),
                    "omr": _matching(d27_sources["omr"], gt),
                    "hybrid": _matching(d27_sources["hybrid"], gt),
                    "raw": _matching_candidates(d27_stages["raw"], score, page, gt),
                    "filtered": _matching_candidates(
                        d27_stages["filtered"], score, page, gt
                    ),
                    "rescue": _matching_candidates(
                        d27_stages["rescue"], score, page, gt
                    ),
                },
                "current": {
                    "baseline": _matching(cur_sources["baseline"], gt),
                    "x4": _matching(cur_sources["sr"], gt),
                    "omr": _matching(cur_sources["omr"], gt),
                    "hybrid": _matching(cur_sources["hybrid"], gt),
                    "raw": _matching_candidates(
                        current_stage_roots["raw"], score, page, gt
                    ),
                    "filtered": _matching_candidates(
                        current_stage_roots["filtered"], score, page, gt
                    ),
                    "rescue": _matching_candidates(
                        current_stage_roots["rescue"], score, page, gt
                    ),
                },
            }
        )

    result = {
        "schema_version": "issue372.merged_double_d27_current_geometry.v1",
        "rows": rows,
    }
    _write_json(output, result)
    print("=== Issue #372 D27/current merged-double geometry ===")
    for row in rows:
        print(f"{row['score']}/{row['page']} GT={row['gt_bbox']}")
        for side in ("d27", "current"):
            print(f"  {side}:")
            for stage in ("baseline", "x4", "omr", "hybrid", "raw", "filtered", "rescue"):
                print(f"    {stage}={row[side][stage]}")
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--d27-repo-root", type=Path, required=True)
    parser.add_argument("--current-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--residual-details", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
