#!/usr/bin/env python3
"""Diagnose saved current-production vs Issue #43 full-width differences."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _host_path(value: str | Path) -> Path:
    path = Path(value)
    try:
        return ROOT / path.relative_to("/workspace")
    except ValueError:
        return path


def _load_json(path: str | Path) -> Any:
    return json.loads(_host_path(path).read_text(encoding="utf-8"))


def _normalize_box(item: Any) -> tuple[int, int, int, int] | None:
    if isinstance(item, Mapping):
        for key in ("bbox", "barline_location", "orig_bbox", "pred_bbox"):
            if key in item:
                item = item[key]
                break
    if isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) == 4:
        return tuple(int(round(float(value))) for value in item)
    return None


def _box_list(path: Path) -> list[tuple[int, int, int, int]]:
    payload = _load_json(path)
    if isinstance(payload, Mapping):
        payload = payload.get("predictions", payload.get("boxes", payload))
    if not isinstance(payload, list):
        return []
    boxes = []
    for item in payload:
        box = _normalize_box(item)
        if box is not None:
            boxes.append(box)
    return boxes


def _score_map(path: Path) -> dict[tuple[int, int, int, int], float]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        return {}
    result: dict[tuple[int, int, int, int], float] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        box = _normalize_box(item.get("bbox"))
        if box is None:
            continue
        result[box] = float(item.get("score", 0.0))
    return result


def _production_page_dirs(report: Mapping[str, Any]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for run in report["provenance"].get("production_runs", []):
        root = _host_path(run["probe_output_dir"])
        for path in root.glob("eval2_*"):
            if path.is_dir():
                result[path.name] = path
    return result


def _full_width_page_dirs(report: Mapping[str, Any]) -> dict[str, Path]:
    root = _host_path(report["variants"]["full_width"]["probe_rescue_root"])
    return {path.name: path for path in root.glob("eval2_*") if path.is_dir()}


def run(report_path: Path) -> dict[str, Any]:
    report = _load_json(report_path)
    threshold = float(report["provenance"]["cnn_threshold"])
    production = _production_page_dirs(report)
    full_width = _full_width_page_dirs(report)

    page_keys = sorted(set(production) | set(full_width))
    changed_pages: list[dict[str, Any]] = []

    for page_key in page_keys:
        prod_dir = production.get(page_key)
        full_dir = full_width.get(page_key)
        if prod_dir is None or full_dir is None:
            changed_pages.append(
                {
                    "page_dir": page_key,
                    "missing_production": prod_dir is None,
                    "missing_full_width": full_dir is None,
                }
            )
            continue

        prod_candidates = _box_list(prod_dir / "pipeline2_no_peak_candidates.json")
        full_candidates = _box_list(full_dir / "pipeline2_no_peak_candidates.json")
        prod_candidate_set = set(prod_candidates)
        full_candidate_set = set(full_candidates)

        prod_final = set(_box_list(prod_dir / "pipeline2_no_peak_filtered_cnn.json"))
        full_final = set(_box_list(full_dir / "pipeline2_no_peak_filtered_cnn.json"))

        if prod_candidate_set == full_candidate_set and prod_final == full_final:
            continue

        prod_scores = _score_map(prod_dir / "pipeline2_no_peak_scored.json")
        full_scores = _score_map(full_dir / "pipeline2_no_peak_scored.json")

        common = sorted(set(prod_scores) & set(full_scores))
        score_deltas = [
            {
                "bbox": list(box),
                "production_score": prod_scores[box],
                "full_width_score": full_scores[box],
                "delta": full_scores[box] - prod_scores[box],
                "production_accept": prod_scores[box] >= threshold,
                "full_width_accept": full_scores[box] >= threshold,
            }
            for box in common
            if prod_scores[box] != full_scores[box]
        ]
        threshold_crossings = [
            item
            for item in score_deltas
            if item["production_accept"] != item["full_width_accept"]
        ]

        changed_pages.append(
            {
                "page_dir": page_key,
                "candidate_count_production": len(prod_candidate_set),
                "candidate_count_full_width": len(full_candidate_set),
                "candidate_sets_exact": prod_candidate_set == full_candidate_set,
                "candidate_removed_in_full_width": [
                    list(box) for box in sorted(prod_candidate_set - full_candidate_set)
                ],
                "candidate_added_in_full_width": [
                    list(box) for box in sorted(full_candidate_set - prod_candidate_set)
                ],
                "final_count_production": len(prod_final),
                "final_count_full_width": len(full_final),
                "final_removed_in_full_width": [
                    list(box) for box in sorted(prod_final - full_final)
                ],
                "final_added_in_full_width": [
                    list(box) for box in sorted(full_final - prod_final)
                ],
                "scored_box_sets_exact": set(prod_scores) == set(full_scores),
                "score_delta_count": len(score_deltas),
                "max_abs_score_delta": (
                    max(abs(float(item["delta"])) for item in score_deltas)
                    if score_deltas
                    else 0.0
                ),
                "threshold_crossing_count": len(threshold_crossings),
                "threshold_crossings": threshold_crossings,
            }
        )

    result = {
        "cnn_threshold": threshold,
        "changed_page_count": len(changed_pages),
        "changed_pages": changed_pages,
    }

    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run(args.report.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
