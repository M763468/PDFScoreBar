#!/usr/bin/env python3
"""Attribute Issue #245 row-band drift to historical/current SR and OMR support.

The analyzer reads saved detector artifacts only. It replays the production
hybrid-consensus function with a fixed fresh baseline and historical/current
SR and OMR combinations, then compares the row-stat bands used by probe
candidate generation. It does not run inference, dense reconstruction, CNN,
MMR, or numbering.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common import barline_iou
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue245.prepare_accuracy_first_mixed_route import (
    inventory_by_key,
    layer_paths,
    load_inventory,
    resolve_repo_path,
)

Box = tuple[int, int, int, int]
CONSENSUS_IOU_THRESHOLD = 0.5
DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_MIXED_REPORT = Path(
    "logs/issue245_accuracy_first_mixed_route/accuracy_first_mixed_route_report.json"
)
DEFAULT_OUTPUT = Path(
    "logs/issue245_accuracy_first_stage_e/hybrid_row_band_source_drift.json"
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_box(value: Sequence[Any]) -> Box:
    if len(value) != 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value)  # type: ignore[return-value]


def _parse_target(raw: str) -> dict[str, Any]:
    parts = raw.split("|")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("target must be SCORE|PAGE|x1,y1,x2,y2")
    score, page, bbox_raw = parts
    try:
        bbox = _normalize_box([item.strip() for item in bbox_raw.split(",")])
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return {"score": score, "page": page, "reference": bbox}


def _find_page(report: dict[str, Any], score: str, page: str) -> dict[str, Any]:
    matches = [
        item
        for item in report.get("pages", [])
        if isinstance(item, dict)
        and str(item.get("score")) == score
        and str(item.get("page")) == page
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one mixed-route page for {score}/{page}, got {len(matches)}")
    return matches[0]


def _semantic_diff(left: Iterable[Box], right: Iterable[Box]) -> dict[str, Any]:
    left_counter = Counter(left)
    right_counter = Counter(right)
    return {
        "semantic_equal": left_counter == right_counter,
        "left_only": [list(box) for box in sorted((left_counter - right_counter).elements())],
        "right_only": [list(box) for box in sorted((right_counter - left_counter).elements())],
    }


def _row_clusters(boxes: Sequence[Box], cluster_max_dist: float = 25.0) -> list[dict[str, Any]]:
    if not boxes:
        return []
    ordered = sorted(enumerate(boxes), key=lambda item: ((item[1][1] + item[1][3]) / 2.0, item[1]))
    groups: list[list[tuple[int, Box]]] = [[ordered[0]]]
    for item in ordered[1:]:
        previous_center = (groups[-1][-1][1][1] + groups[-1][-1][1][3]) / 2.0
        center = (item[1][1] + item[1][3]) / 2.0
        if center - previous_center <= cluster_max_dist:
            groups[-1].append(item)
        else:
            groups.append([item])

    stats = build_row_stats(boxes, cluster_max_dist=cluster_max_dist, min_row_count=1)
    if len(stats) != len(groups):
        raise RuntimeError(
            f"Row cluster reconstruction mismatch: groups={len(groups)} stats={len(stats)}"
        )

    result: list[dict[str, Any]] = []
    for group, stat in zip(groups, stats, strict=True):
        result.append(
            {
                "center": float(stat["center"]),
                "top": int(stat["top"]),
                "bottom": int(stat["bottom"]),
                "members": [list(box) for _, box in group],
            }
        )
    return result


def _relevant_rows(rows: Iterable[dict[str, Any]], reference: Box) -> list[dict[str, Any]]:
    center = (reference[1] + reference[3]) / 2.0
    containing = [row for row in rows if row["top"] <= center <= row["bottom"]]
    if containing:
        return containing
    rows_list = list(rows)
    if not rows_list:
        return []
    nearest = min(rows_list, key=lambda row: abs(float(row["center"]) - center))
    return [{**nearest, "nearest_only": True}]


def _max_support(candidate: Box, support_boxes: Iterable[Box]) -> dict[str, Any]:
    ranked = sorted(
        ((box, barline_iou(candidate, box)) for box in support_boxes),
        key=lambda item: (-item[1], item[0]),
    )
    best_box, best_iou = ranked[0] if ranked else (None, 0.0)
    return {
        "accepted": best_iou > CONSENSUS_IOU_THRESHOLD,
        "max_iou": float(best_iou),
        "best_bbox": list(best_box) if best_box is not None else None,
    }


def _candidate_provenance(
    baseline: Sequence[Box],
    historical_hybrid: Sequence[Box],
    mixed_hybrid: Sequence[Box],
    historical_sr: Sequence[Box],
    historical_omr: Sequence[Box],
    current_sr: Sequence[Box],
    current_omr: Sequence[Box],
    reference: Box,
) -> list[dict[str, Any]]:
    center = (reference[1] + reference[3]) / 2.0
    relevant = [
        box
        for box in baseline
        if min(box[1], box[3]) <= center <= max(box[1], box[3])
        or abs(((box[1] + box[3]) / 2.0) - center) <= 25.0
    ]
    result = []
    historical_set = set(historical_hybrid)
    mixed_set = set(mixed_hybrid)
    for candidate in sorted(relevant):
        historical_sr_support = _max_support(candidate, historical_sr)
        historical_omr_support = _max_support(candidate, historical_omr)
        current_sr_support = _max_support(candidate, current_sr)
        current_omr_support = _max_support(candidate, current_omr)
        result.append(
            {
                "bbox": list(candidate),
                "historical_selected": candidate in historical_set,
                "mixed_selected": candidate in mixed_set,
                "historical_sr": historical_sr_support,
                "historical_omr": historical_omr_support,
                "current_sr": current_sr_support,
                "current_omr": current_omr_support,
            }
        )
    return result


def _has_reference_band(rows: Iterable[dict[str, Any]], reference: Box) -> bool:
    expected = (min(reference[1], reference[3]), max(reference[1], reference[3]))
    return any((int(row["top"]), int(row["bottom"])) == expected for row in rows)


def _variant_summary(boxes: Sequence[Box], reference: Box) -> dict[str, Any]:
    rows = _row_clusters(boxes)
    return {
        "candidate_count": len(boxes),
        "reference_band_present": _has_reference_band(rows, reference),
        "relevant_rows": _relevant_rows(rows, reference),
    }


def _classify(variants: dict[str, dict[str, Any]]) -> str:
    historical = bool(variants["historical_sr_historical_omr"]["reference_band_present"])
    current = bool(variants["current_sr_current_omr"]["reference_band_present"])
    historical_sr = bool(variants["historical_sr_current_omr"]["reference_band_present"])
    historical_omr = bool(variants["current_sr_historical_omr"]["reference_band_present"])
    if not historical or current:
        return "unresolved"
    if historical_sr and not historical_omr:
        return "historical_sr_dependency"
    if historical_omr and not historical_sr:
        return "historical_omr_dependency"
    if historical_sr and historical_omr:
        return "either_historical_support_source_sufficient"
    return "combined_historical_sr_omr_dependency"


def build_report(
    *,
    main_repo_root: Path,
    mixed_report_path: Path,
    targets: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    mixed_report = _load_json(mixed_report_path)
    if mixed_report.get("status") != "completed":
        raise ValueError(f"Mixed route report is not completed: {mixed_report_path}")

    historical_inventory_raw = mixed_report.get("historical_inventory", {}).get("path")
    if not historical_inventory_raw:
        raise ValueError("Mixed route report is missing historical inventory path")
    historical_inventory_path = resolve_repo_path(main_repo_root, historical_inventory_raw)
    historical_inventory = load_inventory(historical_inventory_path)
    historical_by_key = inventory_by_key(historical_inventory)

    reports: list[dict[str, Any]] = []
    for target in targets:
        score = str(target["score"])
        page = str(target["page"])
        reference = _normalize_box(target["reference"])
        page_report = _find_page(mixed_report, score, page)
        historical_record = historical_by_key[(score, page)]
        historical_paths = layer_paths(main_repo_root, historical_record)

        fresh_baseline_path = resolve_repo_path(main_repo_root, page_report["fresh_baseline"])
        current_sr_path = resolve_repo_path(main_repo_root, page_report["current_sr"])
        current_omr_path = resolve_repo_path(main_repo_root, page_report["current_omr"])
        historical_hybrid_path = resolve_repo_path(main_repo_root, page_report["historical_hybrid"])
        mixed_hybrid_path = resolve_repo_path(main_repo_root, page_report["mixed_hybrid"])

        historical_baseline = load_json_boxes(historical_paths["baseline"])
        fresh_baseline = load_json_boxes(fresh_baseline_path)
        historical_sr = load_json_boxes(historical_paths["sr"])
        historical_omr = load_json_boxes(historical_paths["omr"])
        current_sr = load_json_boxes(current_sr_path)
        current_omr = load_json_boxes(current_omr_path)
        saved_historical_hybrid = load_json_boxes(historical_hybrid_path)
        saved_mixed_hybrid = load_json_boxes(mixed_hybrid_path)

        generated = {
            "historical_sr_historical_omr": apply_hybrid_consensus_filter(
                baseline_boxes=fresh_baseline,
                sr_boxes=historical_sr,
                omr_boxes=historical_omr,
            ),
            "historical_sr_current_omr": apply_hybrid_consensus_filter(
                baseline_boxes=fresh_baseline,
                sr_boxes=historical_sr,
                omr_boxes=current_omr,
            ),
            "current_sr_historical_omr": apply_hybrid_consensus_filter(
                baseline_boxes=fresh_baseline,
                sr_boxes=current_sr,
                omr_boxes=historical_omr,
            ),
            "current_sr_current_omr": apply_hybrid_consensus_filter(
                baseline_boxes=fresh_baseline,
                sr_boxes=current_sr,
                omr_boxes=current_omr,
            ),
        }
        variants = {name: _variant_summary(boxes, reference) for name, boxes in generated.items()}

        historical_reproduction = _semantic_diff(
            generated["historical_sr_historical_omr"], saved_historical_hybrid
        )
        current_reproduction = _semantic_diff(
            generated["current_sr_current_omr"], saved_mixed_hybrid
        )
        baseline_comparison = _semantic_diff(historical_baseline, fresh_baseline)

        reports.append(
            {
                "score": score,
                "page": page,
                "reference": list(reference),
                "classification": _classify(variants),
                "paths": {
                    "historical_baseline": str(historical_paths["baseline"]),
                    "fresh_baseline": str(fresh_baseline_path),
                    "historical_sr": str(historical_paths["sr"]),
                    "current_sr": str(current_sr_path),
                    "historical_omr": str(historical_paths["omr"]),
                    "current_omr": str(current_omr_path),
                    "historical_hybrid": str(historical_hybrid_path),
                    "mixed_hybrid": str(mixed_hybrid_path),
                },
                "baseline_semantic_comparison": baseline_comparison,
                "historical_consensus_reproduction": historical_reproduction,
                "current_consensus_reproduction": current_reproduction,
                "variants": variants,
                "relevant_baseline_candidate_provenance": _candidate_provenance(
                    fresh_baseline,
                    saved_historical_hybrid,
                    saved_mixed_hybrid,
                    historical_sr,
                    historical_omr,
                    current_sr,
                    current_omr,
                    reference,
                ),
            }
        )

    return {
        "schema_version": "issue245.hybrid_row_band_source_drift.v1",
        "mixed_report": str(mixed_report_path),
        "historical_inventory": str(historical_inventory_path),
        "consensus_iou_contract": f"> {CONSENSUS_IOU_THRESHOLD}",
        "row_stats_contract": {"cluster_max_dist": 25.0, "min_row_count": 1},
        "targets": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--mixed-report", type=Path, default=DEFAULT_MIXED_REPORT)
    parser.add_argument("--target", type=_parse_target, action="append", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    main_repo = args.main_repo_root.expanduser().resolve()
    mixed_report = resolve_repo_path(main_repo, args.mixed_report)
    output = args.output.expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    report = build_report(
        main_repo_root=main_repo,
        mixed_report_path=mixed_report,
        targets=args.target,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for target in report["targets"]:
        print(
            f"{target['score']}/{target['page']} reference={target['reference']} "
            f"classification={target['classification']}"
        )
    print(f"Wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
