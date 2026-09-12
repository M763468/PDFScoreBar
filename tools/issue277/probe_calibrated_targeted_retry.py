#!/usr/bin/env python3
"""Probe a bounded scale-relative MMR OCR retry for Issue #277.

Experiment-only diagnostic. This builds on probe_native_geometry_robustness.py and
keeps detector/HOMR/SR/OMR plus production thresholds fixed. It tests one causal
hypothesis from the first native-geometry probe:

* the staff-relative horizontal-bar mask was scaled about 4x too aggressively;
* a corrected scale-relative mask, normalized to the legacy geometry at a
  representative 160 px staff height, may recover candidate-native OCR;
* high-score OCR is retried only when the winning OCR path is an unmasked fallback,
  rather than relaxing the score threshold globally.

The proposed bounded decision rule uses two targeted OCR preprocessing views
(no_dilate and standard) on the same shifted, staff-relative crop. A retry result is
usable only when both views agree on the same number. RapidOCR confidence is not
used as semantic truth and expected fixture values never affect selection.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
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

import probe_native_geometry_robustness as base


CALIBRATED_MASK_RATIOS = {
    "kernel_height": 0.025,
    "min_width": 0.25,
    "min_height": 0.025,
    "max_center_distance": 0.25,
    "padding": 0.03125,
}


class CalibratedScaleRelativeOCREngine(MMROCREngine):
    """Experiment-only staff-relative mask calibrated to the legacy 160 px scale."""

    @staticmethod
    def _hbar_mask_geometry(
        staff_height: float, use_staff_relative_geometry: bool
    ) -> tuple[int, int, int, int, int]:
        if not use_staff_relative_geometry:
            return MMROCREngine._hbar_mask_geometry(staff_height, False)

        def scaled(ratio: float) -> int:
            return max(1, int(round(ratio * staff_height)))

        return (
            scaled(CALIBRATED_MASK_RATIOS["kernel_height"]),
            scaled(CALIBRATED_MASK_RATIOS["min_width"]),
            scaled(CALIBRATED_MASK_RATIOS["min_height"]),
            scaled(CALIBRATED_MASK_RATIOS["max_center_distance"]),
            scaled(CALIBRATED_MASK_RATIOS["padding"]),
        )


def _run_calibrated_shifted_staff(
    processor: MMRProcessor,
    counter: base.CountingOCR,
    image: np.ndarray,
    measure_bbox: list[int],
    staff_bbox: list[int],
    mode: str,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    x1, _y1, x2, _y2 = (int(value) for value in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (int(value) for value in staff_bbox)
    staff_height = max(1.0, float(sy2 - sy1))
    margin_x = int(round(staff_height * processor.TARGETED_SHIFTED_X_MARGIN_STAFF_RATIO))
    margin_y = int(round(staff_height * processor.TARGETED_SHIFTED_Y_MARGIN_STAFF_RATIO))
    ox1 = max(0, min(width, x1 - margin_x))
    ox2 = max(0, min(width, x2 + margin_x))
    oy1 = max(0, min(height, sy1 - margin_y))
    oy2 = max(0, min(height, sy2 + margin_y))
    crop = image[oy1:oy2, ox1:ox2]
    if crop is None or crop.size == 0:
        return {"result": base._pair((None, 0.0)), "ocr_calls": 0, "seconds": 0.0}

    staff_top_rel = float(sy1 - oy1)
    mask_geometry = processor.ocr._hbar_mask_geometry(staff_height, True)
    crop = processor.ocr.mask_hbar_candidates(crop, staff_top_rel, staff_height, True)
    if crop is None or crop.size == 0:
        return {"result": base._pair((None, 0.0)), "ocr_calls": 0, "seconds": 0.0}

    processed = processor.ocr.preprocess_variant(
        crop,
        mode=mode,
        angle=0,
        staff_height=staff_height,
        use_staff_relative_geometry=True,
    )
    if processed is None or processed.size == 0:
        return {"result": base._pair((None, 0.0)), "ocr_calls": 0, "seconds": 0.0}

    def run_ocr() -> tuple[Optional[int], float]:
        ocr_result, _ = processor.ocr.ocr_engine(processed)
        number, score, _debug = processor.ocr.select_best_candidate(
            ocr_result or [], processed.shape[1], processed.shape[0]
        )
        if number is None or number < 2:
            return None, 0.0
        return int(number), float(score)

    value, metrics = base._measured(counter, run_ocr)
    return {
        "mode": mode,
        "crop_bbox": [ox1, oy1, ox2, oy2],
        "staff_height": staff_height,
        "mask_geometry": list(mask_geometry),
        "result": base._pair(value),
        **metrics,
    }


def _aggregate(items: list[dict[str, Any]], processor: MMRProcessor) -> dict[str, Any]:
    values = [
        (item["result"]["number"], item["result"]["score"])
        for item in items
    ]
    return base._pair(processor._aggregate_targeted_staff_results(values))


def _two_view_consensus(
    no_dilate: Mapping[str, Any], standard: Mapping[str, Any]
) -> dict[str, Any]:
    left = no_dilate.get("number")
    right = standard.get("number")
    agreed = left is not None and right is not None and int(left) == int(right)
    if not agreed:
        return {"number": None, "skip": None, "score": 0.0, "agreed": False}
    return {
        "number": int(left),
        "skip": int(left) - 1,
        "score": max(float(no_dilate["score"]), float(standard["score"])),
        "agreed": True,
    }


def _simulate_bounded_policy(
    baseline: Mapping[str, Any],
    consensus: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_number = baseline.get("number")
    retry_number = consensus.get("number")
    fallback_origin = "unmasked_fallback" in str(baseline.get("debug", ""))
    trigger = baseline_number is None or fallback_origin

    selected_number = baseline_number
    reason = "baseline_preserved"
    if trigger and retry_number is not None:
        selected_number = retry_number
        reason = "consensus_retry_no_number" if baseline_number is None else "consensus_retry_fallback_origin"
    elif trigger:
        reason = "retry_no_consensus"

    return {
        "trigger": trigger,
        "fallback_origin": fallback_origin,
        "selected_number": selected_number,
        "selected_skip": None if selected_number is None else int(selected_number) - 1,
        "reason": reason,
        "extra_targeted_views_if_triggered": 2,
    }


def _event(
    current: MMRProcessor,
    calibrated: MMRProcessor,
    counter: base.CountingOCR,
    image: np.ndarray,
    support: Mapping[str, Any],
    system_idx: int,
    measure_idx: int,
    expected_skip: int | None,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    primary = support["views"]["primary"]
    system = primary["pages"][0]["systems"][system_idx]
    bbox = base._bbox(primary, system_idx, measure_idx)
    probability = base._cnn_probability(current, image, bbox)

    baseline_raw, baseline_metrics = base._measured(
        counter,
        lambda: current._detect_number_with_evidence_once(
            image, system, *bbox, probability, width, height
        ),
    )
    baseline = base._result(baseline_raw)

    shifted_bbox = calibrated._targeted_shift_x1(bbox)
    no_dilate_staff = [
        _run_calibrated_shifted_staff(
            calibrated,
            counter,
            image,
            shifted_bbox,
            [int(value) for value in stave["bbox"]],
            "no_dilate",
        )
        for stave in system.get("staves", [])
    ]
    standard_staff = [
        _run_calibrated_shifted_staff(
            calibrated,
            counter,
            image,
            shifted_bbox,
            [int(value) for value in stave["bbox"]],
            "standard",
        )
        for stave in system.get("staves", [])
    ]
    no_dilate = _aggregate(no_dilate_staff, calibrated)
    standard = _aggregate(standard_staff, calibrated)
    consensus = _two_view_consensus(no_dilate, standard)
    simulated = _simulate_bounded_policy(baseline, consensus)

    return {
        "system": system_idx,
        "measure": measure_idx,
        "bbox": bbox,
        "shifted_bbox": shifted_bbox,
        "staff_bboxes": [
            [int(value) for value in stave["bbox"]]
            for stave in system.get("staves", [])
        ],
        "probability": probability,
        "expected_skip": expected_skip,
        "baseline": {
            "result": baseline,
            "matches_expected": expected_skip is not None and baseline["skip"] == expected_skip,
            **baseline_metrics,
        },
        "calibrated_mask": {
            "ratios": CALIBRATED_MASK_RATIOS,
            "normalization_reference_staff_height": 160,
            "reference_geometry_at_160": [4, 40, 4, 40, 5],
            "no_dilate": {
                "staff_results": no_dilate_staff,
                "aggregate": no_dilate,
            },
            "standard": {
                "staff_results": standard_staff,
                "aggregate": standard,
            },
            "two_view_consensus": consensus,
        },
        "simulated_bounded_policy": {
            **simulated,
            "matches_expected": (
                expected_skip is not None and simulated["selected_skip"] == expected_skip
            ),
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / base.DEFAULT_MANIFEST_REL).resolve()
    )
    focused_path = (
        args.focused_artifact.resolve()
        if args.focused_artifact is not None
        else base._latest_focused(issue294_root)
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not focused_path.is_file():
        raise FileNotFoundError(focused_path)
    if not args.model.is_file():
        raise FileNotFoundError(args.model)

    started = time.perf_counter()
    manifest = base._load_json(manifest_path)
    matrix_pages = base._load_matrix_pages(manifest, issue294_root)
    expected = base._expected_map(base._load_json(focused_path))
    specs = {str(spec.page_id): spec for spec in base.build_page_specs()}

    raw_ocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(raw_ocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDAExecutionProvider not confirmed: {providers}")
    counter = base.CountingOCR(raw_ocr)
    classifier = MMRClassifier(args.model, torch.device("cuda"))
    current = MMRProcessor(
        args.model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=counter),
    )
    calibrated = MMRProcessor(
        args.model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=CalibratedScaleRelativeOCREngine(ocr_engine=counter),
    )

    targets_by_page: dict[str, list[tuple[int, int]]] = {}
    for page_id, system_idx, measure_idx in base.TARGETS:
        targets_by_page.setdefault(page_id, []).append((system_idx, measure_idx))

    pages: dict[str, Any] = {}
    for page_id, keys in targets_by_page.items():
        spec = specs[page_id]
        matrix_page = matrix_pages[(str(spec.score), str(spec.page_name))]
        _page, image_path, support, mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        events = [
            _event(
                current,
                calibrated,
                counter,
                image,
                support,
                system_idx,
                measure_idx,
                expected.get((page_id, system_idx, measure_idx)),
            )
            for system_idx, measure_idx in keys
        ]
        pages[page_id] = {
            "score": str(spec.score),
            "page_name": str(spec.page_name),
            "image": str(image_path),
            "mapping_mode": mapping_mode,
            "events": events,
        }

    return {
        "schema_version": "issue277.calibrated_targeted_retry_probe.v1",
        "status": "completed",
        "diagnostic_only": True,
        "retained_issue294": {
            "root": str(issue294_root),
            "manifest": str(manifest_path),
            "focused_artifact": str(focused_path),
        },
        "model": str(args.model.resolve()),
        "rapidocr_providers": providers,
        "hypothesis": {
            "current_staff_relative_mask_ratios": [0.10, 1.00, 0.10, 1.00, 0.125],
            "calibrated_staff_relative_mask_ratios": CALIBRATED_MASK_RATIOS,
            "reference_staff_height": 160,
            "legacy_reference_geometry": [4, 40, 4, 40, 5],
            "bounded_trigger": "baseline_none_or_unmasked_fallback_origin",
            "selection": "two_preprocess_views_must_agree; no RapidOCR confidence gate",
        },
        "contract": {
            "historical_a_geometry_used": False,
            "frozen_a_geometry_used": False,
            "expected_values_used_for_selection": False,
            "threshold_changes": False,
            "production_source_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "candidate_native_b_geometry": True,
            "rapidocr_cuda_required": True,
        },
        "ocr_calls_total": counter.calls,
        "runtime_seconds": time.perf_counter() - started,
        "pages": pages,
    }


def _summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    events = []
    for page_id, page in payload["pages"].items():
        for event in page["events"]:
            baseline = event["baseline"]["result"]
            mask = event["calibrated_mask"]
            simulated = event["simulated_bounded_policy"]
            events.append(
                {
                    "key": f"{page_id} s{event['system']} m{event['measure']}",
                    "expected_skip": event["expected_skip"],
                    "baseline_skip": baseline["skip"],
                    "baseline_debug": baseline["debug"],
                    "no_dilate_skip": mask["no_dilate"]["aggregate"]["skip"],
                    "standard_skip": mask["standard"]["aggregate"]["skip"],
                    "consensus_skip": mask["two_view_consensus"]["skip"],
                    "trigger": simulated["trigger"],
                    "selected_skip": simulated["selected_skip"],
                    "matches_expected": simulated["matches_expected"],
                    "reason": simulated["reason"],
                }
            )
    return {
        "status": payload["status"],
        "output": str(output),
        "rapidocr_providers": payload["rapidocr_providers"],
        "ocr_calls_total": payload["ocr_calls_total"],
        "runtime_seconds": payload["runtime_seconds"],
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue294-root", type=Path, default=base.DEFAULT_ISSUE294_ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--focused-artifact", type=Path)
    parser.add_argument("--model", type=Path, default=base.DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        args.output = PROJECT_ROOT / "logs/issue277" / f"calibrated_targeted_retry_{stamp}.json"
    else:
        args.output = args.output.resolve()

    try:
        payload = run(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1

    print(json.dumps(_summary(payload, args.output), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
