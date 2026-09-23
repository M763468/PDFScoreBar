#!/usr/bin/env python3
"""Trace source/stage provenance for the Shostakovich page_021 row-cluster pollution.

Retained-only. For the current maintained-HOMR route this diagnostic compares:
- maintained-original baseline HOMR;
- current-x4 HOMR;
- current hybrid;
- dense raw candidates;
- dense filtered candidates;
- probe-rescue candidates.

It then reports which sources contain the two current cluster families:
- the current-only upper family around cy~=799;
- the D27-corresponding lower family around cy~=846-851.

The families are derived from the observed current filtered cluster itself rather
than hard-coded bbox identities: the largest adjacent y-center gap inside the
target cluster is used as the split point.
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

import numpy as np

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _baseline_detection,
    _current_hybrid,
    _host_path,
    _load_json,
    _x4_detection,
)
from src.common.barline_evaluation import is_barline_match
from src.pipeline.probe_detector.bands import cluster_by_y_distance
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

SCORE = "Shostakovich-Sym5-Va"
PAGE = "page_021"
TARGETS = (
    (1333, 798, 1340, 894),
    (1769, 798, 1778, 896),
    (2749, 802, 2756, 900),
)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _match(a: Sequence[int], b: Sequence[int]) -> bool:
    return is_barline_match(
        a,
        b,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _find(root: Path, filename: str) -> Path:
    record = full68_eval.PageRecord(score=SCORE, page=PAGE)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{SCORE}/{PAGE}: {filename} under {root}")
    return path


def _boxes_from_candidate_file(path: Path) -> list[tuple[int, int, int, int]]:
    payload = _load_json(path)
    return [_norm(box) for box in full68_eval.boxes_from_candidates(payload)]


def _load_inventory_record(path: Path) -> Mapping[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError(f"Invalid inventory: {path}")
    rows = [
        row
        for row in payload["records"]
        if isinstance(row, Mapping) and str(row.get("page")) == PAGE
    ]
    if len(rows) != 1:
        raise ValueError(f"Expected one {PAGE} record in {path}, got {len(rows)}")
    return rows[0]


def _target_cluster(
    filtered: Sequence[tuple[int, int, int, int]],
) -> tuple[list[int], float, float]:
    heights = [abs(b[3] - b[1]) for b in filtered if abs(b[3] - b[1]) > 0]
    median_h = float(np.median(heights)) if heights else 100.0
    max_dist = median_h * 0.5
    centers = np.array([(b[1] + b[3]) / 2.0 for b in filtered], dtype=float)
    clusters, _ = cluster_by_y_distance(
        centers,
        max_dist,
        min_cluster_size=1,
    )
    target_indices = [
        idx
        for idx, box in enumerate(filtered)
        if any(_match(box, target) for target in TARGETS)
    ]
    cluster_ids = [
        cid
        for cid, members in clusters.items()
        if any(idx in members for idx in target_indices)
    ]
    if len(cluster_ids) != 1:
        raise RuntimeError(f"Expected one target cluster, got {cluster_ids}")
    members = list(clusters[cluster_ids[0]])
    ordered = sorted(members, key=lambda idx: centers[idx])
    if len(ordered) < 2:
        raise RuntimeError("Target cluster too small to split")

    gaps = [
        (float(centers[right] - centers[left]), pos, left, right)
        for pos, (left, right) in enumerate(zip(ordered, ordered[1:]))
    ]
    gap, _, left, right = max(gaps)
    split_center = (float(centers[left]) + float(centers[right])) / 2.0
    return members, split_center, gap


def _source_membership(
    source_boxes: Sequence[tuple[int, int, int, int]],
    family_boxes: Sequence[tuple[int, int, int, int]],
) -> dict[str, Any]:
    exact_source = set(source_boxes)
    exact = [box for box in family_boxes if box in exact_source]
    strong = [
        box
        for box in family_boxes
        if any(_match(box, source) for source in source_boxes)
    ]
    return {
        "source_box_count": len(source_boxes),
        "family_exact_count": len(exact),
        "family_strong_match_count": len(strong),
        "family_count": len(family_boxes),
        "exact_fraction": len(exact) / len(family_boxes) if family_boxes else None,
        "strong_fraction": len(strong) / len(family_boxes) if family_boxes else None,
        "exact_family_boxes": [list(box) for box in exact],
        "strong_family_boxes": [list(box) for box in strong],
    }


def _source_target_matches(
    source_boxes: Sequence[tuple[int, int, int, int]],
) -> list[dict[str, Any]]:
    rows = []
    for target in TARGETS:
        matches = [list(box) for box in source_boxes if _match(box, target)]
        rows.append({"target": list(target), "matches": matches})
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run = args.x4_run_root.resolve()
    late_run = args.late_run_root.resolve()
    issue43_root = args.issue43_repo_root.resolve()
    d27_run = args.d27_run_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)

    inventory_path = x4_run / "inventories" / "control" / f"{SCORE}.json"
    record = _load_inventory_record(inventory_path)

    baseline_path = _baseline_detection(record, issue43_root)
    x4_path = _x4_detection(
        record,
        score=SCORE,
        page=PAGE,
        source_repo_root=issue43_root,
    )
    hybrid_path = _current_hybrid(record, issue43_root)

    current_raw_path = _find(
        x4_run / "control" / "aggregate_raw_candidates",
        "pipeline2_no_peak_candidates.json",
    )
    current_filtered_path = _find(
        x4_run / "control" / "aggregate_filtered_candidates",
        "pipeline2_no_peak_candidates.json",
    )
    current_probe_path = _find(
        x4_run / "control" / "aggregate_probe_output",
        "pipeline2_no_peak_candidates.json",
    )
    late_raw_path = _find(
        late_run / "late_raw",
        "pipeline2_no_peak_candidates.json",
    )
    late_filtered_path = _find(
        late_run / "filtered",
        "pipeline2_no_peak_candidates.json",
    )
    late_probe_path = _find(
        late_run
        / "late_raw_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates",
        "pipeline2_no_peak_candidates.json",
    )

    d27_dense = (
        d27_run
        / "runs"
        / SCORE
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
    )
    d27_raw_path = _find(
        d27_dense / "probe_candidates_from_inventory",
        "pipeline2_no_peak_candidates.json",
    )
    d27_filtered_path = _find(
        d27_dense / "probe_candidates_filtered",
        "pipeline2_no_peak_candidates.json",
    )
    d27_probe_path = _find(
        d27_dense / "probe_rescue_candidates",
        "pipeline2_no_peak_candidates.json",
    )

    sources: dict[str, tuple[Path, list[tuple[int, int, int, int]]]] = {
        "maintained_original_baseline": (
            baseline_path,
            [_norm(box) for box in load_json_boxes(baseline_path)],
        ),
        "current_x4_homr": (
            x4_path,
            [_norm(box) for box in load_json_boxes(x4_path)],
        ),
        "current_hybrid": (
            hybrid_path,
            [_norm(box) for box in load_json_boxes(hybrid_path)],
        ),
        "current_raw": (
            current_raw_path,
            _boxes_from_candidate_file(current_raw_path),
        ),
        "current_filtered": (
            current_filtered_path,
            _boxes_from_candidate_file(current_filtered_path),
        ),
        "current_probe": (
            current_probe_path,
            _boxes_from_candidate_file(current_probe_path),
        ),
        "late_raw": (
            late_raw_path,
            _boxes_from_candidate_file(late_raw_path),
        ),
        "late_filtered": (
            late_filtered_path,
            _boxes_from_candidate_file(late_filtered_path),
        ),
        "late_probe": (
            late_probe_path,
            _boxes_from_candidate_file(late_probe_path),
        ),
        "d27_raw": (
            d27_raw_path,
            _boxes_from_candidate_file(d27_raw_path),
        ),
        "d27_filtered": (
            d27_filtered_path,
            _boxes_from_candidate_file(d27_filtered_path),
        ),
        "d27_probe": (
            d27_probe_path,
            _boxes_from_candidate_file(d27_probe_path),
        ),
    }

    current_filtered = sources["current_filtered"][1]
    members, split_center, largest_gap = _target_cluster(current_filtered)
    member_boxes = [current_filtered[idx] for idx in members]
    upper = [
        box
        for box in member_boxes
        if ((box[1] + box[3]) / 2.0) < split_center
    ]
    lower = [
        box
        for box in member_boxes
        if ((box[1] + box[3]) / 2.0) >= split_center
    ]

    source_rows = {}
    for name, (path, boxes) in sources.items():
        source_rows[name] = {
            "path": str(path),
            "upper_family": _source_membership(boxes, upper),
            "lower_family": _source_membership(boxes, lower),
            "target_matches": _source_target_matches(boxes),
        }

    payload = {
        "schema_version": "issue372.page021_row_source_attribution.v1",
        "score": SCORE,
        "page": PAGE,
        "contract": {
            "family_derivation": (
                "split current filtered target cluster at its largest adjacent "
                "y-center gap"
            ),
            "cross_source_match": "center_anchor vov>=0.5 xdist<=12px",
        },
        "family_summary": {
            "target_cluster_count": len(member_boxes),
            "split_center_y": split_center,
            "largest_adjacent_gap": largest_gap,
            "upper_family_count": len(upper),
            "lower_family_count": len(lower),
            "upper_center_histogram": dict(
                sorted(
                    Counter(
                        str((box[1] + box[3]) / 2.0)
                        for box in upper
                    ).items()
                )
            ),
            "lower_center_histogram": dict(
                sorted(
                    Counter(
                        str((box[1] + box[3]) / 2.0)
                        for box in lower
                    ).items()
                )
            ),
        },
        "sources": source_rows,
    }
    _write(output, payload)

    print("=== Issue #372 page_021 row source attribution ===")
    print(json.dumps(payload["family_summary"], indent=2, ensure_ascii=False))
    for name, row in source_rows.items():
        upper_row = row["upper_family"]
        lower_row = row["lower_family"]
        print(
            f"{name}: boxes={upper_row['source_box_count']} "
            f"upper_exact={upper_row['family_exact_count']}/{upper_row['family_count']} "
            f"upper_strong={upper_row['family_strong_match_count']}/{upper_row['family_count']} "
            f"lower_exact={lower_row['family_exact_count']}/{lower_row['family_count']} "
            f"lower_strong={lower_row['family_strong_match_count']}/{lower_row['family_count']}"
        )
        targets = [
            len(target["matches"])
            for target in row["target_matches"]
        ]
        print(f"  target_match_counts={targets}")
    print(f"OUTPUT={output}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--late-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
