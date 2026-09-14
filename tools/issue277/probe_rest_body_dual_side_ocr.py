#!/usr/bin/env python3
"""Probe rest-body-gated dual-side OCR for Issue #277.

Experiment-only. Visual review of the previous diagnostics showed two important
failure modes that the earlier horizontal-bar anchor did not model correctly:

* generic horizontal morphology often anchored to staff lines, not the actual
  multi-measure-rest (MMR) body;
* printed MMR counts can appear either above or below the staff.

This probe therefore removes long thin staff lines inside the measure, detects a
compact MMR body from the remaining staff-band ink, and OCRs narrow canonical
windows both above and below that body. Measure/staff geometry is only a search
window; the final x anchor comes from image content. Expected fixtures are used
only for evaluation after inference.

The same native + +/-1/2/4 px geometry perturbations from the previous full68
stability artifact are replayed on the 20 geometry-sensitive measures.
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
import probe_hbar_anchored_roi as hbar_probe
import probe_native_geometry_robustness as base

REFERENCE_STAFF_HEIGHT = 160.0

# Broad search geometry. These values define a permissive search envelope only;
# the selected body and OCR anchor come from image pixels.
MEASURE_INNER_MARGIN_FRACTION = 0.06
STAFF_BAND_PAD_RATIO = 0.20
LONG_LINE_MIN_MEASURE_FRACTION = 0.68

# MMR-body component/group geometry, normalized by staff height.
BODY_COMPONENT_MIN_AREA_RATIO = 0.0015
BODY_COMPONENT_MIN_WIDTH_RATIO = 0.015
BODY_COMPONENT_MIN_HEIGHT_RATIO = 0.035
BODY_COMPONENT_MAX_HEIGHT_RATIO = 0.95
BODY_GROUP_GAP_RATIO = 0.38
BODY_GROUP_Y_TOLERANCE_RATIO = 0.55
BODY_MIN_WIDTH_RATIO = 0.16
BODY_MAX_WIDTH_RATIO = 5.0
BODY_MIN_HEIGHT_RATIO = 0.055
BODY_MAX_HEIGHT_RATIO = 1.05
BODY_MAX_MEASURE_CENTER_DISTANCE = 0.30
BODY_MIN_INK_SHARE = 0.08
BODY_BEAM_MIN_ASPECT = 1.8
BODY_BEAM_MIN_WIDTH_RATIO = 0.42
BODY_BLOCK_MIN_COMPONENTS = 2
BODY_BLOCK_MIN_WIDTH_RATIO = 0.24
BODY_CLUSTER_TOLERANCE_RATIO = 0.45
MAX_BODY_CANDIDATES_PER_STAFF = 4
MAX_BODY_CLUSTERS = 3

# Number ROI: intentionally symmetric with respect to staff placement because
# the reviewed corpus contains valid counts both above and below the staff.
NUMBER_X_HALF_STAFF_RATIO = 0.78
NUMBER_X_MAX_MEASURE_FRACTION = 0.38
NUMBER_OUTER_Y_STAFF_RATIO = 1.25
NUMBER_INNER_Y_STAFF_RATIO = 0.18


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _clip(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _binary(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    return binary


def _staff_line_suppressed(
    crop: np.ndarray,
    *,
    measure_width: float,
) -> tuple[np.ndarray, np.ndarray]:
    binary = _binary(crop)
    kernel_width = max(7, int(round(LONG_LINE_MIN_MEASURE_FRACTION * measure_width)))
    kernel_width = min(kernel_width, max(7, crop.shape[1]))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 1))
    long_horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    cleaned = cv2.subtract(binary, long_horizontal)
    return cleaned, long_horizontal


def _body_groups_for_staff(
    image: np.ndarray,
    measure_bbox: list[int],
    staff_bbox: list[int],
    staff_index: int,
) -> list[dict[str, Any]]:
    image_h, image_w = image.shape[:2]
    mx1, _my1, mx2, _my2 = (int(v) for v in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (int(v) for v in staff_bbox)
    staff_height = max(1.0, float(sy2 - sy1))
    measure_width = max(2.0, float(mx2 - mx1))

    inner_pad = max(1, int(round(MEASURE_INNER_MARGIN_FRACTION * measure_width)))
    x1 = _clip(mx1 + inner_pad, 0, image_w)
    x2 = _clip(mx2 - inner_pad, 0, image_w)
    y1 = _clip(round(sy1 - STAFF_BAND_PAD_RATIO * staff_height), 0, image_h)
    y2 = _clip(round(sy2 + STAFF_BAND_PAD_RATIO * staff_height), 0, image_h)
    if x2 <= x1 or y2 <= y1:
        return []

    crop = image[y1:y2, x1:x2]
    cleaned, long_horizontal = _staff_line_suppressed(
        crop, measure_width=measure_width
    )
    total_ink = int(np.count_nonzero(cleaned))
    if total_ink <= 0:
        return []

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(cleaned, 8)
    components: list[dict[str, Any]] = []
    min_area = BODY_COMPONENT_MIN_AREA_RATIO * staff_height * staff_height
    for label in range(1, count):
        cx, cy, cw, ch, area = (int(v) for v in stats[label])
        if area < min_area:
            continue
        if cw < BODY_COMPONENT_MIN_WIDTH_RATIO * staff_height:
            continue
        if ch < BODY_COMPONENT_MIN_HEIGHT_RATIO * staff_height:
            continue
        if ch > BODY_COMPONENT_MAX_HEIGHT_RATIO * staff_height:
            continue
        abs_x1 = x1 + cx
        abs_y1 = y1 + cy
        abs_x2 = abs_x1 + cw
        abs_y2 = abs_y1 + ch
        components.append(
            {
                "label": label,
                "bbox": [abs_x1, abs_y1, abs_x2, abs_y2],
                "center_x": x1 + float(centroids[label][0]),
                "center_y": y1 + float(centroids[label][1]),
                "width": cw,
                "height": ch,
                "area": area,
            }
        )

    if not components:
        return []

    components.sort(key=lambda item: (int(item["bbox"][0]), int(item["bbox"][1])))
    groups: list[list[dict[str, Any]]] = []
    for component in components:
        placed = False
        for group in groups:
            right = max(int(item["bbox"][2]) for item in group)
            gap = int(component["bbox"][0]) - right
            center_y = float(median(item["center_y"] for item in group))
            if (
                gap <= BODY_GROUP_GAP_RATIO * staff_height
                and abs(float(component["center_y"]) - center_y)
                <= BODY_GROUP_Y_TOLERANCE_RATIO * staff_height
            ):
                group.append(component)
                placed = True
                break
        if not placed:
            groups.append([component])

    measure_center = (mx1 + mx2) / 2.0
    staff_center = (sy1 + sy2) / 2.0
    results: list[dict[str, Any]] = []
    for group in groups:
        gx1 = min(int(item["bbox"][0]) for item in group)
        gy1 = min(int(item["bbox"][1]) for item in group)
        gx2 = max(int(item["bbox"][2]) for item in group)
        gy2 = max(int(item["bbox"][3]) for item in group)
        width = max(1, gx2 - gx1)
        height = max(1, gy2 - gy1)
        center_x = (gx1 + gx2) / 2.0
        center_y = (gy1 + gy2) / 2.0
        width_staff = width / staff_height
        height_staff = height / staff_height
        center_distance_measure = abs(center_x - measure_center) / measure_width
        center_distance_staff_y = abs(center_y - staff_center) / staff_height
        area = sum(int(item["area"]) for item in group)
        ink_share = area / max(1.0, float(total_ink))
        aspect = width / max(1.0, float(height))

        if width_staff < BODY_MIN_WIDTH_RATIO or width_staff > BODY_MAX_WIDTH_RATIO:
            continue
        if height_staff < BODY_MIN_HEIGHT_RATIO or height_staff > BODY_MAX_HEIGHT_RATIO:
            continue
        if center_distance_measure > BODY_MAX_MEASURE_CENTER_DISTANCE:
            continue
        if center_distance_staff_y > 0.75:
            continue
        if ink_share < BODY_MIN_INK_SHARE:
            continue

        beam_like = bool(
            width_staff >= BODY_BEAM_MIN_WIDTH_RATIO
            and aspect >= BODY_BEAM_MIN_ASPECT
        )
        block_like = bool(
            len(group) >= BODY_BLOCK_MIN_COMPONENTS
            and width_staff >= BODY_BLOCK_MIN_WIDTH_RATIO
        )
        if not (beam_like or block_like):
            continue

        # This score is purely structural. Lower is better.
        structural_score = (
            center_distance_measure
            + 0.20 * center_distance_staff_y
            + 0.10 * (1.0 - min(1.0, ink_share))
            - 0.03 * min(4, len(group))
        )
        results.append(
            {
                "staff": staff_index,
                "staff_bbox": [int(v) for v in staff_bbox],
                "staff_height": staff_height,
                "bbox": [gx1, gy1, gx2, gy2],
                "center_x": float(center_x),
                "center_y": float(center_y),
                "width_staff": float(width_staff),
                "height_staff": float(height_staff),
                "center_distance_measure": float(center_distance_measure),
                "center_distance_staff_y": float(center_distance_staff_y),
                "ink_share": float(ink_share),
                "component_count": len(group),
                "beam_like": beam_like,
                "block_like": block_like,
                "structural_score": float(structural_score),
                "search_bbox": [x1, y1, x2, y2],
                "removed_staff_line_pixels": int(np.count_nonzero(long_horizontal)),
            }
        )

    results.sort(
        key=lambda item: (
            float(item["structural_score"]),
            -float(item["ink_share"]),
            float(item["center_x"]),
        )
    )
    return results[:MAX_BODY_CANDIDATES_PER_STAFF]


def _cluster_body_candidates(
    per_staff: list[list[dict[str, Any]]],
    measure_bbox: list[int],
) -> list[dict[str, Any]]:
    flat = [item for values in per_staff for item in values]
    if not flat:
        return []
    typical_height = float(median(item["staff_height"] for item in flat))
    tolerance = max(1.0, BODY_CLUSTER_TOLERANCE_RATIO * typical_height)
    measure_center = (float(measure_bbox[0]) + float(measure_bbox[2])) / 2.0
    measure_width = max(2.0, float(measure_bbox[2]) - float(measure_bbox[0]))

    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(flat, key=lambda value: float(value["center_x"])):
        best_index: Optional[int] = None
        best_distance: Optional[float] = None
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
        per_staff_best: dict[int, dict[str, Any]] = {}
        for item in cluster:
            staff = int(item["staff"])
            current = per_staff_best.get(staff)
            if current is None or float(item["structural_score"]) < float(
                current["structural_score"]
            ):
                per_staff_best[staff] = item
        bodies = list(per_staff_best.values())
        summarized.append(
            {
                "center_x": center_x,
                "staff_support": len(bodies),
                "measure_center_distance": float(
                    abs(center_x - measure_center) / measure_width
                ),
                "median_structural_score": float(
                    median(item["structural_score"] for item in bodies)
                ),
                "median_ink_share": float(median(item["ink_share"] for item in bodies)),
                "bodies": bodies,
            }
        )

    summarized.sort(
        key=lambda item: (
            -int(item["staff_support"]),
            float(item["measure_center_distance"]),
            float(item["median_structural_score"]),
            -float(item["median_ink_share"]),
        )
    )
    return summarized[:MAX_BODY_CLUSTERS]


def _number_roi(
    image: np.ndarray,
    *,
    body_center_x: float,
    staff_bbox: list[int],
    measure_bbox: list[int],
    side: str,
) -> tuple[Optional[np.ndarray], list[int]]:
    image_h, image_w = image.shape[:2]
    _sx1, sy1, _sx2, sy2 = (int(v) for v in staff_bbox)
    mx1, _my1, mx2, _my2 = (int(v) for v in measure_bbox)
    staff_height = max(1.0, float(sy2 - sy1))
    measure_width = max(2.0, float(mx2 - mx1))
    half_width = min(
        NUMBER_X_HALF_STAFF_RATIO * staff_height,
        NUMBER_X_MAX_MEASURE_FRACTION * measure_width,
    )
    x1 = _clip(round(body_center_x - half_width), 0, image_w)
    x2 = _clip(round(body_center_x + half_width), 0, image_w)

    if side == "above":
        y1 = _clip(round(sy1 - NUMBER_OUTER_Y_STAFF_RATIO * staff_height), 0, image_h)
        y2 = _clip(round(sy1 + NUMBER_INNER_Y_STAFF_RATIO * staff_height), 0, image_h)
    elif side == "below":
        y1 = _clip(round(sy2 - NUMBER_INNER_Y_STAFF_RATIO * staff_height), 0, image_h)
        y2 = _clip(round(sy2 + NUMBER_OUTER_Y_STAFF_RATIO * staff_height), 0, image_h)
    else:
        raise ValueError(side)

    if x2 <= x1 or y2 <= y1:
        return None, [x1, y1, x2, y2]
    roi = image[y1:y2, x1:x2]
    if roi is None or roi.size == 0:
        return None, [x1, y1, x2, y2]
    return roi, [x1, y1, x2, y2]


def _ocr_roi(
    roi: Optional[np.ndarray],
    *,
    staff_height: float,
    ocr: MMROCREngine,
) -> dict[str, Any]:
    if roi is None or roi.size == 0:
        return {"number": None, "skip": None, "score": 0.0, "debug": "empty_roi"}
    scale = REFERENCE_STAFF_HEIGHT / max(1.0, float(staff_height))
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
        return {
            "number": None,
            "skip": None,
            "score": 0.0,
            "debug": "empty_preprocess",
        }
    raw, _ = ocr.ocr_engine(processed)
    number, score, debug = ocr.select_best_candidate(
        raw or [], processed.shape[1], processed.shape[0]
    )
    selected = None if number is None or int(number) < 2 else int(number)
    return {
        "number": selected,
        "skip": None if selected is None else selected - 1,
        "score": float(score) if selected is not None else 0.0,
        "debug": str(debug),
    }


def _evaluate_measure(
    image: np.ndarray,
    system: Mapping[str, Any],
    measure_bbox: list[int],
    ocr: MMROCREngine,
) -> dict[str, Any]:
    per_staff = []
    for staff_index, stave in enumerate(system.get("staves", [])):
        staff_bbox = [int(v) for v in stave["bbox"]]
        per_staff.append(
            _body_groups_for_staff(image, measure_bbox, staff_bbox, staff_index)
        )
    clusters = _cluster_body_candidates(per_staff, measure_bbox)
    if not clusters:
        return {
            "number": None,
            "skip": None,
            "selection_reason": "no_rest_body",
            "body_candidate_counts": [len(values) for values in per_staff],
            "body_cluster_count": 0,
            "selected_body_cluster": None,
            "number_observations": [],
        }

    selected_cluster = clusters[0]
    observations = []
    for body in selected_cluster["bodies"]:
        staff_bbox = [int(v) for v in body["staff_bbox"]]
        staff_height = float(body["staff_height"])
        for side in ("above", "below"):
            roi, roi_bbox = _number_roi(
                image,
                body_center_x=float(selected_cluster["center_x"]),
                staff_bbox=staff_bbox,
                measure_bbox=measure_bbox,
                side=side,
            )
            result = _ocr_roi(roi, staff_height=staff_height, ocr=ocr)
            observations.append(
                {
                    "staff": int(body["staff"]),
                    "side": side,
                    "roi_bbox": roi_bbox,
                    **result,
                }
            )

    votes = Counter(
        int(item["number"])
        for item in observations
        if item["number"] is not None and int(item["number"]) >= 2
    )
    if not votes:
        selected_number = None
        reason = "rest_body_no_number"
    else:
        support = max(votes.values())
        leaders = [number for number, count in votes.items() if count == support]
        if len(leaders) != 1:
            selected_number = None
            reason = "ambiguous_number_votes"
        else:
            selected_number = int(leaders[0])
            competing = [number for number in votes if number != selected_number]
            # One unique number is acceptable regardless of OCR confidence. If multiple
            # different numbers are present, require repeated structural support.
            if competing and support < 2:
                selected_number = None
                reason = "weak_conflicting_number_votes"
            else:
                reason = "body_anchored_number_consensus"

    return {
        "number": selected_number,
        "skip": None if selected_number is None else selected_number - 1,
        "selection_reason": reason,
        "body_candidate_counts": [len(values) for values in per_staff],
        "body_cluster_count": len(clusters),
        "selected_body_cluster": selected_cluster,
        "number_observations": observations,
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
    sensitive = hbar_probe._sensitive_keys(stability)
    variants = hbar_probe._variant_specs(stability)
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
            "image": image,
            "support": support,
            "expected": expected,
            "mapping_mode": mapping_mode,
            "expected_mappings": mappings,
        }

    variant_results: dict[str, Any] = {}
    per_key: dict[str, dict[str, Any]] = defaultdict(dict)

    for variant in variants:
        variant_name = str(variant["name"])
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
            systems = support["views"]["primary"]["pages"][0]["systems"]
            for system_idx, measure_idx in sorted(sensitive[page_id]):
                system = systems[system_idx]
                measure_bbox = [
                    int(v) for v in system["measures"][measure_idx]["bbox"]
                ]
                result = _evaluate_measure(
                    image, system, measure_bbox, processor.ocr
                )
                expected_skip = item["expected"].get((system_idx, measure_idx))
                key = f"{page_id} s{system_idx} m{measure_idx}"
                matches_expected = result["skip"] == expected_skip
                event = {
                    "key": key,
                    "page_id": page_id,
                    "system": system_idx,
                    "measure": measure_idx,
                    "measure_bbox": measure_bbox,
                    "expected_skip": expected_skip,
                    "result": result,
                    "matches_expected": matches_expected,
                }
                events.append(event)
                per_key[key][variant_name] = {
                    "skip": result["skip"],
                    "expected_skip": expected_skip,
                    "selection_reason": result["selection_reason"],
                    "body_cluster_count": result["body_cluster_count"],
                    "matches_expected": matches_expected,
                }

        variant_results[variant_name] = {
            "family": variant["family"],
            "delta": variant["delta"],
            "ocr_calls": counter.calls - before,
            "runtime_seconds": time.perf_counter() - variant_started,
            "events": events,
        }

    key_summary = []
    for key in sorted(per_key):
        observations = per_key[key]
        values = list(observations.values())
        skips = [item["skip"] for item in values]
        expected_skip = values[0]["expected_skip"]
        reasons = Counter(str(item["selection_reason"]) for item in values)
        body_presence = sum(1 for item in values if int(item["body_cluster_count"]) > 0)
        key_summary.append(
            {
                "key": key,
                "expected_skip": expected_skip,
                "variant_count": len(values),
                "non_null_count": sum(skip is not None for skip in skips),
                "skip_counts": {
                    str(number): count
                    for number, count in sorted(
                        Counter(skip for skip in skips if skip is not None).items()
                    )
                },
                "selection_reasons": dict(sorted(reasons.items())),
                "body_present_count": body_presence,
                "semantic_exact_across_variants": len(set(skips)) == 1,
                "all_variants_expected": bool(
                    len(values) == len(variants)
                    and all(item["matches_expected"] for item in values)
                ),
            }
        )

    return {
        "schema_version": "issue277.rest_body_dual_side_ocr.v1",
        "status": "completed",
        "diagnostic_only": True,
        "stability_artifact": str(stability_path),
        "accepted_rebase": accepted_provenance,
        "rapidocr_providers": providers,
        "contract": {
            "historical_a_geometry_used": False,
            "expected_values_used_for_selection": False,
            "production_source_modified": False,
            "candidate_native_b_geometry": True,
            "content_anchor": "staff-line-suppressed MMR body",
            "number_search_sides": ["above", "below"],
            "rapidocr_confidence_used_for_semantic_selection": False,
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
        "--issue294-root",
        type=Path,
        default=base.DEFAULT_ISSUE294_ROOT,
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
