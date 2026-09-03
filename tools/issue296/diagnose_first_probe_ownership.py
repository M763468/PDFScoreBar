#!/usr/bin/env python3
"""Temporary Issue #296 diagnostic for page_015 x=580 producer ownership.

This script intentionally lives on the Issue #296 branch only and must be removed
before the final PR. It replays the *first dense probe generation* with the same
parameters as ``generate_probe_candidates_from_inventory.py``, but uses retained
Issue #274 page_015 source artifacts as seeds. The goal is to determine whether
x=580 can be emitted by ``detect_probe_scan`` itself rather than merely inherited
from a historical hybrid seed that is no longer retained locally.

No production files or canonical GT are modified.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.pipeline.probe_detector import detect_probe_scan

SCORE = "Va__Prokofiev_Symphony5"
PAGE = "page_015"
TARGET = (580, 4005, 584, 4115)


def _normalize_box(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    return tuple(int(round(float(v))) for v in value[:4])


def _boxes_from_payload(payload: Any) -> list[tuple[int, int, int, int]]:
    if isinstance(payload, dict):
        for key in ("predictions", "scores", "boxes", "detections"):
            if key in payload:
                return _boxes_from_payload(payload[key])
        for key in ("bbox", "pred_bbox", "barline_location", "orig_bbox"):
            if key in payload:
                box = _normalize_box(payload[key])
                return [box] if box is not None else []
        return []

    if not isinstance(payload, list):
        return []

    boxes: list[tuple[int, int, int, int]] = []
    for item in payload:
        if isinstance(item, dict):
            box = None
            for key in ("bbox", "pred_bbox", "barline_location", "orig_bbox"):
                if key in item:
                    box = _normalize_box(item[key])
                    break
        else:
            box = _normalize_box(item)
        if box is not None:
            boxes.append(box)
    return boxes


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return _boxes_from_payload(json.loads(path.read_text(encoding="utf-8")))


def _vertical_overlap_ratio(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    denom = max(1, min(abs(a[3] - a[1]), abs(b[3] - b[1])))
    return overlap / denom


def _center_x(box: tuple[int, int, int, int]) -> float:
    return (box[0] + box[2]) / 2.0


def _near_target(box: tuple[int, int, int, int]) -> bool:
    return abs(_center_x(box) - _center_x(TARGET)) <= 12.0 and _vertical_overlap_ratio(box, TARGET) >= 0.5


def _default_run_root(project_root: Path) -> Path:
    return (
        project_root
        / "logs/issue274_homr_unification_analysis/issue274_two_homr_full68_fresh_01"
    )


def _source_paths(run_root: Path) -> dict[str, Path]:
    hybrid_root = run_root / "hybrid" / SCORE
    return {
        "hybrid_result": hybrid_root / "hybrid_results" / f"{PAGE}_hybrid.json",
        "baseline_detections": (
            hybrid_root / "baseline" / "batch" / PAGE / f"{PAGE}_detections.json"
        ),
        "current_homr_detections": (
            hybrid_root
            / "current_support"
            / SCORE
            / PAGE
            / "artifacts/current_homr/batch"
            / PAGE
            / f"{PAGE}_detections.json"
        ),
        "omr_sr_predictions": (
            hybrid_root
            / "current_support"
            / SCORE
            / PAGE
            / "artifacts/omr_sr"
            / PAGE
            / "predictions.json"
        ),
    }


def _replay_first_probe(
    image: np.ndarray,
    existing_boxes: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    staff_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    generated = detect_probe_scan(
        base_img=image,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        band_source="row_stats",
        band_cluster_max_dist=25.0,
        band_min_row_count=1,
        band_scan_line_ratio=0.6,
        band_scan_min_lines=5,
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        probe_width=4,
        ink_threshold=240,
        min_ratio=0.6,
        scan_x_peak_ratio_min=0.0,
        scan_rightmost_min_ratio=0.0,
        max_per_band=80,
        scan_center_on_peak=True,
        vertical_closing=0,
    )
    return [tuple(int(v) for v in box) for box in generated]


def _inspect_source(name: str, path: Path, image: np.ndarray) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "path": str(path),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return result

    seed = _load_boxes(path)
    generated = _replay_first_probe(image, seed)
    seed_near = [list(box) for box in seed if _near_target(box)]
    generated_near = [list(box) for box in generated if _near_target(box)]

    result.update(
        {
            "seed_count": len(seed),
            "seed_target_exact": TARGET in seed,
            "seed_near_target": seed_near,
            "generated_count": len(generated),
            "generated_target_exact": TARGET in generated,
            "generated_near_target": generated_near,
            "first_union_target_exact": TARGET in set(seed).union(generated),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/issue296/diagnostic_03/first_probe_ownership.json"),
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    run_root = (args.run_root or _default_run_root(project_root)).resolve()
    image_path = project_root / "data/evaluation2/images" / SCORE / f"{PAGE}.png"
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)

    sources = {
        name: _inspect_source(name, path, image)
        for name, path in _source_paths(run_root).items()
    }

    hybrid = sources["hybrid_result"]
    if hybrid.get("generated_target_exact") is True:
        classification = "first_dense_probe_reproduces_target_from_retained_hybrid_seed"
    elif any(item.get("generated_target_exact") is True for item in sources.values()):
        classification = "first_dense_probe_reproduces_target_from_at_least_one_retained_source"
    elif any(item.get("generated_near_target") for item in sources.values()):
        classification = "first_dense_probe_reproduces_near_target_but_not_exact_bbox"
    else:
        classification = "first_dense_probe_target_not_reproduced_from_retained_sources"

    payload = {
        "schema_version": "issue296.first_probe_ownership.v1",
        "score": SCORE,
        "page": PAGE,
        "target": list(TARGET),
        "image": str(image_path),
        "run_root": str(run_root),
        "production_equivalent_first_probe_params": {
            "band_source": "row_stats",
            "band_cluster_max_dist": 25.0,
            "band_min_row_count": 1,
            "band_scan_line_ratio": 0.6,
            "band_scan_min_lines": 5,
            "probe_width": 4,
            "ink_threshold": 240,
            "min_ratio": 0.6,
            "scan_x_peak_rescue": True,
            "scan_rightmost_rescue": True,
            "divisi_rescue": True,
            "scan_center_on_peak": True,
            "max_per_band": 80,
            "vertical_closing": 0,
        },
        "sources": sources,
        "classification": classification,
        "interpretation": (
            "If hybrid_result.seed_target_exact is false and "
            "hybrid_result.generated_target_exact is true, x=580 is directly reproducible "
            "as a first dense probe emission from a retained current hybrid seed. That closes "
            "the current producer mechanism without relying on the deleted historical inventory seed."
        ),
    }

    output = args.output
    if not output.is_absolute():
        output = project_root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"SUMMARY={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
