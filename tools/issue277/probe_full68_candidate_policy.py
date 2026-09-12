#!/usr/bin/env python3
"""Full68 retained-artifact gate for the Issue #277 candidate OCR policy.

Experiment-only. Reuses retained Issue #294 maintained-B candidate-native geometry,
reruns current MMR and the focused-gate candidate policy on all 68 evaluation pages,
and scores both against the accepted Issue #264 physical MMR GT spatially rebased
onto the candidate geometry.

Expected values are evaluation-only and never participate in OCR selection.
Historical/frozen A geometry is never used as a runtime signal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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
from tools.issue264.phase_c_fixture_rebase import MeasureRef, map_measure_bbox

import probe_calibrated_targeted_retry as calibrated_probe
import probe_focused_candidate_policy as focused_probe
import probe_native_geometry_robustness as base

ACCEPTED_SCHEMA = "issue264.phase_c_mmr_geometry_rebased_score.v2"
ACCEPTED_SUMMARY = {
    "expected": 177,
    "pages": 68,
    "zero_expected_pages": 16,
}
PAGE_033_ONE_BAR = (0, 0)
TARGETS = base.TARGETS


def _accepted_pages(path: Path) -> tuple[dict[str, Mapping[str, Any]], dict[str, Any]]:
    payload = base._load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError("Malformed accepted Issue #264 report")
    if payload.get("schema") != ACCEPTED_SCHEMA:
        raise ValueError(f"Unexpected accepted report schema: {payload.get('schema')}")
    if payload.get("status") != "passed":
        raise ValueError("Accepted Issue #264 report is not passed")
    summary = payload.get("geometry_rebased_summary")
    pages = payload.get("pages")
    gates = payload.get("gates")
    if not isinstance(summary, Mapping):
        raise ValueError("Accepted report lacks geometry_rebased_summary")
    if not isinstance(pages, list) or len(pages) != 68:
        raise ValueError("Accepted report must contain 68 pages")
    if not isinstance(gates, Mapping) or not all(bool(value) for value in gates.values()):
        raise ValueError("Accepted report has a failed gate")
    for key, expected in ACCEPTED_SUMMARY.items():
        if int(summary.get(key, -1)) != expected:
            raise ValueError(
                f"Accepted report fingerprint mismatch for {key}: "
                f"expected={expected} actual={summary.get(key)}"
            )
    by_id: dict[str, Mapping[str, Any]] = {}
    for page in pages:
        if not isinstance(page, Mapping):
            raise ValueError("Malformed accepted report page")
        page_id = str(page.get("page_id", ""))
        if not page_id or page_id in by_id:
            raise ValueError(f"Duplicate/missing accepted page_id: {page_id!r}")
        by_id[page_id] = page
    expected_ids = {f"page_{index:03d}" for index in range(1, 69)}
    if set(by_id) != expected_ids:
        raise ValueError("Accepted report page IDs are not page_001..page_068")
    return by_id, {
        "path": str(path),
        "schema": payload.get("schema"),
        "status": payload.get("status"),
        "source_git_head": payload.get("source_git_head"),
        "summary": {key: int(summary[key]) for key in ACCEPTED_SUMMARY},
    }


def _rebase_expected(
    accepted_page: Mapping[str, Any],
    candidate_numbering: Mapping[str, Any],
    *,
    global_page_index: int,
) -> tuple[dict[tuple[int, int], int], list[dict[str, Any]]]:
    page_rebase = accepted_page.get("fixture_rebase")
    if not isinstance(page_rebase, Mapping):
        raise ValueError("Accepted page lacks fixture_rebase")
    anchors = page_rebase.get("mappings")
    if not isinstance(anchors, list):
        raise ValueError("Accepted page lacks fixture mappings")

    expected: dict[tuple[int, int], int] = {}
    mappings: list[dict[str, Any]] = []
    for anchor in anchors:
        if not isinstance(anchor, Mapping):
            raise ValueError("Malformed accepted fixture mapping")
        accepted_key = anchor.get("current_key")
        historical_key = anchor.get("historical_key")
        accepted_bbox = anchor.get("current_bbox")
        if not isinstance(accepted_key, list) or len(accepted_key) != 3:
            raise ValueError(f"Malformed accepted current_key: {accepted_key!r}")
        if not isinstance(historical_key, list) or len(historical_key) != 3:
            raise ValueError(f"Malformed accepted historical_key: {historical_key!r}")
        if not isinstance(accepted_bbox, list) or len(accepted_bbox) != 4:
            raise ValueError(f"Malformed accepted current_bbox: {accepted_bbox!r}")
        if int(accepted_key[0]) != global_page_index:
            raise ValueError(
                f"Accepted page index mismatch: expected={global_page_index} "
                f"actual={accepted_key[0]}"
            )

        source = MeasureRef(
            system=int(accepted_key[1]),
            measure=int(accepted_key[2]),
            bbox=tuple(float(value) for value in accepted_bbox),
        )
        candidate, detail = map_measure_bbox(source, candidate_numbering)
        key = (int(candidate.system), int(candidate.measure))
        skip = int(anchor.get("skip") or 0)
        existing = expected.get(key)
        if existing is not None and existing != skip:
            raise ValueError(
                f"Conflicting accepted anchors map to candidate key {key}: "
                f"{existing} vs {skip}"
            )
        expected[key] = skip
        mappings.append(
            {
                "historical_key": [int(value) for value in historical_key],
                "accepted_key": [int(value) for value in accepted_key],
                "candidate_key": [global_page_index, key[0], key[1]],
                "skip": skip,
                "method": str(detail["method"]),
                "overlap_score": float(detail["overlap_score"]),
            }
        )
    return expected, mappings


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


def _errors(value: Mapping[str, int]) -> int:
    return int(value["fn"]) + int(value["mismatch"]) + int(value["fp"])


def _add(total: dict[str, int], value: Mapping[str, int]) -> None:
    for key in total:
        total[key] += int(value[key])


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / base.DEFAULT_MANIFEST_REL).resolve()
    )
    accepted_path = args.accepted_rebase_report.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not accepted_path.is_file():
        raise FileNotFoundError(accepted_path)
    if not args.model.is_file():
        raise FileNotFoundError(args.model)

    started = time.perf_counter()
    manifest = base._load_json(manifest_path)
    matrix_pages = base._load_matrix_pages(manifest, issue294_root)
    accepted_pages, accepted_provenance = _accepted_pages(accepted_path)
    specs = base.build_page_specs()
    if len(specs) != 68:
        raise RuntimeError(f"Expected 68 page specs, got {len(specs)}")

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
    proposed = focused_probe.CandidatePolicyProcessor(
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
    zero_expected_pages = 0
    current_zero_expected_detections = 0
    candidate_zero_expected_detections = 0

    for spec in specs:
        page_id = str(spec.page_id)
        matrix_page = matrix_pages.get((str(spec.score), str(spec.page_name)))
        if matrix_page is None:
            raise KeyError(f"Matrix lacks {page_id}: {(spec.score, spec.page_name)}")
        page_data, image_path, support, mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )
        expected, expected_mappings = _rebase_expected(
            accepted_pages[page_id],
            page_data,
            global_page_index=int(spec.global_index),
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

        current_detected = _detected_map(current_overrides)
        candidate_detected = _detected_map(candidate_overrides)
        current_score = _score(expected, current_detected)
        candidate_score = _score(expected, candidate_detected)
        _add(totals["current"], current_score)
        _add(totals["candidate"], candidate_score)

        if not expected:
            zero_expected_pages += 1
            current_zero_expected_detections += len(current_detected)
            candidate_zero_expected_detections += len(candidate_detected)

        changed = []
        for key in sorted(set(current_detected) | set(candidate_detected)):
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
            "mapping_mode": mapping_mode,
            "expected_mappings": expected_mappings,
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
            "no_page_regression": bool(
                _errors(candidate_score) <= _errors(current_score)
                and int(candidate_score["fp"]) <= int(current_score["fp"])
                and int(candidate_score["tp"]) >= int(current_score["tp"])
            ),
        }

    target_results = []
    for page_id, system_idx, measure_idx in TARGETS:
        page = pages[page_id]
        current_detected = _detected_map(page["current"]["overrides"])
        candidate_detected = _detected_map(page["candidate"]["overrides"])
        expected, _ = _rebase_expected(
            accepted_pages[page_id],
            page_data=pages[page_id] if False else {},
            global_page_index=0,
        ) if False else ({}, [])
        # Read expected directly from the stored mapping list to avoid recomputing geometry.
        expected_skip = None
        for item in page["expected_mappings"]:
            key = item["candidate_key"]
            if int(key[1]) == system_idx and int(key[2]) == measure_idx:
                expected_skip = int(item["skip"])
                break
        target_results.append(
            {
                "key": f"{page_id} s{system_idx} m{measure_idx}",
                "expected_skip": expected_skip,
                "current_skip": current_detected.get((system_idx, measure_idx)),
                "candidate_skip": candidate_detected.get((system_idx, measure_idx)),
                "candidate_matches_expected": bool(
                    expected_skip is not None
                    and candidate_detected.get((system_idx, measure_idx)) == expected_skip
                ),
            }
        )

    page_033 = pages["page_033"]
    page_033_candidate = _detected_map(page_033["candidate"]["overrides"])
    page_042 = pages["page_042"]
    page_042_candidate = _detected_map(page_042["candidate"]["overrides"])
    page_042_expected = {
        (int(item["candidate_key"][1]), int(item["candidate_key"][2])): int(item["skip"])
        for item in page_042["expected_mappings"]
    }

    no_page_regressions = all(bool(page["no_page_regression"]) for page in pages.values())
    gates = {
        "expected_177": int(totals["candidate"]["expected"]) == 177,
        "zero_expected_pages_16": zero_expected_pages == 16,
        "targets_pass": all(item["candidate_matches_expected"] for item in target_results),
        "no_page_regressions": no_page_regressions,
        "aggregate_no_worse": bool(
            _errors(totals["candidate"]) <= _errors(totals["current"])
            and int(totals["candidate"]["tp"]) >= int(totals["current"]["tp"])
        ),
        "no_new_fp": int(totals["candidate"]["fp"]) == 0,
        "zero_expected_detections_zero": candidate_zero_expected_detections == 0,
        "page_033_one_bar_veto": PAGE_033_ONE_BAR not in page_033_candidate,
        "page_042_exact_expected": bool(
            page_042_candidate == page_042_expected and len(page_042_expected) == 5
        ),
    }
    gates["all_pass"] = all(gates.values())

    changed = []
    for page_id, page in pages.items():
        for item in page["changed"]:
            changed.append({"page_id": page_id, **item})

    return {
        "schema_version": "issue277.full68_candidate_policy_probe.v1",
        "status": "completed",
        "diagnostic_only": True,
        "retained_issue294": {
            "root": str(issue294_root),
            "manifest": str(manifest_path),
        },
        "accepted_rebase": accepted_provenance,
        "model": str(args.model.resolve()),
        "rapidocr_providers": providers,
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
        "page_count": len(pages),
        "totals": totals,
        "policy_stats": proposed.policy_stats,
        "current_ocr_calls": current_counter.calls,
        "candidate_ocr_calls": candidate_counter.calls,
        "ocr_call_delta": candidate_counter.calls - current_counter.calls,
        "zero_expected": {
            "pages": zero_expected_pages,
            "current_detections": current_zero_expected_detections,
            "candidate_detections": candidate_zero_expected_detections,
        },
        "targets": target_results,
        "gates": gates,
        "changed_count": len(changed),
        "changed": changed,
        "runtime_seconds": time.perf_counter() - started,
        "pages": pages,
    }


def _summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    regressions = [
        page_id
        for page_id, page in payload["pages"].items()
        if not bool(page["no_page_regression"])
    ]
    return {
        "status": payload["status"],
        "output": str(output),
        "page_count": payload["page_count"],
        "totals": payload["totals"],
        "policy_stats": payload["policy_stats"],
        "current_ocr_calls": payload["current_ocr_calls"],
        "candidate_ocr_calls": payload["candidate_ocr_calls"],
        "ocr_call_delta": payload["ocr_call_delta"],
        "zero_expected": payload["zero_expected"],
        "targets": payload["targets"],
        "gates": payload["gates"],
        "regression_pages": regressions,
        "changed_count": payload["changed_count"],
        "changed": payload["changed"],
        "runtime_seconds": payload["runtime_seconds"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue294-root", type=Path, default=base.DEFAULT_ISSUE294_ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=base.DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        args.output = PROJECT_ROOT / "logs/issue277" / f"full68_candidate_policy_{stamp}.json"
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
    return 0 if bool(payload["gates"]["all_pass"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
