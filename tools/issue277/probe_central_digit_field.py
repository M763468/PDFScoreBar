#!/usr/bin/env python3
"""Probe a content-normalized central digit field for Issue #277.

Experiment-only. Visual review of the #277 diagnostics showed that the shape of the
multi-measure-rest body varies too much across engraving styles to be a mandatory
anchor. A more stable semantic is that the printed MMR count is a standalone integer
near the horizontal center of the measure, while boxed rehearsal/measure numbers and
other numbering are commonly near measure boundaries.

This probe therefore:

* uses candidate-native maintained-HOMR geometry only as a broad search envelope;
* searches the central interior of each measure around every staff, above/inside/below;
* removes long horizontal staff-line ink before connected-component grouping;
* OCRs tight content-anchored groups in both original and isolated form;
* accepts only standalone numeric OCR text (no confidence/max-score semantics);
* rejects conflicting original-vs-isolated reads and competing number leaders;
* reports classifier probability stability separately rather than using fixtures.

The same native + +/-1/2/4 px perturbation envelope is replayed on the 20 previously
identified geometry-sensitive measures. Expected fixtures are used only after inference.
"""

from __future__ import annotations

import argparse
import json
import re
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

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
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
CENTRAL_X_MARGIN_FRACTION = 0.18
VERTICAL_OUTER_STAFF_RATIO = 1.35
HORIZONTAL_REMOVE_STAFF_RATIO = 0.40
COMPONENT_MIN_HEIGHT_STAFF = 0.10
COMPONENT_MAX_HEIGHT_STAFF = 1.05
COMPONENT_MIN_WIDTH_STAFF = 0.012
COMPONENT_MAX_WIDTH_STAFF = 0.70
COMPONENT_MIN_AREA_STAFF2 = 0.0015
GROUP_GAP_STAFF = 0.20
GROUP_Y_TOLERANCE_STAFF = 0.30
GROUP_MAX_WIDTH_STAFF = 1.25
GROUP_MAX_HEIGHT_STAFF = 1.10
GROUP_PAD_STAFF = 0.08
SINGLE_CANDIDATE_MAX_CENTER_DISTANCE = 0.20
DEDUP_IOU = 0.70


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _clip(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _bbox_iou(left: list[int], right: list[int]) -> float:
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    ix1, iy1 = max(lx1, rx1), max(ly1, ry1)
    ix2, iy2 = min(lx2, rx2), min(ly2, ry2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    la = max(1, (lx2 - lx1) * (ly2 - ly1))
    ra = max(1, (rx2 - rx1) * (ry2 - ry1))
    return float(inter / max(1, la + ra - inter))


def _strict_numeric_values(ocr: MMROCREngine, raw: Any) -> list[int]:
    if not raw:
        return []
    items = list(raw)
    try:
        merged = ocr.merge_ocr_results(list(raw))
    except Exception:
        merged = list(raw)
    for item in merged:
        if item not in items:
            items.append(item)

    values = []
    for item in items:
        try:
            _points, text, _confidence = item
        except (TypeError, ValueError):
            continue
        normalized = str(text).strip()
        match = re.fullmatch(r"[EP]?(\d{1,3})", normalized)
        if match is None:
            continue
        value = int(match.group(1))
        if value >= 2:
            values.append(value)
    return sorted(set(values))


def _ocr_patch(
    patch: np.ndarray,
    *,
    staff_height: float,
    ocr: MMROCREngine,
) -> dict[str, Any]:
    if patch is None or patch.size == 0:
        return {"number": None, "values": [], "reason": "empty"}
    scale = REFERENCE_STAFF_HEIGHT / max(1.0, staff_height)
    target_w = max(8, int(round(patch.shape[1] * scale)))
    target_h = max(8, int(round(patch.shape[0] * scale)))
    interpolation = cv2.INTER_CUBIC if scale >= 1.0 else cv2.INTER_AREA
    normalized = cv2.resize(patch, (target_w, target_h), interpolation=interpolation)
    processed = ocr.preprocess_variant(
        normalized,
        mode="no_dilate",
        angle=0,
        staff_height=REFERENCE_STAFF_HEIGHT,
        use_staff_relative_geometry=True,
    )
    if processed is None or processed.size == 0:
        return {"number": None, "values": [], "reason": "empty_preprocess"}
    raw, _ = ocr.ocr_engine(processed)
    values = _strict_numeric_values(ocr, raw or [])
    return {
        "number": values[0] if len(values) == 1 else None,
        "values": values,
        "reason": "unique_numeric" if len(values) == 1 else "non_unique_numeric",
    }


def _groups_for_staff(
    image: np.ndarray,
    measure_bbox: list[int],
    staff_bbox: list[int],
    staff_index: int,
    ocr: MMROCREngine,
) -> list[dict[str, Any]]:
    image_h, image_w = image.shape[:2]
    mx1, _my1, mx2, _my2 = (int(v) for v in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (int(v) for v in staff_bbox)
    staff_height = max(1.0, float(sy2 - sy1))
    measure_width = max(2.0, float(mx2 - mx1))
    x_margin = max(1, int(round(CENTRAL_X_MARGIN_FRACTION * measure_width)))
    x1 = _clip(mx1 + x_margin, 0, image_w)
    x2 = _clip(mx2 - x_margin, 0, image_w)
    y1 = _clip(round(sy1 - VERTICAL_OUTER_STAFF_RATIO * staff_height), 0, image_h)
    y2 = _clip(round(sy2 + VERTICAL_OUTER_STAFF_RATIO * staff_height), 0, image_h)
    if x2 <= x1 or y2 <= y1:
        return []

    crop = image[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    h_width = max(3, int(round(HORIZONTAL_REMOVE_STAFF_RATIO * staff_height)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_width, 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    cleaned = cv2.subtract(binary, horizontal)

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(cleaned, 8)
    components: list[dict[str, Any]] = []
    min_area = COMPONENT_MIN_AREA_STAFF2 * staff_height * staff_height
    for label in range(1, count):
        cx, cy, cw, ch, area = (int(v) for v in stats[label])
        if area < min_area:
            continue
        if ch < COMPONENT_MIN_HEIGHT_STAFF * staff_height:
            continue
        if ch > COMPONENT_MAX_HEIGHT_STAFF * staff_height:
            continue
        if cw < COMPONENT_MIN_WIDTH_STAFF * staff_height:
            continue
        if cw > COMPONENT_MAX_WIDTH_STAFF * staff_height:
            continue
        components.append(
            {
                "label": label,
                "bbox": [x1 + cx, y1 + cy, x1 + cx + cw, y1 + cy + ch],
                "center_x": x1 + float(centroids[label][0]),
                "center_y": y1 + float(centroids[label][1]),
                "area": area,
            }
        )

    components.sort(key=lambda item: (int(item["bbox"][0]), int(item["bbox"][1])))
    grouped: list[list[dict[str, Any]]] = []
    for component in components:
        placed = False
        for group in grouped:
            right = max(int(item["bbox"][2]) for item in group)
            gap = int(component["bbox"][0]) - right
            center_y = float(median(item["center_y"] for item in group))
            if (
                gap <= GROUP_GAP_STAFF * staff_height
                and abs(float(component["center_y"]) - center_y)
                <= GROUP_Y_TOLERANCE_STAFF * staff_height
            ):
                group.append(component)
                placed = True
                break
        if not placed:
            grouped.append([component])

    measure_center = (mx1 + mx2) / 2.0
    results = []
    for group in grouped:
        gx1 = min(int(item["bbox"][0]) for item in group)
        gy1 = min(int(item["bbox"][1]) for item in group)
        gx2 = max(int(item["bbox"][2]) for item in group)
        gy2 = max(int(item["bbox"][3]) for item in group)
        width = gx2 - gx1
        height = gy2 - gy1
        if width <= 0 or height <= 0:
            continue
        if width > GROUP_MAX_WIDTH_STAFF * staff_height:
            continue
        if height > GROUP_MAX_HEIGHT_STAFF * staff_height:
            continue

        pad = max(1, int(round(GROUP_PAD_STAFF * staff_height)))
        px1 = _clip(gx1 - pad, 0, image_w)
        py1 = _clip(gy1 - pad, 0, image_h)
        px2 = _clip(gx2 + pad, 0, image_w)
        py2 = _clip(gy2 + pad, 0, image_h)
        original = image[py1:py2, px1:px2]

        local_x1, local_y1 = gx1 - x1, gy1 - y1
        local_x2, local_y2 = gx2 - x1, gy2 - y1
        isolated_mask = np.zeros_like(cleaned)
        for component in group:
            isolated_mask[labels == int(component["label"])] = 255
        ix1 = _clip(local_x1 - pad, 0, isolated_mask.shape[1])
        iy1 = _clip(local_y1 - pad, 0, isolated_mask.shape[0])
        ix2 = _clip(local_x2 + pad, 0, isolated_mask.shape[1])
        iy2 = _clip(local_y2 + pad, 0, isolated_mask.shape[0])
        isolated = np.full((max(1, iy2 - iy1), max(1, ix2 - ix1), 3), 255, np.uint8)
        mask_crop = isolated_mask[iy1:iy2, ix1:ix2]
        if mask_crop.shape[:2] == isolated.shape[:2]:
            isolated[mask_crop > 0] = (0, 0, 0)

        original_ocr = _ocr_patch(original, staff_height=staff_height, ocr=ocr)
        isolated_ocr = _ocr_patch(isolated, staff_height=staff_height, ocr=ocr)
        o_num = original_ocr["number"]
        i_num = isolated_ocr["number"]
        if o_num is not None and i_num is not None and o_num != i_num:
            selected = None
            reason = "original_isolated_conflict"
        elif o_num is not None:
            selected = int(o_num)
            reason = "original_supported"
        elif i_num is not None:
            selected = int(i_num)
            reason = "isolated_supported"
        else:
            selected = None
            reason = "no_unique_numeric"

        results.append(
            {
                "staff": staff_index,
                "bbox": [gx1, gy1, gx2, gy2],
                "center_x": float((gx1 + gx2) / 2.0),
                "center_y": float((gy1 + gy2) / 2.0),
                "center_distance_measure": float(
                    abs((gx1 + gx2) / 2.0 - measure_center) / measure_width
                ),
                "component_count": len(group),
                "original": original_ocr,
                "isolated": isolated_ocr,
                "number": selected,
                "skip": None if selected is None else selected - 1,
                "reason": reason,
            }
        )
    return results


def _dedupe(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for group in sorted(
        groups,
        key=lambda item: (
            float(item["center_distance_measure"]),
            int(item["staff"]),
            float(item["center_x"]),
        ),
    ):
        duplicate = False
        for current in kept:
            if _bbox_iou(group["bbox"], current["bbox"]) >= DEDUP_IOU:
                duplicate = True
                break
        if not duplicate:
            kept.append(group)
    return kept


def _select(groups: list[dict[str, Any]]) -> tuple[Optional[int], str, int]:
    valid = [item for item in groups if item["number"] is not None]
    if not valid:
        return None, "no_numeric_group", 0
    votes = Counter(int(item["number"]) for item in valid)
    support = max(votes.values())
    leaders = [number for number, count in votes.items() if count == support]
    if len(leaders) == 1 and support >= 2:
        return int(leaders[0]), "repeated_content_support", int(support)
    if len(leaders) == 1 and len(valid) == 1:
        only = valid[0]
        if float(only["center_distance_measure"]) <= SINGLE_CANDIDATE_MAX_CENTER_DISTANCE:
            return int(leaders[0]), "unique_centered_numeric", 1
        return None, "single_numeric_too_far_from_center", 1
    return None, "ambiguous_numeric_groups", int(support)


def _evaluate(
    image: np.ndarray,
    system: Mapping[str, Any],
    measure_bbox: list[int],
    ocr: MMROCREngine,
) -> dict[str, Any]:
    groups = []
    for staff_index, stave in enumerate(system.get("staves", [])):
        groups.extend(
            _groups_for_staff(
                image,
                measure_bbox,
                [int(v) for v in stave["bbox"]],
                staff_index,
                ocr,
            )
        )
    groups = _dedupe(groups)
    number, reason, support = _select(groups)
    return {
        "number": number,
        "skip": None if number is None else number - 1,
        "selection_reason": reason,
        "support": support,
        "groups": groups,
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
    ocr = MMROCREngine(ocr_engine=counter)
    classifier = MMRClassifier(args.model, torch.device("cuda"))

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
            "mappings": mappings,
        }

    per_key: dict[str, dict[str, Any]] = defaultdict(dict)
    variant_results: dict[str, Any] = {}
    for variant in variants:
        name = str(variant["name"])
        before = counter.calls
        events = []
        for page_id in sorted(prepared):
            item = prepared[page_id]
            image = item["image"]
            image_h, image_w = image.shape[:2]
            support = stability_probe._perturb_support(
                item["support"], variant, image_w, image_h
            )
            systems = support["views"]["primary"]["pages"][0]["systems"]
            for system_idx, measure_idx in sorted(sensitive[page_id]):
                system = systems[system_idx]
                bbox = [int(v) for v in system["measures"][measure_idx]["bbox"]]
                margin = 20
                cx1 = max(0, bbox[0] - margin)
                cy1 = max(0, bbox[1] - margin)
                cx2 = min(image_w, bbox[2] + margin)
                cy2 = min(image_h, bbox[3] + margin)
                prob = float(classifier.predict(image[cy1:cy2, cx1:cx2]))
                result = _evaluate(image, system, bbox, ocr)
                expected_skip = item["expected"].get((system_idx, measure_idx))
                key = f"{page_id} s{system_idx} m{measure_idx}"
                observation = {
                    "skip": result["skip"],
                    "number": result["number"],
                    "selection_reason": result["selection_reason"],
                    "support": result["support"],
                    "classifier_prob": prob,
                    "classifier_high": prob > 0.5,
                    "expected_skip": expected_skip,
                    "matches_expected": bool(
                        expected_skip is not None and result["skip"] == expected_skip
                    ),
                }
                per_key[key][name] = observation
                events.append({"key": key, **observation})
        variant_results[name] = {
            "family": variant["family"],
            "delta": variant["delta"],
            "ocr_calls": counter.calls - before,
            "events": events,
        }

    key_summary = []
    for key in sorted(per_key):
        values = list(per_key[key].values())
        skips = [item["skip"] for item in values]
        non_null = [value for value in skips if value is not None]
        expected_skip = values[0]["expected_skip"]
        probs = [float(item["classifier_prob"]) for item in values]
        reasons = Counter(str(item["selection_reason"]) for item in values)
        key_summary.append(
            {
                "key": key,
                "expected_skip": expected_skip,
                "variant_count": len(values),
                "non_null_count": len(non_null),
                "skip_counts": {
                    str(number): count
                    for number, count in sorted(Counter(non_null).items())
                },
                "selection_reasons": dict(sorted(reasons.items())),
                "semantic_exact_across_variants": len(set(skips)) == 1,
                "all_variants_expected": bool(
                    expected_skip is not None
                    and len(skips) == len(variants)
                    and all(skip == expected_skip for skip in skips)
                ),
                "classifier_prob_min": min(probs),
                "classifier_prob_max": max(probs),
                "classifier_threshold_crossing": bool(
                    min(probs) <= 0.5 < max(probs)
                ),
            }
        )

    return {
        "schema_version": "issue277.central_digit_field.v1",
        "status": "completed",
        "diagnostic_only": True,
        "accepted_rebase": accepted_provenance,
        "rapidocr_providers": providers,
        "contract": {
            "historical_a_geometry_used": False,
            "expected_values_used_for_selection": False,
            "production_source_modified": False,
            "standalone_numeric_only": True,
            "rapidocr_confidence_used_for_selection": False,
            "measure_edges_excluded": CENTRAL_X_MARGIN_FRACTION,
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
        "classifier_threshold_crossing_keys": sum(
            1 for item in keys if item["classifier_threshold_crossing"]
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
    except Exception as exc:  # pragma: no cover
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
