#!/usr/bin/env python3
"""Separate row-band geometry from existing-candidate suppression for Issue #245."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import cv2
import numpy as np

from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    is_barline_match,
)
from src.pipeline.probe_detector import detect_probe_scan
from src.pipeline.probe_detector.bands import build_row_stats

Box = tuple[int, int, int, int]
DetectFn = Callable[..., list[Box]]
MATCH_KWARGS = {"rule_name": "center_anchor", "vov_threshold": 0.5, "xdist_threshold": 12.0}
V12_PARAMS = {
    "band_source": "row_stats",
    "band_cluster_max_dist": 25.0,
    "band_min_row_count": 1,
    "ink_threshold": 230,
    "min_ratio": 0.7,
    "probe_width": 4,
    "max_per_band": 100,
    "band_scan_line_ratio": 0.6,
    "band_scan_min_lines": 5,
    "scan_x_peak_rescue": True,
    "scan_rightmost_rescue": True,
    "divisi_rescue": True,
    "scan_x_peak_rescue_mode": "topbottom",
    "scan_x_peak_ratio_min": 0.0,
    "scan_rightmost_min_ratio": 0.0,
    "scan_center_on_peak": True,
    "vertical_closing": 0,
}
SWEEP_VALUES = (0.0, 0.5, 0.55, 0.6, 0.65, 0.75)
MATRIX_IDS = ("HH-on", "HC-on", "CH-on", "CC-on", "HH-off", "HC-off", "CH-off", "CC-off")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(value: str | Path, main_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return main_root.joinpath(*path.parts[2:])
    return path if path.is_absolute() else main_root / path


def _normalize_box(value: Sequence[Any]) -> Box:
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _load_boxes(path: Path) -> list[Box]:
    payload = _load_json(path)
    records = payload.get("predictions", payload) if isinstance(payload, dict) else payload
    boxes: list[Box] = []
    if not isinstance(records, list):
        return boxes
    for item in records:
        if isinstance(item, (list, tuple)):
            boxes.append(_normalize_box(item))
        elif isinstance(item, dict):
            bbox = item.get("bbox", item.get("orig_bbox", item.get("pred_bbox")))
            if isinstance(bbox, (list, tuple)):
                boxes.append(_normalize_box(bbox))
    return boxes


def _find_record(inventory: Path, score: str, page: str) -> dict[str, Any]:
    records = _load_json(inventory).get("records", [])
    matches = [r for r in records if r.get("score") == score and r.get("page") == page]
    if len(matches) != 1:
        raise ValueError(f"Expected one record for {score}/{page}, got {len(matches)}")
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_path(root: Path, score: str, page: str) -> Path:
    direct = root / score / page / "pipeline2_no_peak_candidates.json"
    if direct.is_file():
        return direct
    matches = sorted(
        path
        for path in root.rglob("pipeline2_no_peak_candidates.json")
        if score in str(path) and page in str(path)
    )
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one candidate artifact for {score}/{page}: {matches}")
    return matches[0]


def _height(box: Box) -> int:
    return abs(box[3] - box[1])


def _closest(boxes: Iterable[Box], target: Box) -> dict[str, Any] | None:
    candidates = list(boxes)
    if not candidates:
        return None
    box = min(
        candidates,
        key=lambda item: (
            center_distance_x(item, target),
            -barline_vertical_overlap(item, target),
            sum(abs(item[index] - target[index]) for index in range(4)),
            item,
        ),
    )
    return {
        "bbox": list(box),
        "bbox_delta": [box[index] - target[index] for index in range(4)],
        "xdist": center_distance_x(box, target),
        "vertical_overlap": barline_vertical_overlap(box, target),
        "height": _height(box),
    }


def _target_bands(row_stats: list[dict[str, float]], full: Box, short: Box) -> list[list[int]]:
    centers = ((full[1] + full[3]) / 2.0, (short[1] + short[3]) / 2.0)
    return [
        [int(stat["top"]), int(stat["bottom"])]
        for stat in row_stats
        if any(stat["top"] <= center <= stat["bottom"] for center in centers)
    ]


def _debug_records(debug_path: Path | None, target: Box) -> list[dict[str, Any]]:
    if debug_path is None or not debug_path.with_suffix(".json").is_file():
        return []
    center = (target[0] + target[2]) / 2.0
    records = _load_json(debug_path.with_suffix(".json")).get("records", [])
    result = []
    for record in records:
        col = record.get("col", record.get("seed_col"))
        if col is None or abs(float(col) - center) > 12.0:
            continue
        result.append(
            {
                key: record.get(key)
                for key in (
                    "status",
                    "col",
                    "seed_col",
                    "band",
                    "staff_band",
                    "pred_band",
                    "ratio",
                    "rescue_reason",
                )
            }
        )
    return result


def _stage(
    generated: list[Box],
    full: Box,
    short: Box,
    before: int,
    bands: list[dict[str, float]],
    debug: Path | None,
) -> dict[str, Any]:
    return {
        "exact_full_span_generated": full in generated,
        "exact_short_generated": short in generated,
        "center_anchor_matches": [
            list(box) for box in generated if is_barline_match(box, full, **MATCH_KWARGS)
        ],
        "closest_to_full_span": _closest(generated, full),
        "closest_to_short": _closest(generated, short),
        "candidate_count_before_size_filter": before,
        "candidate_count_after_size_filter": len(generated),
        "target_relevant_row_bands": _target_bands(bands, full, short),
        "target_relevant_debug_records": _debug_records(debug, full),
    }


def run_variant(
    *,
    image: Any,
    existing_boxes: list[Box],
    row_stats: list[dict[str, float]],
    targets: list[dict[str, Any]],
    suppression: bool,
    min_height_ratio: float = 0.012,
    min_width_ratio: float = 0.0,
    existing_vertical_iou: float = 0.0,
    debug_path: Path | None = None,
    detect_fn: DetectFn = detect_probe_scan,
) -> tuple[list[Box], dict[str, dict[str, Any]]]:
    staff_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    candidates = [
        _normalize_box(box)
        for box in detect_fn(
            base_img=image,
            staff_mask=staff_mask,
            existing_boxes=existing_boxes,
            row_stats=row_stats,
            scan_disable_existing_suppression=not suppression,
            scan_existing_min_vertical_iou=existing_vertical_iou,
            debug_path=debug_path,
            **V12_PARAMS,
        )
    ]
    height, width = image.shape[:2]
    filtered = [
        box
        for box in candidates
        if _height(box) >= int(height * min_height_ratio)
        and abs(box[2] - box[0]) >= int(width * min_width_ratio)
    ]
    return filtered, {
        str(target["full_span"]): _stage(
            filtered,
            target["full_span"],
            target["short"],
            len(candidates),
            row_stats,
            debug_path,
        )
        for target in targets
    }


def _remove(boxes: list[Box], targets: list[Box]) -> list[Box]:
    remove = set(targets)
    return [box for box in boxes if box not in remove]


def _inject(boxes: list[Box], targets: list[Box]) -> list[Box]:
    return sorted(set(boxes).union(targets))


def classify(matrix: dict[str, dict[str, Any]], ablations: dict[str, dict[str, Any]]) -> str:
    cc_on = matrix["CC-on"]["exact_full_span_generated"]
    cc_off = matrix["CC-off"]["exact_full_span_generated"]
    hc_off = matrix["HC-off"]["exact_full_span_generated"]
    ch_off = matrix["CH-off"]["exact_full_span_generated"]
    removal = any(
        result["exact_full_span_generated"]
        for name, result in ablations.items()
        if name.startswith("current_frozen_remove")
    )
    if not cc_on and cc_off and removal:
        return "existing_suppression_only"
    if not cc_on and not cc_off and not ch_off and hc_off:
        return "row_band_geometry_only"
    if not cc_on and (cc_off or hc_off) and not removal:
        return "combined_band_and_suppression"
    if not cc_on and not cc_off:
        return "other_existing_geometry_dependency"
    return "unresolved"


def _vertical_iou(left: Box, right: Box) -> float:
    overlap = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    union = max(left[3], right[3]) - min(left[1], right[1])
    return overlap / union if union else 0.0


def _parse_target(raw: str) -> dict[str, Any]:
    score, page, full, short = raw.split("|", 3)
    return {
        "score": score,
        "page": page,
        "full_span": _normalize_box(full.split(",")),
        "short": _normalize_box(short.split(",")),
    }


def build_report(
    *,
    main_root: Path,
    historical_inventory: Path,
    current_inventory: Path,
    historical_raw_root: Path,
    current_raw_root: Path,
    targets: list[dict[str, Any]],
    debug_root: Path,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for target in targets:
        grouped.setdefault((target["score"], target["page"]), []).append(target)
    reports = []
    for (score, page), page_targets in grouped.items():
        historical = _find_record(historical_inventory, score, page)
        current = _find_record(current_inventory, score, page)
        historical_image = _resolve_path(historical["image"], main_root)
        current_image = _resolve_path(current["image"], main_root)
        if _sha256(historical_image) != _sha256(current_image):
            raise ValueError(f"Image hash mismatch for {score}/{page}")
        image = cv2.imread(str(historical_image))
        if image is None:
            raise FileNotFoundError(historical_image)
        h_boxes = _load_boxes(_resolve_path(historical["hybrid_predictions"], main_root))
        c_boxes = _load_boxes(_resolve_path(current["hybrid_predictions"], main_root))
        h_stats = build_row_stats(h_boxes, cluster_max_dist=25.0, min_row_count=1)
        c_stats = build_row_stats(c_boxes, cluster_max_dist=25.0, min_row_count=1)
        base_variants = {}
        for band_name, stats in (("H", h_stats), ("C", c_stats)):
            for existing_name, boxes in (("H", h_boxes), ("C", c_boxes)):
                for suppression in (True, False):
                    name = f"{band_name}{existing_name}-{'on' if suppression else 'off'}"
                    debug = debug_root / score / page / name / "probe.png"
                    _, result = run_variant(
                        image=image,
                        existing_boxes=boxes,
                        row_stats=stats,
                        targets=page_targets,
                        suppression=suppression,
                        debug_path=debug,
                    )
                    base_variants[name] = result
        ablation_variants: dict[str, dict[str, dict[str, Any]]] = {}
        shorts = [target["short"] for target in page_targets]
        subsets = [(f"short_{index + 1}", [short]) for index, short in enumerate(shorts)]
        if len(shorts) > 1:
            subsets.append(("both_shorts", shorts))
        for label, selected in subsets:
            cases = {
                f"current_frozen_remove_{label}": (c_stats, _remove(c_boxes, selected)),
                f"current_recomputed_remove_{label}": (
                    build_row_stats(
                        _remove(c_boxes, selected), cluster_max_dist=25.0, min_row_count=1
                    ),
                    _remove(c_boxes, selected),
                ),
                f"historical_frozen_inject_{label}": (h_stats, _inject(h_boxes, selected)),
                f"historical_recomputed_inject_{label}": (
                    build_row_stats(
                        _inject(h_boxes, selected), cluster_max_dist=25.0, min_row_count=1
                    ),
                    _inject(h_boxes, selected),
                ),
            }
            for name, (stats, boxes) in cases.items():
                _, ablation_variants[name] = run_variant(
                    image=image,
                    existing_boxes=boxes,
                    row_stats=stats,
                    targets=page_targets,
                    suppression=True,
                )
        sweep_outputs: dict[float, list[Box]] = {}
        sweep_results = {}
        for value in SWEEP_VALUES:
            generated, result = run_variant(
                image=image,
                existing_boxes=c_boxes,
                row_stats=c_stats,
                targets=page_targets,
                suppression=True,
                existing_vertical_iou=value,
            )
            sweep_outputs[value] = generated
            sweep_results[str(value)] = result
        zero = set(sweep_outputs[0.0])
        for value, result in sweep_results.items():
            generated = set(sweep_outputs[float(value)])
            for target in page_targets:
                key = str(target["full_span"])
                result[key].update(
                    {
                        "total_candidate_count": len(generated),
                        "added_candidates_relative_to_0": len(generated - zero),
                        "removed_candidates_relative_to_0": len(zero - generated),
                        "target_short_full_span_vertical_iou": _vertical_iou(
                            target["short"], target["full_span"]
                        ),
                    }
                )
        for target in page_targets:
            key = str(target["full_span"])
            reports.append(
                {
                    "score": score,
                    "page": page,
                    "full_span": list(target["full_span"]),
                    "short": list(target["short"]),
                    "image_sha256": _sha256(historical_image),
                    "historical_existing_path": str(
                        _resolve_path(historical["hybrid_predictions"], main_root)
                    ),
                    "current_existing_path": str(
                        _resolve_path(current["hybrid_predictions"], main_root)
                    ),
                    "historical_row_stats": h_stats,
                    "current_row_stats": c_stats,
                    "saved_historical_raw": str(_candidate_path(historical_raw_root, score, page)),
                    "saved_current_raw": str(_candidate_path(current_raw_root, score, page)),
                    "matrix": {name: data[key] for name, data in base_variants.items()},
                    "ablations": {name: data[key] for name, data in ablation_variants.items()},
                    "vertical_iou_sweep": {name: data[key] for name, data in sweep_results.items()},
                    "classification": classify(
                        {name: data[key] for name, data in base_variants.items()},
                        {name: data[key] for name, data in ablation_variants.items()},
                    ),
                }
            )
    return {
        "schema_version": "issue245.probe_geometry_suppression.v1",
        "inputs": {
            "main_root": str(main_root),
            "historical_inventory": str(historical_inventory),
            "current_inventory": str(current_inventory),
            "historical_raw_root": str(historical_raw_root),
            "current_raw_root": str(current_raw_root),
            "debug_root": str(debug_root),
        },
        "parameters": {**V12_PARAMS, "min_height_ratio": 0.012, "min_width_ratio": 0.0},
        "targets": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--historical-inventory", type=Path, required=True)
    parser.add_argument("--current-inventory", type=Path, required=True)
    parser.add_argument("--historical-raw-root", type=Path, required=True)
    parser.add_argument("--current-raw-root", type=Path, required=True)
    parser.add_argument("--target", type=_parse_target, action="append", required=True)
    parser.add_argument("--debug-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        main_root=args.main_root,
        historical_inventory=args.historical_inventory,
        current_inventory=args.current_inventory,
        historical_raw_root=args.historical_raw_root,
        current_raw_root=args.current_raw_root,
        targets=args.target,
        debug_root=args.debug_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for target in report["targets"]:
        print(f"{target['score']}/{target['page']} {target['classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
