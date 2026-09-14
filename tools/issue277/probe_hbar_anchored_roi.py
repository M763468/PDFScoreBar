#!/usr/bin/env python3
"""Probe content-anchored MMR OCR on geometry-sensitive measures for Issue #277.

Experiment-only. The previous full68 metamorphic envelope showed that raw measure/staff
crop geometry is too sensitive to +/-1..4 px perturbations. This probe removes the
measure bbox from the final OCR anchor: it detects a plausible thick horizontal
multi-measure-rest bar from image pixels, centers a small digit ROI on that bar,
normalizes the ROI to a reference staff height, and OCRs only that canonical patch.

The previous stability artifact is used only to select the union of geometry-sensitive
measure keys and to define the perturbation variants. Expected fixture values are used
only for evaluation, never for bar selection or OCR selection.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
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
import probe_native_geometry_robustness as base

REFERENCE_STAFF_HEIGHT = 160.0
SEARCH_X_PAD_RATIO = 0.50
SEARCH_Y_ABOVE_RATIO = 0.75
SEARCH_Y_BELOW_RATIO = 0.50
HBAR_KERNEL_HEIGHT_RATIO = 0.025
HBAR_MIN_WIDTH_RATIO = 0.25
HBAR_MIN_HEIGHT_RATIO = 0.025
HBAR_MAX_STAFF_CENTER_DISTANCE_RATIO = 0.30
ROI_HALF_WIDTH_RATIO = 0.75
ROI_TOP_FROM_STAFF_TOP_RATIO = -0.90
ROI_BOTTOM_FROM_STAFF_TOP_RATIO = 0.35


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sensitive_keys(payload: Mapping[str, Any]) -> dict[str, set[tuple[int, int]]]:
    result: dict[str, set[tuple[int, int]]] = defaultdict(set)
    variants = payload.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("stability artifact lacks variants")
    for name, variant in variants.items():
        if name == "native" or not isinstance(variant, Mapping):
            continue
        for change in variant.get("semantic_changes", []):
            result[str(change["page_id"])].add(
                (int(change["system"]), int(change["measure"]))
            )
    if not result:
        raise ValueError("stability artifact contains no sensitive keys")
    return result


def _variant_specs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    variants = payload.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("stability artifact lacks variants")
    result = []
    for name, item in variants.items():
        if not isinstance(item, Mapping):
            continue
        result.append(
            {
                "name": str(name),
                "family": str(item.get("family", "native")),
                "delta": int(item.get("delta", 0)),
            }
        )
    if not result or result[0]["name"] != "native":
        raise ValueError("expected native as first stability variant")
    return result


def _clip(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _find_hbar_candidates(
    image: np.ndarray,
    measure_bbox: list[int],
    staff_bbox: list[int],
) -> list[dict[str, Any]]:
    height, width = image.shape[:2]
    x1, _y1, x2, _y2 = (int(v) for v in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (int(v) for v in staff_bbox)
    staff_height = max(1.0, float(sy2 - sy1))

    ox1 = _clip(round(x1 - SEARCH_X_PAD_RATIO * staff_height), 0, width)
    ox2 = _clip(round(x2 + SEARCH_X_PAD_RATIO * staff_height), 0, width)
    oy1 = _clip(round(sy1 - SEARCH_Y_ABOVE_RATIO * staff_height), 0, height)
    oy2 = _clip(round(sy2 + SEARCH_Y_BELOW_RATIO * staff_height), 0, height)
    if ox2 <= ox1 or oy2 <= oy1:
        return []

    crop = image[oy1:oy2, ox1:ox2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    kernel_height = max(1, int(round(HBAR_KERNEL_HEIGHT_RATIO * staff_height)))
    kernel = np.ones((kernel_height, 1), np.uint8)
    thick = cv2.erode(binary, kernel, iterations=1)
    thick = cv2.dilate(thick, kernel, iterations=1)
    contours, _ = cv2.findContours(thick, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    staff_center_abs = sy1 + staff_height / 2.0
    measure_center_abs = (x1 + x2) / 2.0
    min_width = HBAR_MIN_WIDTH_RATIO * staff_height
    min_height = HBAR_MIN_HEIGHT_RATIO * staff_height
    max_y_distance = HBAR_MAX_STAFF_CENTER_DISTANCE_RATIO * staff_height

    candidates: list[dict[str, Any]] = []
    for cnt in contours:
        cx, cy, cw, ch = cv2.boundingRect(cnt)
        center_x = ox1 + cx + cw / 2.0
        center_y = oy1 + cy + ch / 2.0
        if cw <= min_width or ch <= min_height:
            continue
        if abs(center_y - staff_center_abs) >= max_y_distance:
            continue
        # Content evidence dominates. Measure-center distance is only a deterministic
        # tie-breaker among plausible bars inside a padded search region.
        candidates.append(
            {
                "bbox": [ox1 + cx, oy1 + cy, ox1 + cx + cw, oy1 + cy + ch],
                "center_x": center_x,
                "center_y": center_y,
                "width": int(cw),
                "height": int(ch),
                "staff_height": staff_height,
                "measure_center_distance": abs(center_x - measure_center_abs),
            }
        )

    candidates.sort(
        key=lambda item: (
            -float(item["width"]),
            float(item["measure_center_distance"]),
            float(item["center_x"]),
        )
    )
    return candidates


def _canonical_roi(
    image: np.ndarray,
    staff_bbox: list[int],
    bar: Mapping[str, Any],
) -> tuple[Optional[np.ndarray], Optional[list[int]]]:
    height, width = image.shape[:2]
    _sx1, sy1, _sx2, sy2 = (int(v) for v in staff_bbox)
    staff_height = max(1.0, float(sy2 - sy1))
    center_x = float(bar["center_x"])

    rx1 = _clip(round(center_x - ROI_HALF_WIDTH_RATIO * staff_height), 0, width)
    rx2 = _clip(round(center_x + ROI_HALF_WIDTH_RATIO * staff_height), 0, width)
    ry1 = _clip(round(sy1 + ROI_TOP_FROM_STAFF_TOP_RATIO * staff_height), 0, height)
    ry2 = _clip(round(sy1 + ROI_BOTTOM_FROM_STAFF_TOP_RATIO * staff_height), 0, height)
    if rx2 <= rx1 or ry2 <= ry1:
        return None, None

    roi = image[ry1:ry2, rx1:rx2]
    if roi is None or roi.size == 0:
        return None, None

    scale = REFERENCE_STAFF_HEIGHT / staff_height
    target_w = max(8, int(round(roi.shape[1] * scale)))
    target_h = max(8, int(round(roi.shape[0] * scale)))
    interpolation = cv2.INTER_CUBIC if scale >= 1.0 else cv2.INTER_AREA
    normalized = cv2.resize(roi, (target_w, target_h), interpolation=interpolation)
    return normalized, [rx1, ry1, rx2, ry2]


def _ocr_roi(
    processor: MMRProcessor,
    roi: np.ndarray,
) -> tuple[Optional[int], float, str]:
    processed = processor.ocr.preprocess_variant(
        roi,
        mode="no_dilate",
        angle=0,
        staff_height=REFERENCE_STAFF_HEIGHT,
        use_staff_relative_geometry=True,
    )
    if processed is None or processed.size == 0:
        return None, 0.0, ""
    result, _ = processor.ocr.ocr_engine(processed)
    number, score, debug = processor.ocr.select_best_candidate(
        result or [], processed.shape[1], processed.shape[0]
    )
    if number is None or int(number) < 2:
        return None, 0.0, debug
    return int(number), float(score), str(debug)


def _anchored_measure(
    processor: MMRProcessor,
    image: np.ndarray,
    system: Mapping[str, Any],
    measure_bbox: list[int],
) -> dict[str, Any]:
    staff_results = []
    for staff_index, stave in enumerate(system.get("staves", [])):
        staff_bbox = [int(v) for v in stave["bbox"]]
        bars = _find_hbar_candidates(image, measure_bbox, staff_bbox)
        if not bars:
            staff_results.append(
                {
                    "staff": staff_index,
                    "bar_count": 0,
                    "selected_bar": None,
                    "roi_bbox": None,
                    "number": None,
                    "score": 0.0,
                    "debug": "no_hbar",
                }
            )
            continue
        bar = bars[0]
        roi, roi_bbox = _canonical_roi(image, staff_bbox, bar)
        if roi is None:
            number, score, debug = None, 0.0, "empty_roi"
        else:
            number, score, debug = _ocr_roi(processor, roi)
        staff_results.append(
            {
                "staff": staff_index,
                "bar_count": len(bars),
                "selected_bar": dict(bar),
                "roi_bbox": roi_bbox,
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
    selected: Optional[int] = None
    selected_score = 0.0
    if votes:
        support = max(votes.values())
        leaders = [number for number, count in votes.items() if count == support]
        if len(leaders) == 1:
            selected = leaders[0]
            selected_score = max(
                float(item["score"])
                for item in staff_results
                if item["number"] == selected
            )

    return {
        "number": selected,
        "skip": None if selected is None else selected - 1,
        "score": selected_score,
        "staff_results": staff_results,
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
    sensitive = _sensitive_keys(stability)
    variants = _variant_specs(stability)
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
        v_started = time.perf_counter()
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
                bbox = [int(v) for v in system["measures"][measure_idx]["bbox"]]
                anchored = _anchored_measure(processor, image, system, bbox)
                expected_skip = item["expected"].get((system_idx, measure_idx))
                key = f"{page_id} s{system_idx} m{measure_idx}"
                event = {
                    "key": key,
                    "page_id": page_id,
                    "system": system_idx,
                    "measure": measure_idx,
                    "measure_bbox": bbox,
                    "expected_skip": expected_skip,
                    "anchored": anchored,
                    "matches_expected": bool(
                        expected_skip is not None and anchored["skip"] == expected_skip
                    ),
                }
                events.append(event)
                per_key[key][name] = {
                    "skip": anchored["skip"],
                    "expected_skip": expected_skip,
                    "matches_expected": event["matches_expected"],
                }

        variant_results[name] = {
            "family": variant["family"],
            "delta": variant["delta"],
            "ocr_calls": counter.calls - before,
            "runtime_seconds": time.perf_counter() - v_started,
            "events": events,
        }

    key_summary = []
    for key in sorted(per_key):
        observations = per_key[key]
        skips = [value["skip"] for value in observations.values()]
        non_null = [value for value in skips if value is not None]
        expected_skip = next(iter(observations.values()))["expected_skip"]
        counts = Counter(non_null)
        key_summary.append(
            {
                "key": key,
                "expected_skip": expected_skip,
                "variant_count": len(observations),
                "non_null_count": len(non_null),
                "skip_counts": {str(k): v for k, v in sorted(counts.items())},
                "semantic_exact_across_variants": len(set(skips)) == 1,
                "all_variants_expected": bool(
                    expected_skip is not None
                    and len(skips) == len(variants)
                    and all(value == expected_skip for value in skips)
                ),
            }
        )

    return {
        "schema_version": "issue277.hbar_anchored_roi_probe.v1",
        "status": "completed",
        "diagnostic_only": True,
        "stability_artifact": str(stability_path),
        "accepted_rebase": accepted_provenance,
        "rapidocr_providers": providers,
        "contract": {
            "historical_a_geometry_used": False,
            "expected_values_used_for_selection": False,
            "production_source_modified": False,
            "content_anchor": "detected_thick_horizontal_rest_bar",
            "canonical_reference_staff_height": REFERENCE_STAFF_HEIGHT,
            "measure_bbox_used_only_for_search_window_and_tiebreak": True,
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
