#!/usr/bin/env python3
"""Focused/risk probe for the next Issue #277 candidate OCR policy.

Experiment-only. Reuses retained Issue #294 candidate-native B geometry and reruns
MMR only. Expected fixture values are used for scoring after inference, never for
selection.

Candidate policy under test:
* preserve current low-CNN / one-bar J2 behavior;
* when high-CNN baseline OCR returns no number, retry one deterministic symmetric
  inward x trim (0.25% of measure width) and accept only a positive OCR candidate;
* when high-score baseline OCR originated from an unmasked fallback, retry one
  shifted staff-relative no_dilate view using a scale-relative hbar mask calibrated
  to the legacy 160 px geometry, and use that positive targeted result;
* otherwise preserve the current targeted-v2/J2 policy.

This is not a production change.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import cv2
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

import probe_calibrated_targeted_retry as calibrated_probe
import probe_native_geometry_robustness as base

INSET_FRACTION = base.MICRO_FRACTION
TARGETS = base.TARGETS


class CandidatePolicyProcessor(MMRProcessor):
    def __init__(
        self,
        model_path: Path,
        device: torch.device,
        *,
        classifier: MMRClassifier,
        ocr_engine: MMROCREngine,
        calibrated_processor: MMRProcessor,
        counter: base.CountingOCR,
    ) -> None:
        super().__init__(
            model_path,
            device,
            classifier=classifier,
            ocr_engine=ocr_engine,
        )
        self.calibrated_processor = calibrated_processor
        self.counter = counter
        self.policy_stats = {
            "inset_triggered": 0,
            "inset_selected": 0,
            "unmasked_fallback_triggered": 0,
            "calibrated_no_dilate_selected": 0,
        }

    @staticmethod
    def _symmetric_inset_bbox(bbox: list[int]) -> list[int]:
        x1, y1, x2, y2 = (int(value) for value in bbox)
        width = x2 - x1
        if width <= 2:
            return [x1, y1, x2, y2]
        dx = min(
            max(1, int(round(width * INSET_FRACTION))),
            max(1, (width - 1) // 2),
        )
        if x1 + dx >= x2 - dx:
            return [x1, y1, x2, y2]
        return [x1 + dx, y1, x2 - dx, y2]

    def _calibrated_shifted_no_dilate(
        self,
        image: Any,
        system: Mapping[str, Any],
        measure_bbox: list[int],
    ) -> tuple[Optional[int], float]:
        shifted_bbox = self._targeted_shift_x1(measure_bbox)
        values = []
        for stave in system.get("staves", []):
            item = calibrated_probe._run_calibrated_shifted_staff(
                self.calibrated_processor,
                self.counter,
                image,
                shifted_bbox,
                [int(value) for value in stave["bbox"]],
                "no_dilate",
            )
            result = item["result"]
            values.append((result["number"], result["score"]))
        return self._aggregate_targeted_staff_results(values)

    def _detect_number_with_evidence(
        self,
        image: Any,
        system: Dict,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        prob: float,
        w_img: int,
        h_img: int,
    ):
        baseline = self._detect_number_with_evidence_once(
            image, system, x1, y1, x2, y2, prob, w_img, h_img
        )
        found, score, debug, evidence = baseline

        # Preserve the current validated low-CNN and one-bar contracts exactly.
        if prob <= self.threshold or (
            self.threshold < prob < self.ONE_BAR_VETO_PROB_MAX
            and evidence >= self.ONE_BAR_VETO_MIN_EVIDENCE
        ):
            return self._detect_number_with_evidence_j2(
                image, system, x1, y1, x2, y2, prob, w_img, h_img, baseline
            )

        measure_bbox = [int(x1), int(y1), int(x2), int(y2)]

        # Candidate-native no-number rescue: one deterministic relative inset.
        if found is None:
            inset_bbox = self._symmetric_inset_bbox(measure_bbox)
            if inset_bbox != measure_bbox:
                self.policy_stats["inset_triggered"] += 1
                inset = MMRProcessor._detect_number_with_evidence(
                    self,
                    image,
                    system,
                    *inset_bbox,
                    prob,
                    w_img,
                    h_img,
                )
                inset_num, inset_score, inset_debug, inset_evidence = inset
                if self._targeted_retry_candidate_acceptable(inset_num, inset_score):
                    self.policy_stats["inset_selected"] += 1
                    return (
                        inset_num,
                        inset_score,
                        f"{inset_debug},issue277_candidate_native_symmetric_inset",
                        inset_evidence,
                    )

        # High-score false positives are not retried generally. Limit this to the
        # empirically suspicious unmasked-fallback OCR path.
        if found is not None and score > self.JITTER_SCORE_TRIGGER:
            if "unmasked_fallback" in str(debug):
                self.policy_stats["unmasked_fallback_triggered"] += 1
                retry_num, retry_score = self._calibrated_shifted_no_dilate(
                    image, system, measure_bbox
                )
                if self._targeted_retry_candidate_acceptable(retry_num, retry_score):
                    self.policy_stats["calibrated_no_dilate_selected"] += 1
                    return (
                        retry_num,
                        retry_score,
                        "issue277_calibrated_shifted_no_dilate_unmasked_fallback_retry",
                        evidence,
                    )
            return baseline

        # Preserve current targeted-v2 behavior for all remaining cases.
        staves = system.get("staves", [])
        full_span_values = [
            self._run_targeted_full_span_staff(
                image, measure_bbox, stave["bbox"], w_img, h_img
            )
            for stave in staves
        ]
        retry_num, retry_score = self._aggregate_targeted_staff_results(full_span_values)
        if self._targeted_retry_candidate_acceptable(retry_num, retry_score):
            return (
                retry_num,
                retry_score,
                "issue277_targeted_full_span_unmasked_heavy_dilate",
                evidence,
            )

        shifted_bbox = self._targeted_shift_x1(measure_bbox)
        shifted_values = []
        if shifted_bbox[0] != measure_bbox[0]:
            shifted_values = [
                self._run_targeted_shifted_staff(
                    image, shifted_bbox, stave["bbox"], w_img, h_img
                )
                for stave in staves
            ]
        retry_num, retry_score = self._aggregate_targeted_staff_results(shifted_values)
        if self._targeted_retry_candidate_acceptable(retry_num, retry_score):
            return (
                retry_num,
                retry_score,
                "issue277_targeted_scale_relative_x1_masked_no_dilate",
                evidence,
            )

        if found is None:
            return baseline

        return self._detect_number_with_evidence_j2(
            image, system, x1, y1, x2, y2, prob, w_img, h_img, baseline
        )


def _candidate_variant(focused: Mapping[str, Any]) -> Mapping[str, Any]:
    variants = focused.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("Focused artifact lacks variants")
    candidate = variants.get("B_b377_mapping_guarded")
    if isinstance(candidate, Mapping):
        return candidate
    matches = [
        value
        for key, value in variants.items()
        if str(key).startswith("B_") and isinstance(value, Mapping)
    ]
    if len(matches) != 1:
        raise ValueError("Unable to identify maintained-B focused variant")
    return matches[0]


def _expected_by_page(candidate: Mapping[str, Any]) -> dict[str, dict[tuple[int, int], int]]:
    result: dict[str, dict[tuple[int, int], int]] = {}
    for page in candidate.get("pages", []):
        page_id = str(page["page_id"])
        expected: dict[tuple[int, int], int] = {}
        for item in page.get("expected", []):
            expected[(int(item["system"]), int(item["measure"]))] = int(item["skip"])
        result[page_id] = expected
    return result


def _detected_map(overrides: list[Mapping[str, Any]]) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    for item in overrides:
        key = (int(item["system"]), int(item["measure"]))
        if key in result:
            raise RuntimeError(f"Duplicate MMR override: {key}")
        result[key] = int(item["skip"])
    return result


def _score(
    expected: Mapping[tuple[int, int], int],
    detected: Mapping[tuple[int, int], int],
) -> dict[str, int]:
    tp = fn = mismatch = fp = 0
    for key, expected_skip in expected.items():
        if key not in detected:
            fn += 1
        elif int(detected[key]) == int(expected_skip):
            tp += 1
        else:
            mismatch += 1
    for key in detected:
        if key not in expected:
            fp += 1
    return {
        "expected": len(expected),
        "detected": len(detected),
        "tp": tp,
        "fn": fn,
        "mismatch": mismatch,
        "fp": fp,
    }


def _add_score(total: dict[str, int], value: Mapping[str, int]) -> None:
    for key in total:
        total[key] += int(value[key])


def _error_count(score: Mapping[str, int]) -> int:
    return int(score["fn"]) + int(score["mismatch"]) + int(score["fp"])


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
    focused = base._load_json(focused_path)
    candidate = _candidate_variant(focused)
    expected_pages = _expected_by_page(candidate)
    matrix_pages = base._load_matrix_pages(manifest, issue294_root)
    specs = {str(spec.page_id): spec for spec in base.build_page_specs()}

    raw_ocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(raw_ocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDAExecutionProvider not confirmed: {providers}")

    classifier = MMRClassifier(args.model, torch.device("cuda"))

    current_counter = base.CountingOCR(raw_ocr)
    current = MMRProcessor(
        args.model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=current_counter),
    )

    candidate_counter = base.CountingOCR(raw_ocr)
    calibrated_processor = MMRProcessor(
        args.model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=calibrated_probe.CalibratedScaleRelativeOCREngine(
            ocr_engine=candidate_counter
        ),
    )
    proposed = CandidatePolicyProcessor(
        args.model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=candidate_counter),
        calibrated_processor=calibrated_processor,
        counter=candidate_counter,
    )

    totals = {
        "current": {key: 0 for key in ("expected", "detected", "tp", "fn", "mismatch", "fp")},
        "candidate": {key: 0 for key in ("expected", "detected", "tp", "fn", "mismatch", "fp")},
    }
    pages: dict[str, Any] = {}

    for page_id in sorted(expected_pages):
        spec = specs.get(page_id)
        if spec is None:
            raise KeyError(page_id)
        matrix_page = matrix_pages.get((str(spec.score), str(spec.page_name)))
        if matrix_page is None:
            raise KeyError((spec.score, spec.page_name))
        page_data, image_path, support, mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )

        current_before = current_counter.calls
        current_started = time.perf_counter()
        current_overrides = current.process_pages(
            [page_data], [image_path], support_data=[support]
        )[0]["measure_overrides"]
        current_seconds = time.perf_counter() - current_started
        current_calls = current_counter.calls - current_before

        candidate_before = candidate_counter.calls
        candidate_started = time.perf_counter()
        candidate_overrides = proposed.process_pages(
            [page_data], [image_path], support_data=[support]
        )[0]["measure_overrides"]
        candidate_seconds = time.perf_counter() - candidate_started
        candidate_calls = candidate_counter.calls - candidate_before

        expected = expected_pages[page_id]
        current_detected = _detected_map(current_overrides)
        candidate_detected = _detected_map(candidate_overrides)
        current_score = _score(expected, current_detected)
        candidate_score = _score(expected, candidate_detected)
        _add_score(totals["current"], current_score)
        _add_score(totals["candidate"], candidate_score)

        changed = []
        all_keys = sorted(set(current_detected) | set(candidate_detected))
        for key in all_keys:
            if current_detected.get(key) != candidate_detected.get(key):
                changed.append(
                    {
                        "system": key[0],
                        "measure": key[1],
                        "expected_skip": expected.get(key),
                        "current_skip": current_detected.get(key),
                        "candidate_skip": candidate_detected.get(key),
                    }
                )

        pages[page_id] = {
            "score": str(spec.score),
            "page_name": str(spec.page_name),
            "image": str(image_path),
            "mapping_mode": mapping_mode,
            "expected_count": len(expected),
            "current": {
                "score": current_score,
                "ocr_calls": current_calls,
                "seconds": current_seconds,
                "overrides": current_overrides,
            },
            "candidate": {
                "score": candidate_score,
                "ocr_calls": candidate_calls,
                "seconds": candidate_seconds,
                "overrides": candidate_overrides,
            },
            "changed": changed,
            "no_page_regression": _error_count(candidate_score) <= _error_count(current_score),
        }

    target_results = []
    for page_id, system_idx, measure_idx in TARGETS:
        page = pages.get(page_id)
        expected_skip = expected_pages.get(page_id, {}).get((system_idx, measure_idx))
        current_map = _detected_map(page["current"]["overrides"]) if page else {}
        candidate_map = _detected_map(page["candidate"]["overrides"]) if page else {}
        target_results.append(
            {
                "key": f"{page_id} s{system_idx} m{measure_idx}",
                "expected_skip": expected_skip,
                "current_skip": current_map.get((system_idx, measure_idx)),
                "candidate_skip": candidate_map.get((system_idx, measure_idx)),
                "candidate_matches_expected": (
                    expected_skip is not None
                    and candidate_map.get((system_idx, measure_idx)) == expected_skip
                ),
            }
        )

    no_page_regressions = all(page["no_page_regression"] for page in pages.values())
    targets_pass = all(item["candidate_matches_expected"] for item in target_results)
    aggregate_no_worse = _error_count(totals["candidate"]) <= _error_count(totals["current"])
    no_new_fp = totals["candidate"]["fp"] <= totals["current"]["fp"]

    return {
        "schema_version": "issue277.focused_candidate_policy_probe.v1",
        "status": "completed",
        "diagnostic_only": True,
        "retained_issue294": {
            "root": str(issue294_root),
            "manifest": str(manifest_path),
            "focused_artifact": str(focused_path),
        },
        "model": str(args.model.resolve()),
        "rapidocr_providers": providers,
        "policy": {
            "no_number_retry": "single symmetric inward x trim at 0.25% measure width",
            "high_score_retry_trigger": "baseline debug contains unmasked_fallback",
            "high_score_retry": "calibrated shifted staff-relative no_dilate",
            "calibrated_mask_ratios": calibrated_probe.CALIBRATED_MASK_RATIOS,
            "threshold_changes": False,
            "expected_values_used_for_selection": False,
            "historical_a_geometry_used": False,
            "frozen_a_geometry_used": False,
        },
        "policy_stats": proposed.policy_stats,
        "focused_page_count": len(pages),
        "totals": totals,
        "current_ocr_calls": current_counter.calls,
        "candidate_ocr_calls": candidate_counter.calls,
        "ocr_call_delta": candidate_counter.calls - current_counter.calls,
        "targets": target_results,
        "gates": {
            "targets_pass": targets_pass,
            "no_page_regressions": no_page_regressions,
            "aggregate_no_worse": aggregate_no_worse,
            "no_new_fp": no_new_fp,
            "all_pass": targets_pass and no_page_regressions and aggregate_no_worse and no_new_fp,
        },
        "runtime_seconds": time.perf_counter() - started,
        "pages": pages,
    }


def _summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    changed = []
    for page_id, page in payload["pages"].items():
        for item in page["changed"]:
            changed.append({"page_id": page_id, **item})
    return {
        "status": payload["status"],
        "output": str(output),
        "focused_page_count": payload["focused_page_count"],
        "totals": payload["totals"],
        "policy_stats": payload["policy_stats"],
        "current_ocr_calls": payload["current_ocr_calls"],
        "candidate_ocr_calls": payload["candidate_ocr_calls"],
        "ocr_call_delta": payload["ocr_call_delta"],
        "targets": payload["targets"],
        "gates": payload["gates"],
        "changed_count": len(changed),
        "changed": changed,
        "runtime_seconds": payload["runtime_seconds"],
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
        args.output = PROJECT_ROOT / "logs/issue277" / f"focused_candidate_policy_{stamp}.json"
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
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(json.dumps(_summary(payload, args.output), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
