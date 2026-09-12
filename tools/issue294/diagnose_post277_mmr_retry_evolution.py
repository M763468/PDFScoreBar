#!/usr/bin/env python3
"""Compare current #277 MMR retry behavior with its pre-review geometry on #294 B keys.

Experiment-only diagnostic. Reuses the completed Issue #294 full68 detector/HOMR/SR/OMR
artifacts and reruns only focused MMR CNN/RapidOCR. It does not change thresholds,
production dispatch, grouping, fixtures, or HOMR outputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

import cv2
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import create_mmr_rapidocr
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue294.diagnose_post277_mmr_decision_path import _differing_keys, _latest_focused
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import _load_json, _load_matrix_pages
from tools.issue294.run_post277_mapping_guarded_mmr import (
    DEFAULT_MANIFEST,
    DEFAULT_MODEL,
    _build_variant_inputs,
)

OFFSETS = (-0.04, -0.02, -0.01, 0.0, 0.01, 0.02, 0.04)


def _tuple(value: tuple[Any, Any, Any, Any]) -> dict[str, Any]:
    number, score, debug, evidence = value
    return {
        "number": None if number is None else int(number),
        "skip": None if number is None else int(number) - 1,
        "score": float(score),
        "debug": str(debug),
        "one_bar_evidence": int(evidence),
    }


def _pair(value: tuple[Any, Any]) -> dict[str, Any]:
    number, score = value
    return {
        "number": None if number is None else int(number),
        "skip": None if number is None else int(number) - 1,
        "score": float(score),
    }


def _legacy_full_span(
    processor: MMRProcessor,
    image: Any,
    measure_bbox: list[int],
    staff_bbox: list[int],
    width: int,
    height: int,
) -> tuple[Any, float]:
    x1, _y1, x2, _y2 = (float(v) for v in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (float(v) for v in staff_bbox)
    staff_height = max(1.0, sy2 - sy1)
    ox1 = max(0, min(width, int(round(x1))))
    ox2 = max(0, min(width, int(round(x2))))
    oy1 = max(0, min(height, int(round(sy1 - 0.5 * staff_height))))
    oy2 = max(0, min(height, int(round(sy2))))
    crop = image[oy1:oy2, ox1:ox2]
    if crop is None or crop.size == 0:
        return None, 0.0
    processed = processor.ocr.preprocess_variant(crop, mode="heavy_dilate", angle=0)
    if processed is None or processed.size == 0:
        return None, 0.0
    raw, _ = processor.ocr.ocr_engine(processed)
    number, score, _debug = processor.ocr.select_best_candidate(
        raw or [], processed.shape[1], processed.shape[0]
    )
    if number is None or number < 2:
        return None, 0.0
    return number, score


def _legacy_shifted(
    processor: MMRProcessor,
    image: Any,
    measure_bbox: list[int],
    staff_bbox: list[int],
    width: int,
    height: int,
) -> tuple[Any, float]:
    x1, _y1, x2, _y2 = (int(v) for v in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (int(v) for v in staff_bbox)
    margin_y = 80
    ox1 = max(0, min(width, x1 - 30))
    ox2 = max(0, min(width, x2 + 30))
    oy1 = max(0, min(height, sy1 - margin_y))
    oy2 = max(0, min(height, sy2 + margin_y))
    crop = image[oy1:oy2, ox1:ox2]
    if crop is None or crop.size == 0:
        return None, 0.0
    crop = processor.ocr.mask_hbar_candidates(crop, margin_y, sy2 - sy1)
    processed = processor.ocr.preprocess_variant(crop, mode="no_dilate", angle=0)
    if processed is None or processed.size == 0:
        return None, 0.0
    raw, _ = processor.ocr.ocr_engine(processed)
    number, score, _debug = processor.ocr.select_best_candidate(
        raw or [], processed.shape[1], processed.shape[0]
    )
    if number is None or number < 2:
        return None, 0.0
    return number, score


def _event_map(page: Mapping[str, Any], field: str) -> dict[tuple[int, int], int]:
    return {
        (int(item["system"]), int(item["measure"])): int(item["skip"])
        for item in page.get(field, [])
    }


def run() -> dict[str, Any]:
    focused_path = _latest_focused()
    focused = _load_json(focused_path)
    differing = _differing_keys(focused)
    expected_pages = {
        str(page["page_id"]): _event_map(page, "expected")
        for page in focused["variants"]["B_b377_mapping_guarded"]["pages"]
    }

    manifest = _load_json(DEFAULT_MANIFEST)
    matrix_pages = _load_matrix_pages(manifest)
    specs_all = build_page_specs(PROJECT_ROOT)
    specs = [spec for spec in specs_all if str(spec.page_id) in differing]
    bases, images, supports, mapping_modes = _build_variant_inputs(
        specs=specs,
        matrix_pages=matrix_pages,
        label="B_b377",
        pipeline_factory=MappingGuardedConnectorPositivePipeline,
    )

    device = torch.device("cuda")
    classifier = MMRClassifier(DEFAULT_MODEL, device)
    rapidocr = create_mmr_rapidocr()
    processor = MMRProcessor(
        DEFAULT_MODEL,
        device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=rapidocr),
    )

    pages: dict[str, Any] = {}
    for spec, base, image_path, support, mapping_mode in zip(
        specs, bases, images, supports, mapping_modes
    ):
        page_id = str(spec.page_id)
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        height, width = image.shape[:2]
        primary = support["views"]["primary"]
        systems = primary["pages"][0]["systems"]
        events: list[dict[str, Any]] = []
        for system_idx, measure_idx in differing[page_id]:
            system = systems[system_idx]
            bbox = [int(v) for v in system["measures"][measure_idx]["bbox"]]
            x1, y1, x2, y2 = bbox
            margin = 20
            crop = image[
                max(0, y1 - margin) : min(height, y2 + margin),
                max(0, x1 - margin) : min(width, x2 + margin),
            ]
            prob = float(processor.classifier.predict(crop))
            baseline = _tuple(
                processor._detect_number_with_evidence_once(
                    image, system, x1, y1, x2, y2, prob, width, height
                )
            )
            current_final = _tuple(
                processor._detect_number_with_evidence(
                    image, system, x1, y1, x2, y2, prob, width, height
                )
            )

            sweep: dict[str, Any] = {}
            measure_width = x2 - x1
            for fraction in OFFSETS:
                sx1 = x1 + int(round(measure_width * fraction))
                sweep[f"{fraction:+.2f}"] = _tuple(
                    processor._detect_number_with_evidence_once(
                        image, system, sx1, y1, x2, y2, prob, width, height
                    )
                )

            current_full = [
                processor._run_targeted_full_span_staff(image, bbox, stave["bbox"], width, height)
                for stave in system.get("staves", [])
            ]
            legacy_full = [
                _legacy_full_span(processor, image, bbox, stave["bbox"], width, height)
                for stave in system.get("staves", [])
            ]
            shifted = processor._targeted_shift_x1(bbox)
            current_shifted = [
                processor._run_targeted_shifted_staff(
                    image, shifted, stave["bbox"], width, height
                )
                for stave in system.get("staves", [])
            ]
            legacy_shifted = [
                _legacy_shifted(processor, image, shifted, stave["bbox"], width, height)
                for stave in system.get("staves", [])
            ]

            expected = expected_pages.get(page_id, {}).get((system_idx, measure_idx))
            events.append(
                {
                    "system": system_idx,
                    "measure": measure_idx,
                    "expected_skip": expected,
                    "mapping_mode": mapping_mode,
                    "bbox": bbox,
                    "probability": prob,
                    "baseline": baseline,
                    "current_policy_final": current_final,
                    "baseline_x1_sweep": sweep,
                    "targeted_full_span": {
                        "current_staff_relative": [_pair(v) for v in current_full],
                        "pre_review_legacy_geometry": [_pair(v) for v in legacy_full],
                    },
                    "targeted_shifted": {
                        "bbox": shifted,
                        "current_staff_relative": [_pair(v) for v in current_shifted],
                        "pre_review_legacy_geometry": [_pair(v) for v in legacy_shifted],
                    },
                    "high_score_baseline_short_circuit": bool(
                        baseline["number"] is not None
                        and baseline["score"] > processor.JITTER_SCORE_TRIGGER
                    ),
                }
            )
        pages[page_id] = {"events": events}

    return {
        "schema_version": "issue294.post277_mmr_retry_evolution.v1",
        "status": "completed",
        "diagnostic_only": True,
        "focused_artifact": str(focused_path),
        "manifest": str(DEFAULT_MANIFEST),
        "contract": {
            "threshold_changes": False,
            "production_dispatch_changes": False,
            "homr_reexecuted": False,
            "classifier_and_rapidocr_reexecuted_only_for_differing_keys": True,
            "legacy_geometry_is_diagnostic_only": True,
        },
        "pages": pages,
    }


def main() -> int:
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
