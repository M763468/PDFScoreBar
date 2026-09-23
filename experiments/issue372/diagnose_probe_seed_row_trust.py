#!/usr/bin/env python3
"""Diagnose whether hybrid rows are trustworthy probe-scan geometry authorities.

Retained-only Issue #372 diagnostic.

For every current-control full68 page this script reconstructs the exact
row_stats clustering used by dense raw candidate generation
(cluster_max_dist=25, min_row_count=1), then relates each hybrid seed row to:

- GT agreement of the hybrid seed(s);
- x4-HOMR and OMR-DLN support of the hybrid seed(s);
- the number of raw-only candidates generated with that row band's geometry;
- GT agreement of those generated candidates.

This is diagnostic evidence only. GT is deliberately used to evaluate possible
production-side trust rules; it is not part of any proposed runtime rule.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _current_hybrid,
    _host_path,
    _load_json,
    _source_worker_result,
    _x4_detection,
)
from src.common import barline_iou
from src.common.barline_evaluation import is_barline_match
from src.pipeline.probe_detector.bands import cluster_by_y_distance
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

CLUSTER_MAX_DIST = 25.0
MIN_ROW_COUNT = 1
IOU_THRESHOLD = 0.5
RAW_FILENAME = "pipeline2_no_peak_candidates.json"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _gt_match(a: Sequence[int], b: Sequence[int]) -> bool:
    return is_barline_match(
        a,
        b,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _load_inventory_record(path: Path, *, page: str) -> Mapping[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError(f"Invalid inventory: {path}")
    rows = [
        row
        for row in payload["records"]
        if isinstance(row, Mapping) and str(row.get("page")) == page
    ]
    if len(rows) != 1:
        raise ValueError(f"Expected one {page} record in {path}, got {len(rows)}")
    return rows[0]


def _candidate_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = _load_json(path)
    return [_norm(box) for box in full68_eval.boxes_from_candidates(payload)]


def _gt_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = _load_json(path)
    return [_norm(box) for box in full68_eval.boxes_from_gt(payload)]


def _resolve_omr(
    record: Mapping[str, Any],
    *,
    score: str,
    page: str,
    issue43_repo_root: Path,
) -> Path:
    hybrid = _current_hybrid(record, issue43_repo_root)
    result_path = _source_worker_result(hybrid, score=score, page=page)
    payload = _load_json(result_path)
    if not isinstance(payload, Mapping) or not payload.get("current_omr"):
        raise ValueError(f"Source worker lacks current_omr: {result_path}")
    path = _host_path(str(payload["current_omr"]), issue43_repo_root)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _support_class(*, x4: bool, omr: bool) -> str:
    if x4 and omr:
        return "x4_and_omr"
    if x4:
        return "x4_only"
    if omr:
        return "omr_only"
    return "neither"


def _row_members(
    boxes: Sequence[tuple[int, int, int, int]],
) -> list[dict[str, Any]]:
    if not boxes:
        return []
    centers = np.array([(box[1] + box[3]) / 2.0 for box in boxes], dtype=float)
    rows, _ = cluster_by_y_distance(
        centers,
        max_distance=CLUSTER_MAX_DIST,
        min_cluster_size=MIN_ROW_COUNT,
    )
    out: list[dict[str, Any]] = []
    for indices in rows.values():
        members = [boxes[i] for i in indices]
        tops = [box[1] for box in members]
        bottoms = [box[3] for box in members]
        cys = [(box[1] + box[3]) / 2.0 for box in members]
        out.append(
            {
                "members": members,
                "center": float(np.median(cys)),
                # resolve_bands converts build_row_stats float medians with int(...).
                "top": int(float(np.median(tops))),
                "bottom": int(float(np.median(bottoms))),
            }
        )
    return sorted(out, key=lambda row: float(row["center"]))


def _match_gt_indices(
    boxes: Sequence[tuple[int, int, int, int]],
    gt: Sequence[tuple[int, int, int, int]],
) -> list[int]:
    return sorted(
        {
            idx
            for box in boxes
            for idx, target in enumerate(gt)
            if _gt_match(box, target)
        }
    )


def _init_bucket() -> dict[str, int]:
    return {
        "rows": 0,
        "gt_true_rows": 0,
        "gt_false_rows": 0,
        "seed_count": 0,
        "gt_seed_count": 0,
        "generated_count": 0,
        "generated_gt_candidate_count": 0,
        "generated_distinct_gt_count": 0,
    }


def _add_bucket(
    bucket: dict[str, int],
    *,
    seed_count: int,
    gt_seed_count: int,
    generated_count: int,
    generated_gt_candidate_count: int,
    generated_distinct_gt_count: int,
) -> None:
    bucket["rows"] += 1
    bucket["gt_true_rows"] += int(gt_seed_count > 0)
    bucket["gt_false_rows"] += int(gt_seed_count == 0)
    bucket["seed_count"] += seed_count
    bucket["gt_seed_count"] += gt_seed_count
    bucket["generated_count"] += generated_count
    bucket["generated_gt_candidate_count"] += generated_gt_candidate_count
    bucket["generated_distinct_gt_count"] += generated_distinct_gt_count


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run = args.x4_run_root.resolve()
    issue43_root = args.issue43_repo_root.resolve()
    gt_root = args.gt_root.resolve()
    raw_root = x4_run / "control" / "aggregate_raw_candidates"
    output = args.output.resolve()

    if not raw_root.is_dir():
        raise FileNotFoundError(raw_root)

    page_rows: list[dict[str, Any]] = []
    buckets: defaultdict[str, dict[str, int]] = defaultdict(_init_bucket)
    processed_pages = 0

    for score, pages in full68_eval.SCORES.items():
        inventory = x4_run / "inventories" / "control" / f"{score}.json"
        if not inventory.is_file():
            raise FileNotFoundError(inventory)

        for page in pages:
            record = _load_inventory_record(inventory, page=page)
            hybrid_path = _current_hybrid(record, issue43_root)
            x4_path = _x4_detection(
                record,
                score=score,
                page=page,
                source_repo_root=issue43_root,
            )
            omr_path = _resolve_omr(
                record,
                score=score,
                page=page,
                issue43_repo_root=issue43_root,
            )
            page_record = full68_eval.PageRecord(score=score, page=page)
            raw_path = full68_eval.find_page_file(raw_root, page_record, RAW_FILENAME)
            if raw_path is None or not raw_path.is_file():
                raise FileNotFoundError(f"{score}/{page}: {RAW_FILENAME} under {raw_root}")

            gt_path = gt_root / score / page / "boxes_sorted.json"
            if not gt_path.is_file():
                raise FileNotFoundError(gt_path)

            hybrid = [_norm(box) for box in load_json_boxes(hybrid_path)]
            x4 = [_norm(box) for box in load_json_boxes(x4_path)]
            omr = [_norm(box) for box in load_json_boxes(omr_path)]
            raw = _candidate_boxes(raw_path)
            gt = _gt_boxes(gt_path)

            hybrid_set = set(hybrid)
            generated = [box for box in raw if box not in hybrid_set]

            for row_index, row in enumerate(_row_members(hybrid)):
                members = list(row["members"])
                top = int(row["top"])
                bottom = int(row["bottom"])
                row_generated = [
                    box for box in generated if box[1] == top and box[3] == bottom
                ]

                member_evidence = []
                gt_seed_count = 0
                support_classes = []
                for seed in members:
                    x4_support = any(barline_iou(seed, box) > IOU_THRESHOLD for box in x4)
                    omr_support = any(barline_iou(seed, box) > IOU_THRESHOLD for box in omr)
                    gt_support = any(_gt_match(seed, box) for box in gt)
                    gt_seed_count += int(gt_support)
                    support_class = _support_class(x4=x4_support, omr=omr_support)
                    support_classes.append(support_class)
                    member_evidence.append(
                        {
                            "bbox": list(seed),
                            "x4_support": x4_support,
                            "omr_support": omr_support,
                            "support_class": support_class,
                            "gt_match": gt_support,
                        }
                    )

                generated_gt_flags = [
                    any(_gt_match(box, target) for target in gt)
                    for box in row_generated
                ]
                generated_gt_candidate_count = sum(generated_gt_flags)
                generated_gt_indices = _match_gt_indices(row_generated, gt)

                if len(members) == 1:
                    row_shape = "singleton"
                    row_support_class = support_classes[0]
                else:
                    row_shape = "multi"
                    has_x4 = any(item["x4_support"] for item in member_evidence)
                    has_omr = any(item["omr_support"] for item in member_evidence)
                    row_support_class = _support_class(x4=has_x4, omr=has_omr)

                row_gt_class = "gt_true" if gt_seed_count > 0 else "gt_false"
                bucket_keys = (
                    "all",
                    row_shape,
                    f"{row_shape}:{row_support_class}",
                    f"{row_shape}:{row_support_class}:{row_gt_class}",
                )
                for key in bucket_keys:
                    _add_bucket(
                        buckets[key],
                        seed_count=len(members),
                        gt_seed_count=gt_seed_count,
                        generated_count=len(row_generated),
                        generated_gt_candidate_count=generated_gt_candidate_count,
                        generated_distinct_gt_count=len(generated_gt_indices),
                    )

                page_rows.append(
                    {
                        "score": score,
                        "page": page,
                        "row_index": row_index,
                        "row_shape": row_shape,
                        "row_support_class": row_support_class,
                        "row_gt_class": row_gt_class,
                        "center": row["center"],
                        "band": [top, bottom],
                        "seed_count": len(members),
                        "gt_seed_count": gt_seed_count,
                        "members": member_evidence,
                        "generated_count": len(row_generated),
                        "generated_gt_candidate_count": generated_gt_candidate_count,
                        "generated_distinct_gt_count": len(generated_gt_indices),
                        "generated_boxes": [list(box) for box in row_generated],
                        "generated_gt_indices": generated_gt_indices,
                        "sources": {
                            "hybrid": str(hybrid_path),
                            "x4": str(x4_path),
                            "omr": str(omr_path),
                            "raw": str(raw_path),
                            "gt": str(gt_path),
                        },
                    }
                )
            processed_pages += 1

    if processed_pages != 68:
        raise RuntimeError(f"Expected 68 pages, processed {processed_pages}")

    suspicious_false_rows = sorted(
        [
            row
            for row in page_rows
            if row["row_gt_class"] == "gt_false" and row["generated_count"] > 0
        ],
        key=lambda row: (
            -int(row["generated_count"]),
            str(row["score"]),
            str(row["page"]),
            int(row["row_index"]),
        ),
    )

    true_singleton_expanders = sorted(
        [
            row
            for row in page_rows
            if row["row_shape"] == "singleton"
            and row["row_gt_class"] == "gt_true"
            and row["generated_count"] > 0
        ],
        key=lambda row: (
            -int(row["generated_distinct_gt_count"]),
            -int(row["generated_count"]),
            str(row["score"]),
            str(row["page"]),
        ),
    )

    true_x4_only_singleton_expanders = [
        row
        for row in true_singleton_expanders
        if row["row_support_class"] == "x4_only"
    ]

    report = {
        "schema_version": "issue372.probe_seed_row_trust.v1",
        "contract": {
            "retained_only": True,
            "gt_used_for_diagnosis_only": True,
            "raw_row_cluster_max_dist": CLUSTER_MAX_DIST,
            "raw_row_min_count": MIN_ROW_COUNT,
            "hybrid_support_iou_threshold": IOU_THRESHOLD,
            "gt_rule": "center_anchor vov>=0.5 xdist<=12px",
        },
        "inputs": {
            "x4_run_root": str(x4_run),
            "issue43_repo_root": str(issue43_root),
            "gt_root": str(gt_root),
            "raw_root": str(raw_root),
        },
        "processed_pages": processed_pages,
        "summary": dict(sorted(buckets.items())),
        "decision_evidence": {
            "false_rows_that_expand_count": len(suspicious_false_rows),
            "true_singleton_rows_that_expand_count": len(true_singleton_expanders),
            "true_x4_only_singleton_rows_that_expand_count": len(
                true_x4_only_singleton_expanders
            ),
            "top_false_rows_that_expand": suspicious_false_rows[:30],
            "top_true_singleton_rows_that_expand": true_singleton_expanders[:30],
            "top_true_x4_only_singleton_rows_that_expand": (
                true_x4_only_singleton_expanders[:30]
            ),
        },
        "rows": page_rows,
    }
    _write(output, report)

    print("=== Issue #372 probe seed-row trust diagnostic ===")
    print(f"processed_pages={processed_pages}")
    print()
    for key in (
        "singleton",
        "singleton:x4_only",
        "singleton:omr_only",
        "singleton:x4_and_omr",
        "multi",
    ):
        if key in buckets:
            print(f"{key}: {json.dumps(buckets[key], ensure_ascii=False)}")

    print()
    print(
        "false_rows_that_expand=",
        len(suspicious_false_rows),
        sep="",
    )
    print(
        "true_singleton_rows_that_expand=",
        len(true_singleton_expanders),
        sep="",
    )
    print(
        "true_x4_only_singleton_rows_that_expand=",
        len(true_x4_only_singleton_expanders),
        sep="",
    )

    print("\n=== top false rows that expand ===")
    for row in suspicious_false_rows[:20]:
        print(
            f"{row['score']}/{row['page']} "
            f"shape={row['row_shape']} support={row['row_support_class']} "
            f"band={row['band']} center={row['center']:.1f} "
            f"seeds={row['seed_count']} generated={row['generated_count']} "
            f"generated_gt={row['generated_distinct_gt_count']}"
        )
        if row["row_shape"] == "singleton":
            print("  seed=", row["members"][0]["bbox"])

    print("\n=== true x4-only singleton expanders ===")
    for row in true_x4_only_singleton_expanders[:20]:
        print(
            f"{row['score']}/{row['page']} "
            f"band={row['band']} center={row['center']:.1f} "
            f"generated={row['generated_count']} "
            f"generated_gt={row['generated_distinct_gt_count']} "
            f"seed={row['members'][0]['bbox']}"
        )

    print(f"\nOUTPUT={output}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
