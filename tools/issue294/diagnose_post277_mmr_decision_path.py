#!/usr/bin/env python3
"""Trace post-#277 MMR decisions on Issue #294 A/B differing focused keys.

This is an experiment-only causal diagnostic. It reconstructs the production-A and
mapping-guarded maintained-B numbering/support views from the retained completed
full68 manifest, automatically selects logical MMR keys whose focused A/B actual
outputs differ, and records the current MMR decision stages:

- primary CNN crop / probability and rescue gate;
- baseline OCR result before #277 targeted retries;
- targeted full-span and +1% x1 retry probes;
- current _detect_number_with_evidence result;
- support-aware alternate veto / Phase-A fallback behavior;
- final override decision.

No thresholds, production dispatch, grouping logic, HOMR artifacts, or fixtures are
changed. OCR probes are diagnostic even when the production CNN rescue gate would
normally prevent OCR from running; this is explicit in the output.
"""

from __future__ import annotations

import argparse
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
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import _load_json, _load_matrix_pages
from tools.issue294.run_post277_mapping_guarded_mmr import (
    DEFAULT_MANIFEST,
    DEFAULT_MODEL,
    _build_variant_inputs,
)

VARIANTS = (
    ("A_production", "A_pinned", MeasureNumberingPipeline),
    ("B_b377_mapping_guarded", "B_b377", MappingGuardedConnectorPositivePipeline),
)


def _latest_focused() -> Path:
    candidates = sorted(
        (PROJECT_ROOT / "logs/issue294").glob("issue294_post277_focused_*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError("No issue294_post277_focused_*.json artifact found")
    return candidates[-1]


def _page_by_id(variant: Mapping[str, Any], page_id: str) -> Mapping[str, Any]:
    for page in variant.get("pages", []):
        if str(page.get("page_id")) == page_id:
            return page
    raise KeyError(f"Variant lacks {page_id}")


def _event_map(page: Mapping[str, Any], field: str) -> dict[tuple[int, int], int]:
    return {
        (int(item["system"]), int(item["measure"])): int(item["skip"])
        for item in page.get(field, [])
    }


def _differing_keys(focused: Mapping[str, Any]) -> dict[str, list[tuple[int, int]]]:
    a = focused["variants"]["A_production"]
    b = focused["variants"]["B_b377_mapping_guarded"]
    a_pages = {str(page["page_id"]): page for page in a["pages"]}
    b_pages = {str(page["page_id"]): page for page in b["pages"]}
    if set(a_pages) != set(b_pages):
        raise RuntimeError("Focused A/B page sets differ")

    result: dict[str, list[tuple[int, int]]] = {}
    for page_id in sorted(a_pages):
        a_actual = _event_map(a_pages[page_id], "actual")
        b_actual = _event_map(b_pages[page_id], "actual")
        keys = sorted(
            key
            for key in set(a_actual) | set(b_actual)
            if a_actual.get(key) != b_actual.get(key)
        )
        if keys:
            result[page_id] = keys
    return result


def _tuple_result(value: tuple[Any, Any, Any, Any]) -> dict[str, Any]:
    number, score, debug, evidence = value
    return {
        "number": None if number is None else int(number),
        "skip": None if number is None else int(number) - 1,
        "score": float(score),
        "debug": str(debug),
        "one_bar_evidence": int(evidence),
    }


def _pair_result(value: tuple[Any, Any]) -> dict[str, Any]:
    number, score = value
    return {
        "number": None if number is None else int(number),
        "skip": None if number is None else int(number) - 1,
        "score": float(score),
    }


def _bbox(payload: Mapping[str, Any], system_idx: int, measure_idx: int) -> list[int]:
    measure = payload["pages"][0]["systems"][system_idx]["measures"][measure_idx]
    return [int(value) for value in measure["bbox"]]


def _event_trace(
    *,
    processor: MMRProcessor,
    base: Mapping[str, Any],
    support: Mapping[str, Any],
    image: Any,
    system_idx: int,
    measure_idx: int,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    primary_page = support["views"]["primary"]
    alternate_page = support["views"]["implicit_start_alternate"]
    fallback_page = support["views"]["fallback"]
    primary_system = primary_page["pages"][0]["systems"][system_idx]
    alternate_system = alternate_page["pages"][0]["systems"][system_idx]
    fallback_system = fallback_page["pages"][0]["systems"][system_idx]

    x1, y1, x2, y2 = _bbox(primary_page, system_idx, measure_idx)
    margin = 20
    crop_bbox = [
        int(max(0, x1 - margin)),
        int(max(0, y1 - margin)),
        int(min(width, x2 + margin)),
        int(min(height, y2 + margin)),
    ]
    cx1, cy1, cx2, cy2 = crop_bbox
    probability = float(processor.classifier.predict(image[cy1:cy2, cx1:cx2]))
    reaches_ocr = probability > processor.rescue_threshold

    # Run the OCR probes even if production would stop at the CNN gate. This is
    # diagnostic only and lets us distinguish a classifier-crop gate flip from an
    # OCR/retry failure using the same candidate-native geometry.
    baseline_raw = processor._detect_number_with_evidence_once(
        image, primary_system, x1, y1, x2, y2, probability, width, height
    )
    baseline = _tuple_result(baseline_raw)

    measure_bbox = [x1, y1, x2, y2]
    full_span_values_raw = [
        processor._run_targeted_full_span_staff(
            image, measure_bbox, stave["bbox"], width, height
        )
        for stave in primary_system.get("staves", [])
    ]
    full_span_aggregate_raw = processor._aggregate_targeted_staff_results(
        full_span_values_raw
    )

    shifted_bbox = processor._targeted_shift_x1(measure_bbox)
    shifted_values_raw = []
    if shifted_bbox[0] != measure_bbox[0]:
        shifted_values_raw = [
            processor._run_targeted_shifted_staff(
                image, shifted_bbox, stave["bbox"], width, height
            )
            for stave in primary_system.get("staves", [])
        ]
    shifted_aggregate_raw = processor._aggregate_targeted_staff_results(
        shifted_values_raw
    )

    primary_final_raw = processor._detect_number_with_evidence(
        image, primary_system, x1, y1, x2, y2, probability, width, height
    )
    primary_final = _tuple_result(primary_final_raw)
    primary_valid, primary_status, primary_vetoed = processor._valid_status(
        primary_final_raw[0], probability, primary_final_raw[1], primary_final_raw[3]
    )

    final_number = primary_final_raw[0]
    final_score = primary_final_raw[1]
    final_evidence = primary_final_raw[3]
    final_valid = bool(primary_valid)
    final_status = str(primary_status)
    final_vetoed = bool(primary_vetoed)
    alternate_trace: dict[str, Any] | None = None
    fallback_trace: dict[str, Any] | None = None

    alternate_bbox = _bbox(alternate_page, system_idx, measure_idx)
    if primary_valid and alternate_bbox[0] != x1:
        alt_raw = processor._detect_number_with_evidence(
            image,
            alternate_system,
            *alternate_bbox,
            probability,
            width,
            height,
        )
        alt_veto = processor._should_veto_one_bar_rest(
            alt_raw[0], probability, alt_raw[1], alt_raw[3]
        )
        alternate_trace = {
            "bbox": alternate_bbox,
            "result": _tuple_result(alt_raw),
            "would_veto_primary": bool(alt_veto),
        }
        if alt_veto:
            final_valid = False
            final_status = "one_bar_veto"
            final_vetoed = True

    # Match _process_page_with_support: fallback is tried only when the primary
    # final OCR number is None and the shared primary CNN probability is >0.5.
    if primary_final_raw[0] is None and probability > processor.threshold:
        fallback_bbox = _bbox(fallback_page, system_idx, measure_idx)
        fallback_raw = processor._detect_number_with_evidence(
            image,
            fallback_system,
            *fallback_bbox,
            probability,
            width,
            height,
        )
        fb_valid, fb_status, fb_vetoed = processor._valid_status(
            fallback_raw[0], probability, fallback_raw[1], fallback_raw[3]
        )
        fallback_trace = {
            "bbox": fallback_bbox,
            "result": _tuple_result(fallback_raw),
            "valid": bool(fb_valid),
            "status": str(fb_status),
            "vetoed": bool(fb_vetoed),
        }
        final_number = fallback_raw[0]
        final_score = fallback_raw[1]
        final_evidence = fallback_raw[3]
        final_valid = bool(fb_valid)
        final_status = str(fb_status)
        final_vetoed = bool(fb_vetoed)

    if not reaches_ocr:
        production_override = None
        production_stop = "cnn_at_or_below_rescue_threshold"
    elif final_valid and final_number is not None:
        production_override = {
            "skip": int(final_number) - 1,
            "number": int(final_number),
            "score": float(final_score),
            "one_bar_evidence": int(final_evidence),
            "status": final_status,
        }
        production_stop = "override_emitted"
    else:
        production_override = None
        production_stop = "ocr_reached_no_valid_override"

    if not reaches_ocr:
        decision_class = "cnn_rescue_gate_stop"
    elif primary_final["debug"].startswith("issue277_targeted_"):
        decision_class = "issue277_targeted_retry_selected"
    elif baseline["number"] is not None and baseline["score"] > processor.JITTER_SCORE_TRIGGER:
        decision_class = "baseline_above_retry_trigger"
    elif fallback_trace is not None:
        decision_class = "phase_a_fallback_path"
    else:
        decision_class = "ocr_path_other"

    return {
        "base_measure_bbox": _bbox(base, system_idx, measure_idx),
        "primary_measure_bbox": measure_bbox,
        "alternate_measure_bbox": alternate_bbox,
        "fallback_measure_bbox": _bbox(fallback_page, system_idx, measure_idx),
        "classifier": {
            "crop_margin_px": margin,
            "crop_bbox": crop_bbox,
            "probability": probability,
            "threshold": float(processor.threshold),
            "rescue_threshold": float(processor.rescue_threshold),
            "production_reaches_ocr": reaches_ocr,
        },
        "baseline_before_targeted_retry": baseline,
        "targeted_full_span": {
            "per_staff": [_pair_result(value) for value in full_span_values_raw],
            "aggregate": _pair_result(full_span_aggregate_raw),
        },
        "targeted_shifted": {
            "bbox": shifted_bbox,
            "per_staff": [_pair_result(value) for value in shifted_values_raw],
            "aggregate": _pair_result(shifted_aggregate_raw),
        },
        "primary_current_final": {
            **primary_final,
            "valid": bool(primary_valid),
            "status": str(primary_status),
            "vetoed": bool(primary_vetoed),
        },
        "alternate": alternate_trace,
        "fallback": fallback_trace,
        "production_override": production_override,
        "production_stop": production_stop,
        "decision_class": decision_class,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()

    focused_path = (args.focused or _latest_focused()).resolve()
    manifest_path = args.manifest.resolve()
    model_path = args.model.resolve()
    focused = _load_json(focused_path)
    manifest = _load_json(manifest_path)
    if manifest.get("status") != "completed" or int(manifest.get("completed_page_count", 0)) != 68:
        raise ValueError("Diagnostic requires the retained completed 68-page manifest")
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    differing = _differing_keys(focused)
    if not differing:
        raise RuntimeError("Focused artifact has no A/B actual-output differences")

    specs_by_id = {str(spec.page_id): spec for spec in build_page_specs()}
    specs = [specs_by_id[page_id] for page_id in differing]
    matrix_pages = _load_matrix_pages(manifest)

    reconstructed: dict[str, dict[str, Any]] = {}
    for variant_name, label, factory in VARIANTS:
        bases, images, supports, mapping_modes = _build_variant_inputs(
            specs=specs,
            matrix_pages=matrix_pages,
            label=label,
            pipeline_factory=factory,
        )
        reconstructed[variant_name] = {
            str(spec.page_id): {
                "base": base,
                "image": image,
                "support": support,
                "mapping_mode": mapping_mode,
            }
            for spec, base, image, support, mapping_mode in zip(
                specs, bases, images, supports, mapping_modes
            )
        }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("MMR decision-path diagnostic requires CUDA")
    classifier = MMRClassifier(model_path, device)
    rapidocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(rapidocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR did not activate CUDA: {providers}")
    processor = MMRProcessor(
        model_path=model_path,
        device=device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=rapidocr),
    )

    focused_variants = {
        "A_production": focused["variants"]["A_production"],
        "B_b377_mapping_guarded": focused["variants"]["B_b377_mapping_guarded"],
    }
    report: dict[str, Any] = {
        "schema_version": "issue294.post277_mmr_decision_path.v1",
        "status": "completed",
        "diagnostic_only": True,
        "focused_artifact": str(focused_path),
        "focused_artifact_git": focused.get("git"),
        "manifest": str(manifest_path),
        "runtime": {"device": str(device), "rapidocr_providers": providers},
        "contract": {
            "threshold_changes": False,
            "production_dispatch_changes": False,
            "grouping_changes": False,
            "homr_reexecuted": False,
            "classifier_and_rapidocr_reexecuted_only_for_differing_keys": True,
            "ocr_probed_even_below_rescue_gate_for_diagnosis": True,
        },
        "pages": {},
    }

    image_cache: dict[str, Any] = {}
    for page_id, keys in differing.items():
        a_page = _page_by_id(focused_variants["A_production"], page_id)
        b_page = _page_by_id(focused_variants["B_b377_mapping_guarded"], page_id)
        a_expected = _event_map(a_page, "expected")
        a_actual = _event_map(a_page, "actual")
        b_actual = _event_map(b_page, "actual")
        page_events = []

        for system_idx, measure_idx in keys:
            event: dict[str, Any] = {
                "system": system_idx,
                "measure": measure_idx,
                "expected_skip": a_expected.get((system_idx, measure_idx)),
                "focused_actual": {
                    "A": a_actual.get((system_idx, measure_idx)),
                    "B": b_actual.get((system_idx, measure_idx)),
                },
                "variants": {},
            }
            for variant_name in ("A_production", "B_b377_mapping_guarded"):
                item = reconstructed[variant_name][page_id]
                image_path = Path(item["image"])
                cache_key = str(image_path)
                if cache_key not in image_cache:
                    image = cv2.imread(cache_key)
                    if image is None:
                        raise FileNotFoundError(image_path)
                    image_cache[cache_key] = image
                trace = _event_trace(
                    processor=processor,
                    base=item["base"],
                    support=item["support"],
                    image=image_cache[cache_key],
                    system_idx=system_idx,
                    measure_idx=measure_idx,
                )
                trace["mapping_mode"] = item["mapping_mode"]
                event["variants"][variant_name] = trace

            a_trace = event["variants"]["A_production"]
            b_trace = event["variants"]["B_b377_mapping_guarded"]
            event["A_to_B"] = {
                "primary_bbox_delta": [
                    b_trace["primary_measure_bbox"][index]
                    - a_trace["primary_measure_bbox"][index]
                    for index in range(4)
                ],
                "classifier_probability_delta": (
                    b_trace["classifier"]["probability"]
                    - a_trace["classifier"]["probability"]
                ),
                "rescue_gate_changed": (
                    b_trace["classifier"]["production_reaches_ocr"]
                    != a_trace["classifier"]["production_reaches_ocr"]
                ),
                "decision_class_changed": (
                    b_trace["decision_class"] != a_trace["decision_class"]
                ),
            }
            page_events.append(event)

        report["pages"][page_id] = {"events": page_events}

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
