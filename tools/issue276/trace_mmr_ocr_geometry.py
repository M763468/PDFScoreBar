#!/usr/bin/env python3
"""Trace retained MMR OCR geometry cases without changing production heuristics.

This tool deliberately mirrors the observable parts of ``MMROCREngine``.  It
records every image handed to RapidOCR, but uses the production OCR engine for
candidate parsing and selection.  The mirror is guarded by equality checks so
that the report cannot silently describe different scoring semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACCEPTED_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
REUSE_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
MODEL_PATH = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
OUTPUT_ROOT = PROJECT_ROOT / "logs/issue276_mmr_ocr_geometry_trace"
TARGET_KEYS = {"page_025": (0, 0), "page_055": (1, 1)}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def image_hash(image: Any) -> str:
    """Stable SHA-256 for a NumPy image (including shape and dtype)."""
    array = image
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode())
    digest.update(str(array.dtype).encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


def serialise(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, tuple):
        return [serialise(item) for item in value]
    if isinstance(value, list):
        return [serialise(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): serialise(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def trace_mask_hbar_candidates(engine: Any, image: Any, staff_top_rel: float, staff_height: float):
    """Mirror production masking and return contour decisions plus the image."""
    import cv2
    import numpy as np

    if image is None:
        return image, []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((4, 1), np.uint8)
    thick = cv2.dilate(cv2.erode(binary, kernel, iterations=1), kernel, iterations=1)
    contours, _ = cv2.findContours(thick, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    masked = image.copy()
    center = staff_top_rel + staff_height / 2.0
    records = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        cy = y + height / 2.0
        distance = abs(cy - center)
        selected = width > 40 and height > 4 and distance < 40
        record = {
            "contour_bbox": [x, y, width, height],
            "staff_center": center,
            "distance": distance,
            "masked": selected,
        }
        if selected:
            pad = 5
            rectangle = [
                max(0, x - pad),
                max(0, y - pad),
                min(image.shape[1], x + width + pad),
                min(image.shape[0], y + height + pad),
            ]
            record["mask_rectangle"] = rectangle
            cv2.rectangle(masked, tuple(rectangle[:2]), tuple(rectangle[2:]), (255, 255, 255), -1)
        records.append(record)
    production = engine.mask_hbar_candidates(image, staff_top_rel, staff_height)
    if not np.array_equal(masked, production):
        raise AssertionError("diagnostic hbar mask differs from production output")
    return masked, records


def candidate_trace(engine: Any, ocr_result: list, width: int, height: int) -> dict[str, Any]:
    """Expose production ``select_best_candidate`` semantics candidate by candidate."""
    if not ocr_result:
        expected = engine.select_best_candidate(ocr_result, width, height)
        return {
            "raw_detections": [],
            "numeric_candidates": [],
            "selected": None,
            "production_selection": {
                "number": expected[0],
                "score": expected[1],
                "debug": expected[2],
            },
        }
    candidates = []
    for item, source in engine._candidate_items(ocr_result):
        points, text, confidence = item
        clean = re.sub(r"^[EP](\d)", r"\1", text)
        clean = re.sub(r"[.,;]", "", clean)
        blacklisted = engine._has_blacklisted_text(text)
        values = engine._extract_numeric_candidates(clean, blacklisted)
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        dx, dy, ratio = (
            abs(cx - width / 2.0) / width,
            abs(cy - height / 2.0) / height,
            (y2 - y1) / height,
        )
        for raw_value in values:
            try:
                value = int(raw_value)
            except ValueError:
                continue
            if value < 2:
                continue
            score = 100 - dx * 200 - dy * 100
            if 0.4 <= ratio <= 0.95:
                score += 20
            elif ratio < 0.3:
                score -= 30
            if "=" in text and len(text.split("=")) > 1 and raw_value in text.split("=")[1]:
                score -= 80
            if value > 100:
                score -= 50
            if value > 20 and width < 100:
                score -= 200
            debug = f"dx={dx:.2f},dy={dy:.2f},h={ratio:.2f},{source}"
            if blacklisted:
                debug += ",blacklist_digit"
            candidates.append(
                {
                    "source": source,
                    "raw_text": text,
                    "rapidocr_confidence": float(confidence),
                    "numeric_value": value,
                    "bbox": serialise(points),
                    "bbox_center": [cx, cy],
                    "dist_x_norm": dx,
                    "dist_y_norm": dy,
                    "height_ratio": ratio,
                    "blacklisted": blacklisted,
                    "spatial_score": score,
                    "production_debug": debug,
                }
            )
    candidates.sort(key=lambda item: item["spatial_score"], reverse=True)
    for rank, item in enumerate(candidates, start=1):
        item["ranking"] = rank
        item["selected"] = rank == 1
    selected = candidates[0] if candidates else None
    expected = engine.select_best_candidate(ocr_result, width, height)
    actual = (
        (None, 0, "")
        if selected is None
        else (selected["numeric_value"], selected["spatial_score"], selected["production_debug"])
    )
    if actual != expected:
        raise AssertionError(
            f"candidate trace diverged from production: {actual!r} != {expected!r}"
        )
    return {
        "raw_detections": raw_detection_trace(ocr_result),
        "numeric_candidates": candidates,
        "selected": selected,
        "production_selection": {"number": expected[0], "score": expected[1], "debug": expected[2]},
    }


def raw_detection_trace(ocr_result: Iterable[Any]) -> list[dict[str, Any]]:
    if not ocr_result:
        return []
    return [
        {
            "bbox": serialise(item[0]),
            "raw_text": str(item[1]),
            "rapidocr_confidence": float(item[2]),
        }
        for item in ocr_result
    ]


def perturbations(bbox: Iterable[int]) -> list[dict[str, Any]]:
    """Measure-driven horizontal perturbations; never mutates bbox."""
    base = list(bbox)
    result = [{"name": "baseline", "bbox": base.copy()}]
    for index, name in ((0, "measure_x1"), (2, "measure_x2")):
        for delta in (-2, -1, 1, 2):
            changed = base.copy()
            changed[index] += delta
            result.append({"name": f"{name}{delta:+d}", "bbox": changed})
    for axis, left, right in (("x", 0, 2),):
        for delta in (-2, -1, 1, 2):
            changed = base.copy()
            changed[left] += delta
            changed[right] += delta
            result.append({"name": f"shift_{axis}{delta:+d}", "bbox": changed})
    return result


def staff_perturbations(system: Mapping[str, Any], stave_index: int) -> list[dict[str, Any]]:
    """Return deep-copied, staff-driven vertical OCR-crop perturbations."""
    original = list(system["staves"][stave_index]["bbox"])
    result = [{"name": "baseline", "system": deepcopy(system)}]
    for index, name in ((1, "staff_y1"), (3, "staff_y2")):
        for delta in (-2, -1, 1, 2):
            changed = deepcopy(system)
            changed["staves"][stave_index]["bbox"][index] = original[index] + delta
            result.append({"name": f"{name}{delta:+d}", "system": changed})
    for delta in (-2, -1, 1, 2):
        changed = deepcopy(system)
        for index in (1, 3):
            changed["staves"][stave_index]["bbox"][index] = original[index] + delta
        result.append({"name": f"staff_shift_y{delta:+d}", "system": changed})
    return result


def candidate_image_geometry(
    candidate: Mapping[str, Any], crop_bbox: list[int], angle: float
) -> dict[str, Any]:
    """Map angle=0 RapidOCR processed coordinates through the 20px border."""
    if angle != 0:
        return {"image_coordinate_mapping_available": False}
    points = candidate["bbox"]
    xs, ys = (
        [point[0] + crop_bbox[0] - 20 for point in points],
        [point[1] + crop_bbox[1] - 20 for point in points],
    )
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    return {
        "image_coordinate_mapping_available": True,
        "candidate_image_bbox": bbox,
        "candidate_image_center": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
    }


def first_divergence(left: Mapping[str, Any], right: Mapping[str, Any]) -> str | None:
    stages = (
        "stave_crop_pixels",
        "mask_rectangles",
        "masked_pixels",
        "processed_pixels",
        "rapidocr_raw",
        "numeric_candidates",
        "candidate_ranking",
        "selected_number",
        "final_validity",
    )
    for stage in stages:
        if left.get(stage) != right.get(stage):
            return stage
    return None


class RecordingOCR:
    def __init__(self, wrapped: Any):
        self.wrapped = wrapped
        self.calls = 0
        self.records: list[dict[str, Any]] = []

    def __call__(self, image: Any):
        result, elapsed = self.wrapped(image)
        self.calls += 1
        self.records.append(
            {
                "processed_image_shape": list(image.shape),
                "processed_pixel_hash": image_hash(image),
                "rapidocr": raw_detection_trace(result),
            }
        )
        return result, elapsed

    def begin_view(self) -> None:
        """Compatibility with the Issue #274 production replay wrapper."""
        return None


class RecordingClassifier:
    def __init__(self, wrapped: Any):
        self.wrapped, self.calls = wrapped, 0

    def predict(self, image: Any) -> float:
        self.calls += 1
        return self.wrapped.predict(image)


def trace_view(
    *,
    processor: Any,
    image: Any,
    system: Mapping[str, Any],
    measure: Mapping[str, Any],
    probability: float,
    save_images: bool = False,
    image_root: Path | None = None,
) -> dict[str, Any]:
    """Run a manual, production-equivalent per-view OCR trace."""
    import cv2

    x1, y1, x2, y2 = measure["bbox"]
    height, width = image.shape[:2]
    variants = (
        [("standard", 0)]
        if probability <= processor.threshold
        else [("standard", 0), ("no_dilate", 0), ("heavy_dilate", 0)]
    )
    variant_rows, evidence_by_variant, ocr_calls = [], {}, []
    for mode, angle in variants:
        stave_rows = []
        for stave_index, stave in enumerate(system.get("staves", [])):
            sx1, sx2 = int(max(0, x1 - 30)), int(min(width, x2 + 30))
            sy1, sy2 = int(max(0, stave["bbox"][1] - 80)), int(min(height, stave["bbox"][3] + 80))
            crop = image[sy1:sy2, sx1:sx2]
            if crop.size == 0:
                continue
            masked, mask_records = trace_mask_hbar_candidates(
                processor.ocr, crop, 80, stave["bbox"][3] - stave["bbox"][1]
            )
            processed = processor.ocr.preprocess_variant(masked, mode=mode, angle=angle)
            raw, _ = processor.ocr.ocr_engine(processed)
            traced = candidate_trace(processor.ocr, raw, processed.shape[1], processed.shape[0])
            measure_center = [(x1 + x2) / 2, (y1 + y2) / 2]
            staff_center_y = (stave["bbox"][1] + stave["bbox"][3]) / 2
            for candidate in traced["numeric_candidates"]:
                candidate.update(candidate_image_geometry(candidate, [sx1, sy1, sx2, sy2], angle))
                if candidate.get("image_coordinate_mapping_available"):
                    cx, cy = candidate["candidate_image_center"]
                    candidate.update(
                        {
                            "measure_bbox": list(measure["bbox"]),
                            "measure_center": measure_center,
                            "staff_bbox": list(stave["bbox"]),
                            "staff_center_y": staff_center_y,
                            "candidate_dx_from_measure_center": cx - measure_center[0],
                            "candidate_dx_from_measure_center_norm": (cx - measure_center[0])
                            / max(1, x2 - x1),
                            "candidate_dy_from_measure_center": cy - measure_center[1],
                            "candidate_dy_from_staff_center": cy - staff_center_y,
                            "candidate_dy_from_staff_center_norm": (cy - staff_center_y)
                            / max(1, stave["bbox"][3] - stave["bbox"][1]),
                        }
                    )
                    masked_records = [item for item in mask_records if item["masked"]]
                    if masked_records:
                        nearest = min(
                            masked_records,
                            key=lambda item: (
                                abs(
                                    (item["mask_rectangle"][0] + item["mask_rectangle"][2]) / 2
                                    + sx1
                                    - cx
                                )
                                + abs(
                                    (item["mask_rectangle"][1] + item["mask_rectangle"][3]) / 2
                                    + sy1
                                    - cy
                                )
                            ),
                        )
                        rect = nearest["mask_rectangle"]
                        hx = (rect[0] + rect[2]) / 2 + sx1
                        hy = (rect[1] + rect[3]) / 2 + sy1
                        candidate.update(
                            {
                                "nearest_masked_hbar_bbox": [
                                    rect[0] + sx1,
                                    rect[1] + sy1,
                                    rect[2] + sx1,
                                    rect[3] + sy1,
                                ],
                                "candidate_dx_from_hbar_center": cx - hx,
                                "candidate_dy_from_hbar_center": cy - hy,
                            }
                        )
            evidence = processor._count_high_confidence_one_bar_evidence(raw)
            evidence_by_variant[(mode, angle)] = (
                evidence_by_variant.get((mode, angle), 0) + evidence
            )
            row = {
                "stave_index": stave_index,
                "crop_bbox": [sx1, sy1, sx2, sy2],
                "crop_shape": list(crop.shape),
                "crop_pixel_hash": image_hash(crop),
                "mask_candidates": mask_records,
                "masked_crop_pixel_hash": image_hash(masked),
                "preprocess_mode": mode,
                "rotation_angle": angle,
                "processed_image_shape": list(processed.shape),
                "processed_pixel_hash": image_hash(processed),
                **traced,
            }
            if save_images and image_root is not None:
                image_root.mkdir(parents=True, exist_ok=True)
                stem = f"{mode}_{angle:+d}_stave{stave_index}"
                cv2.imwrite(str(image_root / f"{stem}_crop.png"), crop)
                cv2.imwrite(str(image_root / f"{stem}_masked.png"), masked)
                cv2.imwrite(str(image_root / f"{stem}_processed.png"), processed)
            stave_rows.append(row)
            ocr_calls.append(row)
        valid = [row for row in stave_rows if row["production_selection"]["number"] is not None]
        aggregate = None
        if valid:
            chosen_number = Counter(
                row["production_selection"]["number"] for row in valid
            ).most_common(1)[0][0]
            matching = [
                row for row in valid if row["production_selection"]["number"] == chosen_number
            ]
            best = max(matching, key=lambda row: row["production_selection"]["score"])
            aggregate = {
                "number": chosen_number,
                "score": best["production_selection"]["score"],
                "stave_index": best["stave_index"],
            }
        variant_rows.append(
            {
                "variant": f"{mode}:{angle}",
                "staves": stave_rows,
                "aggregation": aggregate,
                "one_bar_evidence": evidence_by_variant.get((mode, angle), 0),
            }
        )
    usable = [
        row
        for row in variant_rows
        if row["aggregation"] is not None
        and not (row["aggregation"]["number"] > 20 and x2 - x1 < 100)
    ]
    if not usable:
        fallback_configs = (
            ("unmasked_fallback_standard", 80, -30, 30, processor.rescue_threshold),
            ("left_wide_unmasked_fallback_standard", 120, -180, 60, processor.threshold),
        )
        for name, margin_y, dx1, dx2, min_prob in fallback_configs:
            if usable or probability <= min_prob:
                continue
            fallback_staves = []
            for stave_index, stave in enumerate(system.get("staves", [])):
                sx1, sx2 = int(max(0, x1 + dx1)), int(min(width, x2 + dx2))
                sy1, sy2 = (
                    int(max(0, stave["bbox"][1] - margin_y)),
                    int(min(height, stave["bbox"][3] + margin_y)),
                )
                crop = image[sy1:sy2, sx1:sx2]
                if crop.size == 0:
                    continue
                processed = processor.ocr.preprocess_variant(crop, mode="standard", angle=0)
                raw, _ = processor.ocr.ocr_engine(processed)
                traced = candidate_trace(processor.ocr, raw, processed.shape[1], processed.shape[0])
                evidence = processor._count_high_confidence_one_bar_evidence(raw)
                evidence_by_variant[(name, 0)] = evidence_by_variant.get((name, 0), 0) + evidence
                row = {
                    "stave_index": stave_index,
                    "crop_bbox": [sx1, sy1, sx2, sy2],
                    "crop_shape": list(crop.shape),
                    "crop_pixel_hash": image_hash(crop),
                    "mask_candidates": [],
                    "masked_crop_pixel_hash": image_hash(crop),
                    "preprocess_mode": "standard",
                    "rotation_angle": 0,
                    "processed_image_shape": list(processed.shape),
                    "processed_pixel_hash": image_hash(processed),
                    **traced,
                }
                if (
                    traced["production_selection"]["number"] is not None
                    and traced["production_selection"]["score"]
                    > processor.UNMASKED_FALLBACK_MIN_SCORE
                ):
                    fallback_staves.append(row)
                ocr_calls.append(row)
            if fallback_staves:
                chosen_number = Counter(
                    row["production_selection"]["number"] for row in fallback_staves
                ).most_common(1)[0][0]
                matching = [
                    row
                    for row in fallback_staves
                    if row["production_selection"]["number"] == chosen_number
                ]
                best = max(matching, key=lambda row: row["production_selection"]["score"])
                aggregate = {
                    "number": chosen_number,
                    "score": best["production_selection"]["score"],
                    "stave_index": best["stave_index"],
                }
                variant_rows.append(
                    {
                        "variant": f"{name}:0",
                        "staves": fallback_staves,
                        "aggregation": aggregate,
                        "one_bar_evidence": evidence_by_variant[(name, 0)],
                    }
                )
                usable.append(variant_rows[-1])
    final = max(usable, key=lambda row: row["aggregation"]["score"]) if usable else None
    found = None if final is None else final["aggregation"]["number"]
    score = 0 if final is None else final["aggregation"]["score"]
    evidence = max(evidence_by_variant.values(), default=0)
    valid, status, vetoed = processor._valid_status(found, probability, score, evidence)
    return {
        "measure_bbox": list(measure["bbox"]),
        "cnn_probability": probability,
        "variants": variant_rows,
        "one_bar_evidence": evidence,
        "final": {
            "found_num": found,
            "score": score,
            "selected_variant": None if final is None else final["variant"],
            "valid": valid,
            "status": status,
            "vetoed": vetoed,
        },
        "_ocr_calls": ocr_calls,
    }


def compact_stages(trace: Mapping[str, Any]) -> dict[str, Any]:
    calls = trace.get("_ocr_calls", [])
    return {
        "stave_crop_pixels": [row["crop_pixel_hash"] for row in calls],
        "mask_rectangles": [
            [item.get("mask_rectangle") for item in row["mask_candidates"] if item["masked"]]
            for row in calls
        ],
        "masked_pixels": [row["masked_crop_pixel_hash"] for row in calls],
        "processed_pixels": [row["processed_pixel_hash"] for row in calls],
        "rapidocr_raw": [row["raw_detections"] for row in calls],
        "numeric_candidates": [row["numeric_candidates"] for row in calls],
        "candidate_ranking": [
            [(item["numeric_value"], item["ranking"]) for item in row["numeric_candidates"]]
            for row in calls
        ],
        "selected_number": trace["final"]["found_num"],
        "final_validity": trace["final"]["valid"],
    }


def final_selected_candidate(trace: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the candidate that produced the final variant aggregation."""
    final = trace["final"]
    if final["found_num"] is None or final["selected_variant"] is None:
        return None
    variant = next(
        item for item in trace["variants"] if item["variant"] == final["selected_variant"]
    )
    aggregate = variant["aggregation"]
    if aggregate is None:
        return None
    stave = next(
        item for item in variant["staves"] if item["stave_index"] == aggregate["stave_index"]
    )
    return next(
        item
        for item in stave["numeric_candidates"]
        if item["numeric_value"] == final["found_num"]
        and item["spatial_score"] == final["score"]
        and item["selected"]
    )


def production_support_trace(
    processor: Any,
    recorder: Any,
    image: Any,
    page_data: Mapping[str, Any],
    support: Mapping[str, Any],
    page_num: int,
    keys: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    """Reuse the #274 production-exact wrapper for selected retained keys."""
    from tools.issue274.audit_positive_geometry_disagreements import (
        _production_exact_replay,
        slice_one_measure,
    )

    rows = []
    for sys_idx, measure_idx in keys:
        sliced_page, sliced_support = slice_one_measure(page_data, support, sys_idx, measure_idx)
        overrides, calls, predict_calls = _production_exact_replay(
            processor=processor,
            recorder=recorder,
            image=image,
            page_data=sliced_page,
            support=sliced_support,
            page_num=page_num,
        )
        rows.append(
            {
                "key": [sys_idx, measure_idx],
                "overrides": overrides,
                "calls": calls,
                "cnn_calls": predict_calls,
                "support_stats": dict(processor.support_stats),
            }
        )
    return rows


def assert_trace_matches_production(
    processor: Any,
    image: Any,
    system: Mapping[str, Any],
    measure: Mapping[str, Any],
    probability: float,
) -> dict[str, Any]:
    """Assert the diagnostic final agrees with the unchanged production call."""
    height, width = image.shape[:2]
    traced = trace_view(
        processor=processor, image=image, system=system, measure=measure, probability=probability
    )
    x1, y1, x2, y2 = measure["bbox"]
    production = processor._detect_number_with_evidence(
        image, system, x1, y1, x2, y2, probability, width, height
    )
    actual = (traced["final"]["found_num"], traced["final"]["score"], traced["one_bar_evidence"])
    expected = (production[0], production[1], production[3])
    if actual != expected:
        raise AssertionError(f"diagnostic/production mismatch: {actual!r} != {expected!r}")
    return {
        "passed": True,
        "found_num": expected[0],
        "score": expected[1],
        "one_bar_evidence": expected[2],
    }


def preflight() -> dict[str, Any]:
    from tools.issue264.run_phase_c_mmr_regression import build_page_specs

    specs = {spec.page_id: spec for spec in build_page_specs()}
    pages = {}
    for page_id in ("page_025", "page_033", "page_042", "page_055"):
        paths = {
            "image": specs[page_id].image,
            "numbering_base": ACCEPTED_ROOT / "intermediate" / page_id / "numbering_base.json",
            "accepted_geometry": ACCEPTED_ROOT
            / "intermediate"
            / page_id
            / "numbering_mmr_geometry.json",
            "accepted_overrides": ACCEPTED_ROOT / "intermediate" / page_id / "overrides_mmr.json",
            "reuse_support": REUSE_ROOT / "intermediate" / page_id / "mmr_support.json",
        }
        missing = [key for key, path in paths.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"{page_id}: {', '.join(missing)}")
        pages[page_id] = {key: str(path) for key, path in paths.items()}
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(MODEL_PATH)
    return pages


def override_keys(path: Path) -> list[tuple[int, int]]:
    payload = load_json(path)
    rows = payload.get(
        "measure_overrides", payload.get("overrides", payload if isinstance(payload, list) else [])
    )
    return [(int(row["system"]), int(row["measure"])) for row in rows]


def run(
    output_root: Path = OUTPUT_ROOT, *, save_images: bool = False, preflight_only: bool = False
) -> Path:
    pages = preflight()
    if preflight_only:
        path = output_root / "issue276_mmr_ocr_geometry_trace.preflight.json"
        write_json(path, {"preflight": pages})
        return path
    import cv2
    import torch

    from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import create_mmr_rapidocr

    started = time.perf_counter()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for retained Issue #276 OCR tracing")
    recorder = RecordingOCR(create_mmr_rapidocr("cuda"))
    classifier = RecordingClassifier(MMRClassifier(MODEL_PATH, device))
    processor = MMRProcessor(
        MODEL_PATH,
        device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=recorder),
    )
    report: dict[str, Any] = {
        "schema_version": "issue276.mmr_ocr_geometry_trace.v1",
        "evaluation_contract": {
            "production_source_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "numbering_reexecuted": False,
            "full68_mmr_reexecuted": False,
        },
        "targets": pages,
        "cases": {},
        "perturbation_summary": {},
    }
    for page_id, key in TARGET_KEYS.items():
        image = cv2.imread(pages[page_id]["image"])
        h, w = image.shape[:2]
        accepted = load_json(Path(pages[page_id]["accepted_geometry"]))["pages"][0]["systems"][
            key[0]
        ]
        reuse = load_json(Path(pages[page_id]["reuse_support"]))["views"]["primary"]["pages"][0][
            "systems"
        ][key[0]]
        cases = {}
        for name, system in (("accepted_geometry", accepted), ("reuse_geometry", reuse)):
            measure = system["measures"][key[1]]
            x1, y1, x2, y2 = measure["bbox"]
            crop = image[max(0, y1 - 20) : min(h, y2 + 20), max(0, x1 - 20) : min(w, x2 + 20)]
            probability = processor.classifier.predict(crop)
            traced = trace_view(
                processor=processor,
                image=image,
                system=system,
                measure=measure,
                probability=probability,
                save_images=save_images,
                image_root=output_root / "images" / page_id / name,
            )
            traced["diagnostic_vs_production"] = assert_trace_matches_production(
                processor, image, system, measure, probability
            )
            traced["stage_comparison"] = compact_stages(traced)
            traced.pop("_ocr_calls", None)
            cases[name] = traced
        report["cases"][page_id] = {
            "key": list(key),
            "accepted_geometry": cases["accepted_geometry"],
            "reuse_geometry": cases["reuse_geometry"],
            "first_divergent_stage": first_divergence(
                cases["accepted_geometry"]["stage_comparison"],
                cases["reuse_geometry"]["stage_comparison"],
            ),
        }
        perturb = []
        for item in perturbations(reuse["measures"][key[1]]["bbox"]):
            system = deepcopy(reuse)
            system["measures"][key[1]]["bbox"] = item["bbox"]
            measure = system["measures"][key[1]]
            x1, y1, x2, y2 = item["bbox"]
            probability = processor.classifier.predict(
                image[max(0, y1 - 20) : min(h, y2 + 20), max(0, x1 - 20) : min(w, x2 + 20)]
            )
            traced = trace_view(
                processor=processor,
                image=image,
                system=system,
                measure=measure,
                probability=probability,
            )
            perturb.append(
                {
                    "name": item["name"],
                    "bbox": item["bbox"],
                    "found_num": traced["final"]["found_num"],
                    "selected_variant": traced["final"]["selected_variant"],
                    "selected_candidate": final_selected_candidate(traced),
                    "rapidocr_confidences": [
                        candidate["rapidocr_confidence"]
                        for call in traced["_ocr_calls"]
                        for candidate in call["numeric_candidates"]
                    ],
                    "spatial_score": traced["final"]["score"],
                    "validity": traced["final"]["valid"],
                }
            )
        vertical = []
        for stave_index in range(len(reuse.get("staves", []))):
            baseline_crop = None
            for item in staff_perturbations(reuse, stave_index):
                system = item["system"]
                measure = system["measures"][key[1]]
                x1, y1, x2, y2 = measure["bbox"]
                probability = processor.classifier.predict(
                    image[max(0, y1 - 20) : min(h, y2 + 20), max(0, x1 - 20) : min(w, x2 + 20)]
                )
                traced = trace_view(
                    processor=processor,
                    image=image,
                    system=system,
                    measure=measure,
                    probability=probability,
                )
                crop_calls = traced["_ocr_calls"]
                crop = crop_calls[stave_index] if stave_index < len(crop_calls) else crop_calls[0]
                entry = {
                    "name": item["name"],
                    "stave_index": stave_index,
                    "actual_crop_bbox": crop["crop_bbox"],
                    "actual_crop_pixel_hash": crop["crop_pixel_hash"],
                    "found_num": traced["final"]["found_num"],
                    "selected_variant": traced["final"]["selected_variant"],
                    "selected_candidate": final_selected_candidate(traced),
                    "spatial_score": traced["final"]["score"],
                    "validity": traced["final"]["valid"],
                }
                if item["name"] == "baseline":
                    baseline_crop = entry
                else:
                    entry["actual_crop_changed"] = bool(
                        baseline_crop
                        and (
                            entry["actual_crop_bbox"] != baseline_crop["actual_crop_bbox"]
                            or entry["actual_crop_pixel_hash"]
                            != baseline_crop["actual_crop_pixel_hash"]
                        )
                    )
                vertical.append(entry)
        report["perturbation_summary"][page_id] = {
            "horizontal_measure_driven": perturb,
            "vertical_staff_driven": vertical,
        }
    for page_id in ("page_033", "page_042"):
        image = cv2.imread(pages[page_id]["image"])
        h, w = image.shape[:2]
        geometry = load_json(Path(pages[page_id]["accepted_geometry"]))["pages"][0]["systems"]
        controls = []
        for sys_idx, measure_idx in override_keys(Path(pages[page_id]["accepted_overrides"])):
            system = geometry[sys_idx]
            measure = system["measures"][measure_idx]
            x1, y1, x2, y2 = measure["bbox"]
            probability = processor.classifier.predict(
                image[max(0, y1 - 20) : min(h, y2 + 20), max(0, x1 - 20) : min(w, x2 + 20)]
            )
            traced = trace_view(
                processor=processor,
                image=image,
                system=system,
                measure=measure,
                probability=probability,
            )
            traced.pop("_ocr_calls", None)
            controls.append({"key": [sys_idx, measure_idx], "trace": traced})
        report["cases"][page_id] = {
            "control": "one_bar_phase_a_artifact_control"
            if page_id == "page_033"
            else "issue244_accepted_five_overrides",
            "expected_override_count": len(controls),
            "controls": controls,
        }
        support = load_json(Path(pages[page_id]["reuse_support"]))
        page_data = load_json(Path(pages[page_id]["numbering_base"]))
        keys = override_keys(Path(pages[page_id]["accepted_overrides"]))
        if page_id == "page_033":
            causal = load_json(
                PROJECT_ROOT / "logs/issue274_page033_xy_causal/issue274_page033_xy_causal.json"
            )
            keys = sorted(
                {
                    (int(item["system"]), int(item["measure"]))
                    for item in causal.get("detect_calls", [])
                    if item.get("one_bar_veto")
                }
                | set(keys)
            )
        report["cases"][page_id]["actual_reusable_support_path"] = production_support_trace(
            processor, recorder, image, page_data, support, int(page_id.split("_")[1]), keys
        )
    report["runtime"] = {
        "elapsed_sec": time.perf_counter() - started,
        "rapidocr_calls": recorder.calls,
        "cnn_calls": classifier.calls,
    }
    path = output_root / "issue276_mmr_ocr_geometry_trace.json"
    write_json(path, report)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--save-images", action="store_true")
    args = parser.parse_args()
    print(run(args.output_root, save_images=args.save_images, preflight_only=args.preflight))


if __name__ == "__main__":
    main()
