#!/usr/bin/env python3
"""Audit geometry disagreements for completed positive Issue #274 MMR overrides.

This diagnostic reads only retained artifacts and probes the completed positive
MMR keys.  It never scans every measure or invokes detector, HOMR, SR, OMR-DLN,
or numbering.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from tools.issue264.phase_c_fixture_rebase import normalise_overrides, rebase_expected_overrides

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REUSE_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
ACCEPTED_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
PAGE_INPUTS = PROJECT_ROOT / "logs/issue94_mmr_current_state/page_inputs.json"
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures"
MODEL_PATH = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
OUTPUT_ROOT = PROJECT_ROOT / "logs/issue274_positive_geometry_audit"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def _skip(item: Mapping[str, Any]) -> int:
    return int(item.get("skip") or 0)


def _index(payload: Any) -> dict[tuple[int, int, int], dict[str, Any]]:
    return {_key(item): item for item in normalise_overrides(payload)}


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_file():
        return path
    if not path.is_absolute() and (candidate := PROJECT_ROOT / path).is_file():
        return candidate
    if "/workspace/" in str(path):
        candidate = PROJECT_ROOT / str(path).split("/workspace/", 1)[1]
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(path)


def _legacy_page_inputs() -> list[Mapping[str, Any]]:
    payload = _load_json(PAGE_INPUTS)
    pages = payload.get("pages") if isinstance(payload, Mapping) else None
    expected_ids = [f"page_{index:03d}" for index in range(1, 69)]
    if not isinstance(pages, list) or [page.get("page_id") for page in pages] != expected_ids:
        raise ValueError("Historical page inputs must be the unique page_001..page_068 sequence")
    return pages


def _view_differs(primary: Mapping[str, Any], alternate: Mapping[str, Any]) -> bool:
    return list(primary["bbox"]) != list(alternate["bbox"])


def _p1_consensus(audit: Mapping[str, Any]) -> bool:
    primary, fallback, alternate = (
        audit["views"]["primary"],
        audit["views"]["fallback"],
        audit["views"].get("implicit_start_alternate"),
    )
    return bool(
        audit["implicit_start"]
        and alternate is not None
        and primary["selected_found_num"] != fallback["selected_found_num"]
        and alternate["selected_found_num"] != primary["selected_found_num"]
        and fallback["selected_found_num"] == alternate["selected_found_num"]
        and fallback["valid_positive"]
        and alternate["valid_positive"]
    )


def _p2_disagreement(audit: Mapping[str, Any]) -> bool:
    primary, fallback = audit["views"]["primary"], audit["views"]["fallback"]
    return bool(
        primary["valid_positive"]
        and fallback["valid_positive"]
        and primary["selected_found_num"] != fallback["selected_found_num"]
    )


def _variant_from_debug(debug: str) -> str | None:
    return debug.rsplit("variant=", 1)[1] if "variant=" in debug else None


def _json_value(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _raw_candidates(ocr_result: Any) -> list[dict[str, Any]]:
    candidates = []
    if not isinstance(ocr_result, list):
        return candidates
    for item in ocr_result:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        text, confidence = str(item[1]), item[2]
        candidates.append(
            {
                "raw_text": text,
                "confidence": float(confidence),
                "bbox": _json_value(item[0]),
                "numeric_candidates": [int(value) for value in re.findall(r"\d+", text)],
            }
        )
    return candidates


class _RecordingRapidOCR:
    def __init__(self, wrapped: Any):
        self.wrapped = wrapped
        self.current_records: list[dict[str, Any]] = []
        self.calls = 0

    def begin_view(self) -> None:
        self.current_records = []

    def __call__(self, image: Any):
        result, elapsed = self.wrapped(image)
        self.calls += 1
        self.current_records.append({"candidates": _raw_candidates(result)})
        return result, elapsed


def _probe_view(
    *,
    processor: Any,
    recorder: _RecordingRapidOCR,
    image: Any,
    system: Mapping[str, Any],
    measure: Mapping[str, Any],
    image_width: int,
    image_height: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    x1, y1, x2, y2 = measure["bbox"]
    margin = 20
    cx1, cy1 = int(max(0, x1 - margin)), int(max(0, y1 - margin))
    cx2, cy2 = int(min(image_width, x2 + margin)), int(min(image_height, y2 + margin))
    probability = processor.classifier.predict(image[cy1:cy2, cx1:cx2])
    recorder.begin_view()
    found_number, score, debug, one_bar_evidence = processor._detect_number_with_evidence(
        image, system, x1, y1, x2, y2, probability, image_width, image_height
    )
    valid_positive, status_label, vetoed = processor._valid_status(
        found_number, probability, score, one_bar_evidence
    )
    return (
        {
            "measure_bbox": measure["bbox"],
            "staff_bboxes": [staff["bbox"] for staff in system.get("staves", [])],
            "cnn_probability": probability,
            "selected_found_num": found_number,
            "selected_score": score,
            "debug_candidate": debug,
            "ocr_variant": _variant_from_debug(debug),
            "one_bar_evidence": one_bar_evidence,
            "valid_positive": valid_positive,
            "status_label": status_label,
            "vetoed": vetoed,
        },
        deepcopy(recorder.current_records),
    )


def _build_rebased_gt(
    page_inputs: list[Mapping[str, Any]],
) -> dict[str, dict[tuple[int, int, int], dict[str, Any]]]:
    rebased: dict[str, dict[tuple[int, int, int], dict[str, Any]]] = {}
    for global_index, page in enumerate(page_inputs):
        page_id = str(page["page_id"])
        fixture_path = FIXTURE_ROOT / f"expected_overrides_{page_id}.json"
        fixture = _load_json(fixture_path) if fixture_path.is_file() else {"overrides": []}
        if normalise_overrides(fixture):
            historical_path = _resolve_project_path(str(page["numbering_base"]))
            current_path = ACCEPTED_ROOT / "intermediate" / page_id / "numbering_base.json"
            expected, _mappings = rebase_expected_overrides(
                fixture,
                _load_json(historical_path),
                _load_json(current_path),
                global_page_index=global_index,
            )
        else:
            expected = {"overrides": []}
        rebased[page_id] = _index(expected)
    return rebased


def _score(
    expected_by_page: Mapping[str, Mapping[tuple[int, int, int], Mapping[str, Any]]],
    detected_by_page: Mapping[str, Mapping[tuple[int, int, int], Mapping[str, Any]]],
) -> dict[str, Any]:
    names = ("expected", "detected", "matched_tp", "missed_fn", "skip_mismatch", "unexpected_fp")
    totals = {name: 0 for name in names}
    zero_expected_pages = 0
    zero_expected_page_detections = 0
    for page_id, expected in expected_by_page.items():
        detected = detected_by_page[page_id]
        for key, item in expected.items():
            totals["expected"] += 1
            actual = detected.get(key)
            if actual is None:
                totals["missed_fn"] += 1
            elif _skip(actual) == _skip(item):
                totals["matched_tp"] += 1
            else:
                totals["skip_mismatch"] += 1
        for key in detected:
            totals["detected"] += 1
            if key not in expected:
                totals["unexpected_fp"] += 1
        if not expected:
            zero_expected_pages += 1
            zero_expected_page_detections += len(detected)
    precision = totals["matched_tp"] / totals["detected"] if totals["detected"] else 0.0
    recall = totals["matched_tp"] / totals["expected"] if totals["expected"] else 0.0
    return {
        **totals,
        "pages": len(expected_by_page),
        "zero_expected_pages": zero_expected_pages,
        "zero_expected_page_detections": zero_expected_page_detections,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _state(item: Mapping[str, Any] | None, expected: Mapping[str, Any] | None) -> str:
    if expected is None:
        return "not_represented_in_gt"
    if item is None:
        return "absent"
    return "exact" if _skip(item) == _skip(expected) else "skip_mismatch"


def _classify_change(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    expected: Mapping[str, Any] | None,
) -> str:
    if expected is None:
        return "not_represented_in_gt"
    before_state, after_state = _state(before, expected), _state(after, expected)
    if after_state == "exact" and before_state != "exact":
        return "improvement"
    if before_state == "exact" and after_state != "exact":
        return "regression"
    return "neutral"


def _apply_projection(
    *,
    name: str,
    current: Mapping[str, Mapping[tuple[int, int, int], dict[str, Any]]],
    audits: Mapping[tuple[int, int, int], Mapping[str, Any]],
    expected: Mapping[str, Mapping[tuple[int, int, int], Mapping[str, Any]]],
) -> tuple[dict[str, dict[tuple[int, int, int], dict[str, Any]]], list[dict[str, Any]]]:
    projected = deepcopy(current)
    changes = []
    for key, audit in audits.items():
        page_id = audit["page_id"]
        current_item = projected[page_id][key]
        p1 = _p1_consensus(audit)
        p2 = _p2_disagreement(audit)
        action = None
        if name in ("P1", "P3") and p1:
            current_item["skip"] = audit["views"]["fallback"]["selected_found_num"] - 1
            current_item["comment"] = "diagnostic_projection:P1_implicit_consensus"
            action = "recovered"
        elif name in ("P2", "P3") and p2 and not p1:
            del projected[page_id][key]
            action = "suppressed"
        if action:
            before = current[page_id][key]
            after = projected[page_id].get(key)
            changes.append(
                {
                    "key": list(key),
                    "page_id": page_id,
                    "action": action,
                    "before_skip": _skip(before),
                    "after_skip": _skip(after) if after is not None else None,
                    "classification": _classify_change(before, after, expected[page_id].get(key)),
                }
            )
    return projected, changes


def run_legacy(output_root: Path = OUTPUT_ROOT) -> Path:
    import cv2
    import torch

    from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import (
        collect_rapidocr_providers,
        create_mmr_rapidocr,
        providers_include_cuda,
    )
    from tools.issue264.run_phase_c_mmr_regression import build_page_specs

    started = time.perf_counter()
    page_inputs = _legacy_page_inputs()
    specs = {spec.page_id: spec for spec in build_page_specs()}
    current_by_page = {
        str(page["page_id"]): _index(
            _load_json(REUSE_ROOT / "intermediate" / str(page["page_id"]) / "overrides_mmr.json")
        )
        for page in page_inputs
    }
    positive_keys = [key for items in current_by_page.values() for key in items]
    if not positive_keys:
        raise ValueError("No positive Issue #274 MMR overrides found")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for this positive-key MMR audit")
    classifier = MMRClassifier(MODEL_PATH, device)
    provider = create_mmr_rapidocr("cuda")
    recorder = _RecordingRapidOCR(provider)
    processor = MMRProcessor(
        model_path=MODEL_PATH,
        device=device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=recorder),
    )

    audits: dict[tuple[int, int, int], dict[str, Any]] = {}
    raw_by_key: dict[tuple[int, int, int], dict[str, Any]] = {}
    primary_calls = 0
    for global_index, page_input in enumerate(page_inputs):
        page_id = str(page_input["page_id"])
        page_keys = sorted(current_by_page[page_id])
        if not page_keys:
            continue
        spec = specs[page_id]
        image = cv2.imread(str(spec.image))
        if image is None:
            raise RuntimeError(f"Could not read image: {spec.image}")
        image_height, image_width = image.shape[:2]
        support = _load_json(REUSE_ROOT / "intermediate" / page_id / "mmr_support.json")
        views = {
            name: support["views"][name]["pages"][0]["systems"]
            for name in ("primary", "fallback", "implicit_start_alternate")
        }
        print(f"Auditing positive keys: {page_id} ({len(page_keys)})", flush=True)
        for key in page_keys:
            _page, system_index, measure_index = key
            primary_system = views["primary"][system_index]
            primary_measure = primary_system["measures"][measure_index]
            primary, primary_raw = _probe_view(
                processor=processor,
                recorder=recorder,
                image=image,
                system=primary_system,
                measure=primary_measure,
                image_width=image_width,
                image_height=image_height,
            )
            primary_calls += len(primary_raw)
            fallback_system = views["fallback"][system_index]
            fallback_measure = fallback_system["measures"][measure_index]
            fallback, fallback_raw = _probe_view(
                processor=processor,
                recorder=recorder,
                image=image,
                system=fallback_system,
                measure=fallback_measure,
                image_width=image_width,
                image_height=image_height,
            )
            alternate_system = views["implicit_start_alternate"][system_index]
            alternate_measure = alternate_system["measures"][measure_index]
            implicit_start = _view_differs(primary_measure, alternate_measure)
            alternate = None
            alternate_raw: list[dict[str, Any]] = []
            if implicit_start:
                alternate, alternate_raw = _probe_view(
                    processor=processor,
                    recorder=recorder,
                    image=image,
                    system=alternate_system,
                    measure=alternate_measure,
                    image_width=image_width,
                    image_height=image_height,
                )
            audit = {
                "page_id": page_id,
                "key": list(key),
                "existing_override": current_by_page[page_id][key],
                "implicit_start": implicit_start,
                "views": {
                    "primary": primary,
                    "fallback": fallback,
                    "implicit_start_alternate": alternate,
                },
            }
            expected_found_num = _skip(current_by_page[page_id][key]) + 1
            audit["primary_reproduces_existing_override"] = (
                primary["selected_found_num"] == expected_found_num
            )
            if (
                len(
                    {
                        primary["selected_found_num"],
                        fallback["selected_found_num"],
                        None if alternate is None else alternate["selected_found_num"],
                    }
                )
                > 1
            ):
                raw_by_key[key] = {
                    "primary": primary_raw,
                    "fallback": fallback_raw,
                    "implicit_start_alternate": alternate_raw if alternate is not None else None,
                }
            audits[key] = audit

    reproducibility_mismatches = [
        audit for audit in audits.values() if not audit["primary_reproduces_existing_override"]
    ]
    base_report = {
        "schema_version": "issue274.positive_geometry_audit.v1",
        "evaluation_contract": {
            "production_source_modified": False,
            "full68_mmr_scan": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "numbering_reexecuted": False,
            "classifier_initialization_count": 1,
            "rapidocr_initialization_count": 1,
        },
        "runtime": {"elapsed_sec": time.perf_counter() - started},
        "evaluated_positive_keys": len(audits),
        "ocr_calls_total": recorder.calls,
        "extra_ocr_calls": recorder.calls - primary_calls,
        "primary_reproducibility": {
            "passed": not reproducibility_mismatches,
            "mismatch_count": len(reproducibility_mismatches),
            "mismatches": reproducibility_mismatches,
        },
        "support_stats": processor.support_stats,
        "rapidocr": {
            "providers": collect_rapidocr_providers(provider),
            "cuda_confirmed": providers_include_cuda(collect_rapidocr_providers(provider)),
        },
        "audits": list(audits.values()),
        "raw_ocr_for_disagreements": [
            {"key": list(key), "views": raw} for key, raw in sorted(raw_by_key.items())
        ],
    }
    output_path = output_root / "issue274_positive_geometry_audit.json"
    if reproducibility_mismatches:
        base_report["status"] = "stopped_runtime_nondeterminism_or_contract_mismatch"
        _write_json(output_path, base_report)
        print(f"report: {output_path}")
        return output_path

    expected_by_page = _build_rebased_gt(page_inputs)
    policies = {"current": (deepcopy(current_by_page), [])}
    for policy in ("P1", "P2", "P3"):
        policies[policy] = _apply_projection(
            name=policy,
            current=current_by_page,
            audits=audits,
            expected=expected_by_page,
        )
    projections = {}
    for name, (projection, changes) in policies.items():
        metrics = _score(expected_by_page, projection)
        projections[name] = {
            "metrics": metrics,
            "changed_pages": sorted({change["page_id"] for change in changes}),
            "recovered_keys": [change for change in changes if change["action"] == "recovered"],
            "suppressed_keys": [change for change in changes if change["action"] == "suppressed"],
            "acceptance": {
                "passed": metrics["unexpected_fp"] == 0
                and metrics["missed_fn"] <= 3
                and metrics["skip_mismatch"] <= 6,
                "unexpected_fp_zero": metrics["unexpected_fp"] == 0,
                "missed_fn_not_above_3": metrics["missed_fn"] <= 3,
                "skip_mismatch_not_above_6": metrics["skip_mismatch"] <= 6,
            },
        }
    base_report.update(
        {
            "status": "completed",
            "projections": projections,
            "focused": {
                page_id: next(audit for audit in audits.values() if audit["page_id"] == page_id)
                for page_id in ("page_025", "page_055", "page_033", "page_042")
                if any(audit["page_id"] == page_id for audit in audits.values())
            },
        }
    )
    _write_json(output_path, base_report)
    print(
        json.dumps(
            {
                "evaluated_positive_keys": len(audits),
                "projections": {name: item["metrics"] for name, item in projections.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"report: {output_path}")
    return output_path


def slice_one_measure(
    page_data: Mapping[str, Any], support: Mapping[str, Any], sys_idx: int, measure_idx: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Retain one system/measure while preserving its original staff geometry."""

    sliced_page_data = deepcopy(page_data)
    page = sliced_page_data["pages"][0]
    system = deepcopy(page["systems"][sys_idx])
    system["measures"] = [deepcopy(system["measures"][measure_idx])]
    page["systems"] = [system]

    sliced_support = deepcopy(support)
    for view in ("primary", "fallback", "implicit_start_alternate"):
        view_page = sliced_support["views"][view]["pages"][0]
        view_system = deepcopy(view_page["systems"][sys_idx])
        view_system["measures"] = [deepcopy(view_system["measures"][measure_idx])]
        view_page["systems"] = [view_system]
    return sliced_page_data, sliced_support


def _production_exact_replay(
    *,
    processor: Any,
    recorder: _RecordingRapidOCR,
    image: Any,
    page_data: Mapping[str, Any],
    support: Mapping[str, Any],
    page_num: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Call the production support state machine unchanged for one sliced measure."""

    height, width = image.shape[:2]
    primary_system = support["views"]["primary"]["pages"][0]["systems"][0]
    fallback_system = support["views"]["fallback"]["pages"][0]["systems"][0]
    alternate_system = support["views"]["implicit_start_alternate"]["pages"][0]["systems"][0]
    labels = {
        id(primary_system): "primary",
        id(fallback_system): "fallback",
        id(alternate_system): "implicit_start_alternate",
    }
    traces: list[dict[str, Any]] = []
    predict_calls = 0
    original_predict = processor.classifier.predict
    original_detect = processor._detect_number_with_evidence

    def traced_predict(crop: Any) -> float:
        nonlocal predict_calls
        predict_calls += 1
        return original_predict(crop)

    def traced_detect(image_arg, system, x1, y1, x2, y2, prob, w_img, h_img):
        recorder.begin_view()
        found_num, score, debug, one_bar_evidence = original_detect(
            image_arg, system, x1, y1, x2, y2, prob, w_img, h_img
        )
        traces.append(
            {
                "view": labels.get(id(system), "unknown"),
                "bbox": [x1, y1, x2, y2],
                "passed_prob": prob,
                "found_num": found_num,
                "score": score,
                "debug": debug,
                "one_bar_evidence": one_bar_evidence,
            }
        )
        return found_num, score, debug, one_bar_evidence

    processor.classifier.predict = traced_predict
    processor._detect_number_with_evidence = traced_detect
    try:
        overrides = processor._process_page_with_support(
            page_data=page_data,
            support=support,
            image=image,
            page_num=page_num,
            image_width=width,
            image_height=height,
            debug_img=None,
        )
    finally:
        processor.classifier.predict = original_predict
        processor._detect_number_with_evidence = original_detect
    return overrides, traces, predict_calls


def _counterfactual_probe(
    *,
    processor: Any,
    recorder: _RecordingRapidOCR,
    image: Any,
    system: Mapping[str, Any],
    measure: Mapping[str, Any],
    primary_prob: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Probe another geometry using the production replay's primary CNN probability."""

    height, width = image.shape[:2]
    x1, y1, x2, y2 = measure["bbox"]
    recorder.begin_view()
    found_num, score, debug, one_bar_evidence = processor._detect_number_with_evidence(
        image, system, x1, y1, x2, y2, primary_prob, width, height
    )
    valid, status, vetoed = processor._valid_status(
        found_num, primary_prob, score, one_bar_evidence
    )
    return (
        {
            "measure_bbox": measure["bbox"],
            "staff_bboxes": [staff["bbox"] for staff in system.get("staves", [])],
            "shared_primary_prob": primary_prob,
            "selected_found_num": found_num,
            "selected_score": score,
            "debug_candidate": debug,
            "ocr_variant": _variant_from_debug(debug),
            "one_bar_evidence": one_bar_evidence,
            "valid_positive": valid,
            "status_label": status,
            "vetoed": vetoed,
        },
        deepcopy(recorder.current_records),
    )


def run(output_root: Path = OUTPUT_ROOT) -> Path:
    import cv2
    import torch

    from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import (
        collect_rapidocr_providers,
        create_mmr_rapidocr,
        providers_include_cuda,
    )
    from tools.issue264.run_phase_c_mmr_regression import build_page_specs

    started = time.perf_counter()
    page_inputs = _legacy_page_inputs()
    specs = {spec.page_id: spec for spec in build_page_specs()}
    current_by_page = {
        str(page["page_id"]): _index(
            _load_json(REUSE_ROOT / "intermediate" / str(page["page_id"]) / "overrides_mmr.json")
        )
        for page in page_inputs
    }
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for this positive-key MMR audit")
    classifier = MMRClassifier(MODEL_PATH, device)
    provider = create_mmr_rapidocr("cuda")
    recorder = _RecordingRapidOCR(provider)
    processor = MMRProcessor(
        MODEL_PATH, device, classifier=classifier, ocr_engine=MMROCREngine(ocr_engine=recorder)
    )

    audits: list[dict[str, Any]] = []
    mismatch_count = 0
    classifier_predict_calls = 0
    for page in page_inputs:
        page_id = str(page["page_id"])
        page_keys = sorted(current_by_page[page_id])
        if not page_keys:
            continue
        image = cv2.imread(str(specs[page_id].image))
        if image is None:
            raise RuntimeError(f"Could not read image: {specs[page_id].image}")
        support = _load_json(REUSE_ROOT / "intermediate" / page_id / "mmr_support.json")
        page_data = _load_json(ACCEPTED_ROOT / "intermediate" / page_id / "numbering_base.json")
        print(f"Replaying production positives: {page_id} ({len(page_keys)})", flush=True)
        for key in page_keys:
            _page, sys_idx, measure_idx = key
            sliced_page, sliced_support = slice_one_measure(
                page_data, support, sys_idx, measure_idx
            )
            existing = current_by_page[page_id][key]
            overrides, trace, predict_count = _production_exact_replay(
                processor=processor,
                recorder=recorder,
                image=image,
                page_data=sliced_page,
                support=sliced_support,
                page_num=int(existing["page"]) + 1,
            )
            classifier_predict_calls += predict_count
            reproduced = len(overrides) == 1 and _skip(overrides[0]) == _skip(existing)
            mismatch_count += int(not reproduced)
            audits.append(
                {
                    "page_id": page_id,
                    "key": list(key),
                    "existing_override": existing,
                    "production_exact_result": overrides,
                    "reproduced": reproduced,
                    "classifier_predict_calls": predict_count,
                    "production_path_trace": trace,
                }
            )

    report = {
        "schema_version": "issue274.positive_geometry_audit.v2",
        "status": "completed" if mismatch_count == 0 else "stopped_production_exact_mismatch",
        "evaluation_contract": {
            "production_source_modified": False,
            "full68_mmr_scan": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "numbering_reexecuted": False,
        },
        "runtime": {
            "elapsed_sec": time.perf_counter() - started,
            "classifier_initialization_count": 1,
            "rapidocr_initialization_count": 1,
            "classifier_predict_calls": classifier_predict_calls,
            "ocr_calls": recorder.calls,
        },
        "production_exact_reproducibility": {
            "evaluated": len(audits),
            "reproduced": len(audits) - mismatch_count,
            "mismatch_count": mismatch_count,
            "mismatches": [audit for audit in audits if not audit["reproduced"]],
        },
        "production_path_traces": audits,
        "rapidocr": {
            "providers": collect_rapidocr_providers(provider),
            "cuda_confirmed": providers_include_cuda(collect_rapidocr_providers(provider)),
        },
        "policy_projection_executed": False,
    }
    if mismatch_count == 0:
        counterfactuals = []
        extra_ocr_calls_before = recorder.calls
        for audit in audits:
            page_id = audit["page_id"]
            _page, sys_idx, measure_idx = audit["key"]
            image = cv2.imread(str(specs[page_id].image))
            support = _load_json(REUSE_ROOT / "intermediate" / page_id / "mmr_support.json")
            primary_trace = next(
                trace for trace in audit["production_path_trace"] if trace["view"] == "primary"
            )
            primary_prob = primary_trace["passed_prob"]
            views = support["views"]
            primary_measure = views["primary"]["pages"][0]["systems"][sys_idx]["measures"][
                measure_idx
            ]
            fallback_system = views["fallback"]["pages"][0]["systems"][sys_idx]
            fallback_measure = fallback_system["measures"][measure_idx]
            fallback, fallback_raw = _counterfactual_probe(
                processor=processor,
                recorder=recorder,
                image=image,
                system=fallback_system,
                measure=fallback_measure,
                primary_prob=primary_prob,
            )
            alternate = None
            alternate_raw = None
            alternate_system = views["implicit_start_alternate"]["pages"][0]["systems"][sys_idx]
            alternate_measure = alternate_system["measures"][measure_idx]
            if _view_differs(primary_measure, alternate_measure):
                alternate, alternate_raw = _counterfactual_probe(
                    processor=processor,
                    recorder=recorder,
                    image=image,
                    system=alternate_system,
                    measure=alternate_measure,
                    primary_prob=primary_prob,
                )
            primary_found = primary_trace["found_num"]
            raw = {}
            if fallback["selected_found_num"] != primary_found:
                raw["fallback"] = fallback_raw
            if alternate is not None and alternate["selected_found_num"] != primary_found:
                raw["implicit_start_alternate"] = alternate_raw
            counterfactuals.append(
                {
                    "page_id": page_id,
                    "key": audit["key"],
                    "primary_found_num": primary_found,
                    "fallback": fallback,
                    "implicit_start_alternate": alternate,
                    "raw_ocr_for_disagreement": raw,
                }
            )
        report["counterfactual_views"] = {
            "contract": "Counterfactual OCR uses the production replay primary CNN probability; no per-view CNN inference occurs.",
            "items": counterfactuals,
            "extra_ocr_calls": recorder.calls - extra_ocr_calls_before,
        }
    output_path = output_root / "issue274_positive_geometry_audit.json"
    _write_json(output_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "reproducibility": report["production_exact_reproducibility"],
                "runtime": report["runtime"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"report: {output_path}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    run(args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
