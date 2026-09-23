#!/usr/bin/env python3
"""Inspect page_021 row-cluster membership behind the CNN staff-band regression.

Retained-only. Reconstructs the exact build_row_stats clustering inputs for:
- current maintained-HOMR control;
- late-raw x4 counterfactual;
- historical D27 producer.

For the cluster containing the three visible Shostakovich page_021 targets, the
report records all member boxes, sorted y-center gaps, median top/bottom, and
cross-variant correspondence. This is intended to expose bridge boxes that can
chain adjacent physical rows into one row_stats cluster.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from src.common.barline_evaluation import is_barline_match
from src.pipeline.probe_detector.bands import cluster_by_y_distance
from tools.issue120 import eval_full68_from_intermediates as full68_eval

SCORE = "Shostakovich-Sym5-Va"
PAGE = "page_021"
TARGETS = (
    (1333, 798, 1340, 894),
    (1769, 798, 1778, 896),
    (2749, 802, 2756, 900),
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = _load(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected list payload: {path}")
    result = []
    for row in payload:
        raw = row.get("bbox") if isinstance(row, Mapping) else row
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) >= 4:
            result.append(_norm(raw))
    return result


def _find(root: Path, filename: str) -> Path:
    record = full68_eval.PageRecord(score=SCORE, page=PAGE)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{SCORE}/{PAGE}: {filename} under {root}")
    return path


def _match(a: Sequence[int], b: Sequence[int]) -> bool:
    return is_barline_match(
        a,
        b,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _cluster_payload(
    *,
    name: str,
    filtered_root: Path,
) -> dict[str, Any]:
    path = _find(filtered_root, "pipeline2_no_peak_candidates.json")
    boxes = _boxes(path)
    if not boxes:
        raise ValueError(f"No filtered boxes: {path}")

    heights = np.array([abs(b[3] - b[1]) for b in boxes if abs(b[3] - b[1]) > 0], dtype=float)
    median_h = float(np.median(heights)) if heights.size else 100.0
    cluster_max_dist = median_h * 0.5
    y_centers = np.array([(b[1] + b[3]) / 2.0 for b in boxes], dtype=float)
    clusters, noise = cluster_by_y_distance(
        y_centers,
        cluster_max_dist,
        min_cluster_size=1,
    )

    target_indices: dict[str, list[int]] = {}
    target_cluster_ids: dict[str, list[int]] = {}
    for target in TARGETS:
        key = ",".join(str(v) for v in target)
        indices = [idx for idx, box in enumerate(boxes) if _match(box, target)]
        target_indices[key] = indices
        ids = []
        for cluster_id, members in clusters.items():
            if any(idx in members for idx in indices):
                ids.append(int(cluster_id))
        target_cluster_ids[key] = ids

    cluster_ids = sorted({
        cluster_id
        for ids in target_cluster_ids.values()
        for cluster_id in ids
    })
    relevant = []
    for cluster_id in cluster_ids:
        members = list(clusters[cluster_id])
        ordered = sorted(members, key=lambda idx: y_centers[idx])
        tops = [boxes[idx][1] for idx in members]
        bottoms = [boxes[idx][3] for idx in members]
        centers = [float(y_centers[idx]) for idx in members]
        gaps = []
        for left, right in zip(ordered, ordered[1:]):
            gaps.append({
                "from_index": int(left),
                "to_index": int(right),
                "from_center": float(y_centers[left]),
                "to_center": float(y_centers[right]),
                "gap": float(y_centers[right] - y_centers[left]),
            })

        relevant.append({
            "cluster_id": int(cluster_id),
            "member_count": len(members),
            "median_top": float(np.median(tops)),
            "median_bottom": float(np.median(bottoms)),
            "median_center": float(np.median(centers)),
            "min_center": float(min(centers)),
            "max_center": float(max(centers)),
            "center_span": float(max(centers) - min(centers)),
            "max_adjacent_gap": max((row["gap"] for row in gaps), default=0.0),
            "members": [
                {
                    "index": int(idx),
                    "bbox": list(boxes[idx]),
                    "center_y": float(y_centers[idx]),
                    "height": int(abs(boxes[idx][3] - boxes[idx][1])),
                    "matches_target": any(_match(boxes[idx], target) for target in TARGETS),
                }
                for idx in ordered
            ],
            "adjacent_center_gaps": gaps,
        })

    return {
        "name": name,
        "filtered_path": str(path),
        "filtered_count": len(boxes),
        "median_height": median_h,
        "cluster_max_dist": cluster_max_dist,
        "cluster_count": len(clusters),
        "noise_count": len(noise),
        "target_indices": target_indices,
        "target_cluster_ids": target_cluster_ids,
        "relevant_clusters": relevant,
        "_boxes": boxes,
    }


def _annotate_correspondence(
    variant: dict[str, Any],
    reference: dict[str, Any],
    *,
    field_name: str,
) -> None:
    ref_boxes = reference["_boxes"]
    for cluster in variant["relevant_clusters"]:
        for member in cluster["members"]:
            box = tuple(member["bbox"])
            matches = [
                list(ref)
                for ref in ref_boxes
                if _match(box, ref)
            ]
            member[field_name] = matches
            member[field_name + "_count"] = len(matches)


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run = args.x4_run_root.resolve()
    late_run = args.late_run_root.resolve()
    d27_run = args.d27_run_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)

    control_filtered = x4_run / "control" / "aggregate_filtered_candidates"
    late_filtered = late_run / "filtered"
    d27_filtered = (
        d27_run
        / "runs"
        / SCORE
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_candidates_filtered"
    )
    for path in (control_filtered, late_filtered, d27_filtered):
        if not path.is_dir():
            raise FileNotFoundError(path)

    control = _cluster_payload(
        name="current_control",
        filtered_root=control_filtered,
    )
    late = _cluster_payload(
        name="late_raw_x4",
        filtered_root=late_filtered,
    )
    d27 = _cluster_payload(
        name="historical_d27",
        filtered_root=d27_filtered,
    )

    _annotate_correspondence(control, d27, field_name="d27_strong_matches")
    _annotate_correspondence(late, d27, field_name="d27_strong_matches")
    _annotate_correspondence(d27, control, field_name="current_strong_matches")

    for variant in (control, late, d27):
        variant.pop("_boxes", None)

    payload = {
        "schema_version": "issue372.page021_row_cluster_membership.v1",
        "score": SCORE,
        "page": PAGE,
        "targets": [list(target) for target in TARGETS],
        "contract": {
            "cluster_algorithm": "cluster_by_y_distance on filtered bbox y-centers",
            "cluster_max_dist": "0.5 * median filtered bbox height",
            "min_cluster_size": 1,
            "cross_variant_match": "center_anchor vov>=0.5 xdist<=12px",
        },
        "variants": [control, late, d27],
    }
    _write(output, payload)

    print("=== Issue #372 page_021 row-cluster membership ===")
    for variant in payload["variants"]:
        print(
            f"\n{variant['name']}: filtered={variant['filtered_count']} "
            f"median_h={variant['median_height']:.3f} "
            f"cluster_max_dist={variant['cluster_max_dist']:.3f}"
        )
        for cluster in variant["relevant_clusters"]:
            print(
                f"  cluster={cluster['cluster_id']} n={cluster['member_count']} "
                f"median=[{cluster['median_top']:.1f},{cluster['median_bottom']:.1f}] "
                f"center_span={cluster['center_span']:.1f} "
                f"max_gap={cluster['max_adjacent_gap']:.1f}"
            )
            for member in cluster["members"]:
                marker = "*" if member["matches_target"] else " "
                print(
                    f"   {marker} bbox={member['bbox']} "
                    f"cy={member['center_y']:.1f} h={member['height']} "
                    f"d27_matches={member.get('d27_strong_matches_count')} "
                    f"current_matches={member.get('current_strong_matches_count')}"
                )
    print(f"\nOUTPUT={output}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--late-run-root", type=Path, required=True)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
