#!/usr/bin/env python3
"""Probe candidate-native MMR sensitivity to small horizontal measure-edge perturbations.

Experiment-only diagnostic for Issue #294. It reuses retained full68 detector/HOMR/SR/OMR
artifacts and reruns only MMR OCR on the A/B-differing focused keys. The probe never uses
historical-A geometry as an input. Instead it perturbs maintained-B measure x edges by
small scale-relative fractions to determine whether the remaining failures are ordinary
crop-boundary sensitivity that can be addressed generically.
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

FRACTIONS = (0.0025, 0.005, 0.01, 0.02)


def _event_map(page: Mapping[str, Any], field: str) -> dict[tuple[int, int], int]:
    return {
        (int(item["system"]), int(item["measure"])): int(item["skip"])
        for item in page.get(field, [])
    }


def _result(value: tuple[Any, Any, Any, Any]) -> dict[str, Any]:
    number, score, debug, evidence = value
    return {
        "number": None if number is None else int(number),
        "skip": None if number is None else int(number) - 1,
        "score": float(score),
        "debug": str(debug),
        "one_bar_evidence": int(evidence),
    }


def _clip_bbox(bbox: list[int], width: int, height: int) -> list[int] | None:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(width - 1, int(x1)))
    x2 = max(1, min(width, int(x2)))
    y1 = max(0, min(height - 1, int(y1)))
    y2 = max(1, min(height, int(y2)))
    if x2 - x1 <= 1 or y2 - y1 <= 1:
        return None
    return [x1, y1, x2, y2]


def _geometry_variants(bbox: list[int], width: int, height: int) -> dict[str, list[int]]:
    x1, y1, x2, y2 = bbox
    measure_width = max(1, x2 - x1)
    result: dict[str, list[int]] = {}
    for fraction in FRACTIONS:
        dx = max(1, int(round(measure_width * fraction)))
        candidates = {
            f"left_in_{fraction:.4f}": [x1 + dx, y1, x2, y2],
            f"right_in_{fraction:.4f}": [x1, y1, x2 - dx, y2],
            f"symmetric_in_{fraction:.4f}": [x1 + dx, y1, x2 - dx, y2],
            f"symmetric_out_{fraction:.4f}": [x1 - dx, y1, x2 + dx, y2],
            f"translate_left_{fraction:.4f}": [x1 - dx, y1, x2 - dx, y2],
            f"translate_right_{fraction:.4f}": [x1 + dx, y1, x2 + dx, y2],
        }
        for name, candidate in candidates.items():
            clipped = _clip_bbox(candidate, width, height)
            if clipped is not None:
                result[name] = clipped
    return result


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
    specs = [spec for spec in build_page_specs() if str(spec.page_id) in differing]
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
    for spec, image_path, support, mapping_mode in zip(specs, images, supports, mapping_modes):
        page_id = str(spec.page_id)
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        height, width = image.shape[:2]
        systems = support["views"]["primary"]["pages"][0]["systems"]
        events: list[dict[str, Any]] = []
        for system_idx, measure_idx in differing[page_id]:
            system = systems[system_idx]
            bbox = [int(v) for v in system["measures"][measure_idx]["bbox"]]
            expected_skip = expected_pages.get(page_id, {}).get((system_idx, measure_idx))
            probes: dict[str, Any] = {}
            for name, probe_bbox in _geometry_variants(bbox, width, height).items():
                x1, y1, x2, y2 = probe_bbox
                margin = 20
                cnn_crop = image[
                    max(0, y1 - margin) : min(height, y2 + margin),
                    max(0, x1 - margin) : min(width, x2 + margin),
                ]
                prob = float(processor.classifier.predict(cnn_crop))
                once = _result(
                    processor._detect_number_with_evidence_once(
                        image, system, x1, y1, x2, y2, prob, width, height
                    )
                )
                policy = _result(
                    processor._detect_number_with_evidence(
                        image, system, x1, y1, x2, y2, prob, width, height
                    )
                )
                probes[name] = {
                    "bbox": probe_bbox,
                    "probability": prob,
                    "once": once,
                    "current_policy": policy,
                    "once_expected": expected_skip is not None and once["skip"] == expected_skip,
                    "policy_expected": expected_skip is not None and policy["skip"] == expected_skip,
                }
            events.append(
                {
                    "system": system_idx,
                    "measure": measure_idx,
                    "expected_skip": expected_skip,
                    "mapping_mode": mapping_mode,
                    "native_bbox": bbox,
                    "probes": probes,
                }
            )
        pages[page_id] = {"events": events}

    return {
        "schema_version": "issue294.post277_edge_jitter.v1",
        "status": "completed",
        "diagnostic_only": True,
        "focused_artifact": str(focused_path),
        "manifest": str(DEFAULT_MANIFEST),
        "fractions": list(FRACTIONS),
        "contract": {
            "historical_a_geometry_used": False,
            "threshold_changes": False,
            "production_dispatch_changes": False,
            "homr_reexecuted": False,
            "classifier_and_rapidocr_reexecuted_only_for_differing_keys": True,
        },
        "pages": pages,
    }


def main() -> int:
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
