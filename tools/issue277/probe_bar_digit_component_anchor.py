#!/usr/bin/env python3
"""Probe a bar+digit-component content anchor for Issue #277.

Experiment-only. Builds on the first hbar-anchored probe, but does not OCR a wide
staff-relative window. Instead it:

1. detects plausible thick horizontal rest-bar segments with horizontal morphology;
2. clusters bar candidates across staves by absolute x position;
3. searches only above each candidate bar for compact connected-component groups;
4. chooses the digit group geometrically, never by RapidOCR confidence;
5. normalizes only that tight digit patch to a reference staff height;
6. uses cross-staff agreement / cluster agreement instead of max OCR score.

The previous geometry-stability artifact selects the sensitive measure set and the
same native + +/-1/2/4 px perturbation variants. Expected fixture values are used
only after inference for evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Optional

import cv2
import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)

import probe_full68_candidate_policy as full_probe
import probe_geometry_stability_envelope as stability_probe
import probe_hbar_anchored_roi as hbar_v1
import probe_native_geometry_robustness as base

REFERENCE_STAFF_HEIGHT = 160.0
SEARCH_X_PAD_STAFF = 0.60
SEARCH_Y_ABOVE_STAFF = 0.80
SEARCH_Y_BELOW_STAFF = 0.55
BAR_OPEN_WIDTH_STAFF = 0.15
BAR_MIN_WIDTH_STAFF = 0.18
BAR_MIN_HEIGHT_STAFF = 0.02
BAR_MAX_HEIGHT_STAFF = 0.20
BAR_MAX_CENTER_DISTANCE_STAFF = 0.45
BAR_MIN_ASPECT = 2.0
BAR_CLUSTER_TOLERANCE_STAFF = 0.35
MAX_BAR_CLUSTERS = 2

DIGIT_HALF_WIDTH_STAFF = 0.60
DIGIT_TOP_FROM_BAR_STAFF = -1.25
DIGIT_BOTTOM_FROM_BAR_STAFF = -0.12
DIGIT_REMOVE_HORIZONTAL_STAFF = 0.30
DIGIT_MIN_HEIGHT_STAFF = 0.08
DIGIT_MAX_HEIGHT_STAFF = 0.70
DIGIT_MIN_WIDTH_STAFF = 0.015
DIGIT_MAX_WIDTH_STAFF = 0.55
DIGIT_MAX_X_DISTANCE_STAFF = 0.50
DIGIT_TARGET_Y_ABOVE_BAR_STAFF = 0.55
DIGIT_MAX_Y_DISTANCE_STAFF = 0.55
DIGIT_GROUP_GAP_STAFF = 0.20
DIGIT_GROUP_Y_TOLERANCE_STAFF = 0.25
DIGIT_GROUP_AMBIGUITY_MARGIN = 0.08
DIGIT_PAD_STAFF = 0.08


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _clip(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _bar_candidates(
    image: np.ndarray,
    measure_bbox: list[int],
    staff_bbox: list[int],
    staff_index: int,
) -> list[dict[str, Any]]:
    height, width = image.shape[:2]
    x1, _y1, x2, _y2 = (int(v) for v in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (int(v) for v in staff_bbox)
    staff_height = max(1.0, float(sy2 - sy1))

    ox1 = _clip(round(x1 - SEARCH_X_PAD_STAFF * staff_height), 0, width)
    ox2 = _clip(round(x2 + SEARCH_X_PAD_STAFF * staff_height), 0, width)
    oy1 = _clip(round(sy1 - SEARCH_Y_ABOVE_STAFF * staff_height), 0, height)
    oy2 = _clip(round(sy2 + SEARCH_Y_BELOW_STAFF * staff_height), 0, height)
    if ox2 <= ox1 or oy2 <= oy1:
        return []

    crop = image[oy1:oy2, ox1:ox2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    kernel_width = max(3, int(round(BAR_OPEN_WIDTH_STAFF * staff_height)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(
        horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    staff_center = sy1 + staff_height / 2.0
    measure_center = (x1 + x2) / 2.0
    result: list[dict[str, Any]] = []
    for contour in contours:
        cx, cy, cw, ch = cv2.boundingRect(contour)
        if cw < BAR_MIN_WIDTH_STAFF * staff_height:
            continue
        if ch < BAR_MIN_HEIGHT_STAFF * staff_height:
            continue
        if ch > BAR_MAX_HEIGHT_STAFF * staff_height:
            continue
        if cw / max(1.0, float(ch)) < BAR_MIN_ASPECT:
            continue
        center_x = ox1 + cx + cw / 2.0
        center_y = oy1 + cy + ch / 2.0
        if abs(center_y - staff_center) > BAR_MAX_CENTER_DISTANCE_STAFF * staff_height:
            continue
        result.append(
            {
                "staff": staff_index,
                "staff_bbox": [int(v) for v in staff_bbox],
                "staff_height": staff_height,
                "bbox": [ox1 + cx, oy1 + cy, ox1 + cx + cw, oy1 + cy + ch],
                "center_x": float(center_x),
                "center_y": float(center_y),
                "width": int(cw),
                "height": int(ch),
                "width_staff": float(cw / staff_height),
                "height_staff": float(ch / staff_height),
                "measure_center_distance_staff": float(
                    abs(center_x - measure_center) / staff_height
                ),
            }
        )

    result.sort(
        key=lambda item: (
            float(item["measure_center_distance_staff"]),
            -float(item["width_staff"]),
            float(item["center_x"]),
        )
    )
    return result


def _cluster_bars(
    candidates_by_staff: list[list[dict[str, Any]]],
    measure_bbox: list[int],
) -> list[dict[str, Any]]:
    flat = [item for values in candidates_by_staff for item in values]
    if not flat:
        return []
    typical_staff_height = float(median(item["staff_height"] for item in flat))
    tolerance = max(1.0, BAR_CLUSTER_TOLERANCE_STAFF * typical_staff_height)
    measure_center = (float(measure_bbox[0]) + float(measure_bbox[2])) / 2.0

    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(flat, key=lambda value: float(value["center_x"])):
        best_index = None
        best_distance = None
        for index, cluster in enumerate(clusters):
            cluster_center = float(median(value["center_x"] for value in cluster))
            distance = abs(float(item["center_x"]) - cluster_center)
            if distance <= tolerance and (best_distance is None or distance < best_distance):
                best_index = index
                best_distance = distance
        if best_index is None:
            clusters.append([item])
        else:
            clusters[best_index].append(item)

    summarized = []
    for cluster in clusters:
        center_x = float(median(item["center_x"] for item in cluster))
        per_staff: dict[int, dict[str, Any]] = {}
        for item in cluster:
            staff = int(item["staff"])
            current = per_staff.get(staff)
            if current is None or abs(float(item["center_x"]) - center_x) < abs(
                float(current["center_x"]) - center_x
            ):
                per_staff[staff] = item
        bars = list(per_staff.values())
        summarized.append(
            {
                "center_x": center_x,
                "staff_support": len(bars),
                "measure_center_distance_staff": float(
                    abs(center_x - measure_center) / typical_staff_height
                ),
                "median_width_staff": float(
                    median(item["width_staff"] for item in bars)
                ),
                "bars": bars,
            }
        )

    summarized.sort(
        key=lambda item: (
            -int(item["staff_support"]),
            float(item["measure_center_distance_staff"]),
            -float(item["median_width_staff"]),
            float(item["center_x"]),
        )
    )
    return summarized[:MAX_BAR_CLUSTERS]


def _component_groups(
    image: np.ndarray,
    bar: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    height, width = image.shape[:2]
    staff_height = float(bar["staff_height"])
    center_x = float(bar["center_x"])
    center_y = float(bar["center_y"])

    x1 = _clip(round(center_x - DIGIT_HALF_WIDTH_STAFF * staff_height), 0, width)
    x2 = _clip(round(center_x + DIGIT_HALF_WIDTH_STAFF * staff_height), 0, width)
    y1 = _clip(round(center_y + DIGIT_TOP_FROM_BAR_STAFF * staff_height), 0, height)
    y2 = _clip(round(center_y + DIGIT_BOTTOM_FROM_BAR_STAFF * staff_height), 0, height)
    if x2 <= x1 or y2 <= y1:
        return [], {"zone_bbox": [x1, y1, x2, y2], "reason": "empty_zone"}

    crop = image[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    horizontal_width = max(
        3, int(round(DIGIT_REMOVE_HORIZONTAL_STAFF * staff_height))
    )
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_width, 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    cleaned = cv2.subtract(binary, horizontal)

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(cleaned, 8)
    components: list[dict[str, Any]] = []
    for label in range(1, count):
        cx, cy, cw, ch, area = (int(v) for v in stats[label])
        if ch < DIGIT_MIN_HEIGHT_STAFF * staff_height:
            continue
        if ch > DIGIT_MAX_HEIGHT_STAFF * staff_height:
            continue
        if cw < DIGIT_MIN_WIDTH_STAFF * staff_height:
            continue
        if cw > DIGIT_MAX_WIDTH_STAFF * staff_height:
            continue
        abs_x1, abs_y1 = x1 + cx, y1 + cy
        abs_x2, abs_y2 = abs_x1 + cw, abs_y1 + ch
        comp_center_x = x1 + float(centroids[label][0])
        comp_center_y = y1 + float(centroids[label][1])
        components.append(
            {
                "bbox": [abs_x1, abs_y1, abs_x2, abs_y2],
                "center_x": comp_center_x,
                "center_y": comp_center_y,
                "width": cw,
                "height": ch,
                "area": area,
            }
        )

    components.sort(key=lambda item: (int(item["bbox"][0]), int(item["bbox"][1])))
    groups: list[list[dict[str, Any]]] = []
    for component in components:
        placed = False
        for group in groups:
            right = max(int(item["bbox"][2]) for item in group)
            gap = int(component["bbox"][0]) - right
            group_center_y = float(median(item["center_y"] for item in group))
            if (
                gap <= DIGIT_GROUP_GAP_STAFF * staff_height
                and abs(float(component["center_y"]) - group_center_y)
                <= DIGIT_GROUP_Y_TOLERANCE_STAFF * staff_height
            ):
                group.append(component)
                placed = True
                break
        if not placed:
            groups.append([component])

    target_y = center_y - DIGIT_TARGET_Y_ABOVE_BAR_STAFF * staff_height
    summarized: list[dict[str, Any]] = []
    for group in groups:
        gx1 = min(int(item["bbox"][0]) for item in group)
        gy1 = min(int(item["bbox"][1]) for item in group)
        gx2 = max(int(item["bbox"][2]) for item in group)
        gy2 = max(int(item["bbox"][3]) for item in group)
        group_center_x = (gx1 + gx2) / 2.0
        group_center_y = (gy1 + gy2) / 2.0
        x_distance = abs(group_center_x - center_x) / staff_height
        y_distance = abs(group_center_y - target_y) / staff_height
        if x_distance > DIGIT_MAX_X_DISTANCE_STAFF:
            continue
        if y_distance > DIGIT_MAX_Y_DISTANCE_STAFF:
            continue
        geometry_score = x_distance + 0.5 * y_distance
        summarized.append(
            {
                "bbox": [gx1, gy1, gx2, gy2],
                "component_count": len(group),
                "center_x": group_center_x,
                "center_y": group_center_y,
                "x_distance_staff": float(x_distance),
                "y_distance_staff": float(y_distance),
                "geometry_score": float(geometry_score),
            }
        )

    summarized.sort(
        key=lambda item: (
            float(item["geometry_score"]),
            float(item["center_x"]),
        )
    )
    return summarized, {
        "zone_bbox": [x1, y1, x2, y2],
        "raw_component_count": len(components),
        "plausible_group_count": len(summarized),
    }


def _select_group(groups: list[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], str]:
    if not groups:
        return None, "no_digit_group"
    if len(groups) >= 2:
        margin = float(groups[1]["geometry_score"]) - float(groups[0]["geometry_score"])
        if margin < DIGIT_GROUP_AMBIGUITY_MARGIN:
            return None, "ambiguous_digit_groups"
    return groups[0], "selected"


def _ocr_group(
    image: np.ndarray,
    bar: Mapping[str, Any],
    group: Mapping[str, Any],
    ocr: MMROCREngine,
) -> tuple[Optional[int], float, str, list[int]]:
    height, width = image.shape[:2]
    staff_height = float(bar["staff_height"])
    pad = max(1, int(round(DIGIT_PAD_STAFF * staff_height)))
    gx1, gy1, gx2, gy2 = (int(v) for v in group["bbox"])
    x1 = _clip(gx1 - pad, 0, width)
    y1 = _clip(gy1 - pad, 0, height)
    x2 = _clip(gx2 + pad, 0, width)
    y2 = _clip(gy2 + pad, 0, height)
    if x2 <= x1 or y2 <= y1:
        return None, 0.0, "empty_digit_roi", [x1, y1, x2, y2]

    roi = image[y1:y2, x1:x2]
    scale = REFERENCE_STAFF_HEIGHT / max(1.0, staff_height)
    target_w = max(8, int(round(roi.shape[1] * scale)))
    target_h = max(8, int(round(roi.shape[0] * scale)))
    interpolation = cv2.INTER_CUBIC if scale >= 1.0 else cv2.INTER_AREA
    normalized = cv2.resize(roi, (target_w, target_h), interpolation=interpolation)
    processed = ocr.preprocess_variant(
        normalized,
        mode="no_dilate",
        angle=0,
        staff_height=REFERENCE_STAFF_HEIGHT,
        use_staff_relative_geometry=True,
    )
    if processed is None or processed.size == 0:
        return None, 0.0, "empty_preprocess", [x1, y1, x2, y2]
    result, _ = ocr.ocr_engine(processed)
    number, score, debug = ocr.select_best_candidate(
        result or [], processed.shape[1], processed.shape[0]
    )
    if number is None or int(number) < 2:
        return None, 0.0, str(debug), [x1, y1, x2, y2]
    return int(number), float(score), str(debug), [x1, y1, x2, y2]


def _evaluate_cluster(
    image: np.ndarray,
    cluster: Mapping[str, Any],
    ocr: MMROCREngine,
) -> dict[str, Any]:
    staff_results = []
    for bar in cluster["bars"]:
        groups, component_debug = _component_groups(image, bar)
        selected_group, reason = _select_group(groups)
        if selected_group is None:
            number, score, debug, roi_bbox = None, 0.0, reason, None
        else:
            number, score, debug, roi_bbox = _ocr_group(
                image, bar, selected_group, ocr
            )
        staff_results.append(
            {
                "staff": int(bar["staff"]),
                "bar": dict(bar),
                "component_debug": component_debug,
                "selected_group": selected_group,
                "digit_roi_bbox": roi_bbox,
                "number": number,
                "skip": None if number is None else number - 1,
                "score": score,
                "debug": debug,
            }
        )

    votes = Counter(
        int(item["number"])
        for item in staff_results
        if item["number"] is not None and int(item["number"]) >= 2
    )
    selected = None
    support = 0
    if votes:
        support = max(votes.values())
        leaders = [number for number, count in votes.items() if count == support]
        if len(leaders) == 1:
            selected = int(leaders[0])
    return {
        "cluster": dict(cluster),
        "number": selected,
        "skip": None if selected is None else selected - 1,
        "number_support": int(support),
        "staff_results": staff_results,
    }


def _select_cluster_result(results: list[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], str]:
    valid = [item for item in results if item["number"] is not None]
    if not valid:
        return None, "no_cluster_number"
    numbers = {int(item["number"]) for item in valid}
    if len(numbers) == 1:
        valid.sort(
            key=lambda item: (
                -int(item["number_support"]),
                -int(item["cluster"]["staff_support"]),
                float(item["cluster"]["measure_center_distance_staff"]),
            )
        )
        return valid[0], "cluster_agreement"

    best_support = max(int(item["number_support"]) for item in valid)
    leaders = [item for item in valid if int(item["number_support"]) == best_support]
    if len(leaders) != 1:
        return None, "ambiguous_cluster_numbers"
    return leaders[0], "cross_staff_support"


def _anchored_measure(
    image: np.ndarray,
    system: Mapping[str, Any],
    measure_bbox: list[int],
    ocr: MMROCREngine,
) -> dict[str, Any]:
    candidates_by_staff = []
    for staff_index, stave in enumerate(system.get("staves", [])):
        staff_bbox = [int(v) for v in stave["bbox"]]
        candidates_by_staff.append(
            _bar_candidates(image, measure_bbox, staff_bbox, staff_index)
        )
    clusters = _cluster_bars(candidates_by_staff, measure_bbox)
    evaluated = [_evaluate_cluster(image, cluster, ocr) for cluster in clusters]
    selected, reason = _select_cluster_result(evaluated)
    return {
        "number": None if selected is None else selected["number"],
        "skip": None if selected is None else selected["skip"],
        "selection_reason": reason,
        "bar_candidate_counts": [len(value) for value in candidates_by_staff],
        "cluster_count": len(clusters),
        "clusters": evaluated,
    }


def _summary_for_key(
    key: str,
    observations: Mapping[str, Mapping[str, Any]],
    variant_count: int,
) -> dict[str, Any]:
    values = list(observations.values())
    expected_skip = values[0]["expected_skip"]
    skips = [item["skip"] for item in values]
    non_null = [value for value in skips if value is not None]
    failure_reasons = Counter(str(item["selection_reason"]) for item in values)
    return {
        "key": key,
        "expected_skip": expected_skip,
        "variant_count": len(values),
        "non_null_count": len(non_null),
        "skip_counts": {
            str(number): count for number, count in sorted(Counter(non_null).items())
        },
        "selection_reasons": dict(sorted(failure_reasons.items())),
        "semantic_exact_across_variants": len(set(skips)) == 1,
        "all_variants_expected": bool(
            expected_skip is not None
            and len(skips) == variant_count
            and all(skip == expected_skip for skip in skips)
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    stability_path = args.stability_artifact.resolve()
    accepted_path = args.accepted_rebase_report.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / base.DEFAULT_MANIFEST_REL).resolve()
    )
    for path in (stability_path, accepted_path, manifest_path, args.model.resolve()):
        if not path.is_file():
            raise FileNotFoundError(path)

    started = time.perf_counter()
    stability = _load(stability_path)
    sensitive = hbar_v1._sensitive_keys(stability)
    variants = hbar_v1._variant_specs(stability)
    manifest = base._load_json(manifest_path)
    matrix_pages = base._load_matrix_pages(manifest, issue294_root)
    accepted_pages, accepted_provenance = full_probe._accepted_pages(accepted_path)
    specs = {str(spec.page_id): spec for spec in base.build_page_specs()}

    raw_ocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(raw_ocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDAExecutionProvider not confirmed: {providers}")
    counter = base.CountingOCR(raw_ocr)
    classifier = MMRClassifier(args.model, torch.device("cuda"))
    processor = MMRProcessor(
        args.model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=counter),
    )

    prepared: dict[str, Any] = {}
    for page_id in sorted(sensitive):
        spec = specs[page_id]
        matrix_page = matrix_pages[(str(spec.score), str(spec.page_name))]
        page_data, image_path, support, mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        expected, mappings = full_probe._rebase_expected(
            accepted_pages[page_id],
            page_data,
            global_page_index=int(spec.global_index),
        )
        prepared[page_id] = {
            "spec": spec,
            "image": image,
            "support": support,
            "expected": expected,
            "mapping_mode": mapping_mode,
            "expected_mappings": mappings,
        }

    variant_results: dict[str, Any] = {}
    per_key: dict[str, dict[str, Any]] = defaultdict(dict)

    for variant in variants:
        name = str(variant["name"])
        before = counter.calls
        variant_started = time.perf_counter()
        events = []
        for page_id in sorted(prepared):
            item = prepared[page_id]
            image = item["image"]
            height, width = image.shape[:2]
            support = stability_probe._perturb_support(
                item["support"], variant, width, height
            )
            primary = support["views"]["primary"]["pages"][0]["systems"]
            for system_idx, measure_idx in sorted(sensitive[page_id]):
                system = primary[system_idx]
                measure_bbox = [
                    int(v) for v in system["measures"][measure_idx]["bbox"]
                ]
                probability = base._cnn_probability(
                    processor, image, measure_bbox
                )
                anchored = _anchored_measure(
                    image, system, measure_bbox, processor.ocr
                )
                expected_skip = item["expected"].get((system_idx, measure_idx))
                key = f"{page_id} s{system_idx} m{measure_idx}"
                event = {
                    "key": key,
                    "page_id": page_id,
                    "system": system_idx,
                    "measure": measure_idx,
                    "measure_bbox": measure_bbox,
                    "probability": probability,
                    "reaches_ocr": probability > processor.rescue_threshold,
                    "expected_skip": expected_skip,
                    "anchored": anchored,
                    "matches_expected": bool(
                        expected_skip is not None
                        and anchored["skip"] == expected_skip
                    ),
                }
                events.append(event)
                per_key[key][name] = {
                    "skip": anchored["skip"],
                    "expected_skip": expected_skip,
                    "selection_reason": anchored["selection_reason"],
                    "probability": probability,
                }
        variant_results[name] = {
            "family": variant["family"],
            "delta": variant["delta"],
            "ocr_calls": counter.calls - before,
            "runtime_seconds": time.perf_counter() - variant_started,
            "events": events,
        }

    key_summary = [
        _summary_for_key(key, observations, len(variants))
        for key, observations in sorted(per_key.items())
    ]
    return {
        "schema_version": "issue277.bar_digit_component_anchor.v1",
        "status": "completed",
        "diagnostic_only": True,
        "stability_artifact": str(stability_path),
        "accepted_rebase": accepted_provenance,
        "rapidocr_providers": providers,
        "contract": {
            "historical_a_geometry_used": False,
            "expected_values_used_for_selection": False,
            "production_source_modified": False,
            "content_anchor": "cross_staff_horizontal_bar_plus_digit_components",
            "canonical_reference_staff_height": REFERENCE_STAFF_HEIGHT,
            "rapidocr_confidence_used_for_selection": False,
            "max_ocr_score_selection": False,
        },
        "sensitive_page_count": len(sensitive),
        "sensitive_measure_count": sum(len(value) for value in sensitive.values()),
        "variant_count": len(variants),
        "ocr_calls": counter.calls,
        "runtime_seconds": time.perf_counter() - started,
        "key_summary": key_summary,
        "variants": variant_results,
    }


def summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    keys = payload["key_summary"]
    return {
        "status": payload["status"],
        "output": str(output),
        "sensitive_page_count": payload["sensitive_page_count"],
        "sensitive_measure_count": payload["sensitive_measure_count"],
        "variant_count": payload["variant_count"],
        "ocr_calls": payload["ocr_calls"],
        "semantic_exact_keys": sum(
            1 for item in keys if item["semantic_exact_across_variants"]
        ),
        "all_variants_expected_keys": sum(
            1 for item in keys if item["all_variants_expected"]
        ),
        "keys": keys,
        "runtime_seconds": payload["runtime_seconds"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--issue294-root", type=Path, default=base.DEFAULT_ISSUE294_ROOT
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--stability-artifact", type=Path, required=True)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=base.DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    try:
        payload = run(args)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary(payload, output), indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic CLI
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
