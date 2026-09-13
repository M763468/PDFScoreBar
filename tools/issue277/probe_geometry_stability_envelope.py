#!/usr/bin/env python3
"""Full68 geometry-stability envelope for the Issue #277 candidate OCR policy.

Experiment-only. Reuses retained Issue #294 maintained-B candidate-native geometry
and the already validated Issue #277 candidate policy. It perturbs only the MMR
support geometry seen by the OCR/classifier layer; detector/HOMR/SR/OMR are not
rerun and expected fixtures are never used for selection.

The gate asks a stronger question than the ordinary full68 correctness gate:
within the observed <=4 px producer-drift envelope, does the final semantic MMR
override map remain exactly invariant?
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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
import probe_focused_candidate_policy as focused_probe
import probe_full68_candidate_policy as full_probe
import probe_native_geometry_robustness as base

DELTAS = (-4, -2, -1, 1, 2, 4)
TARGETS = base.TARGETS
PAGE_033_ONE_BAR = full_probe.PAGE_033_ONE_BAR


def _variant_specs() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = [{"name": "native", "family": "native", "delta": 0}]
    for family in ("measure_x1", "measure_x2", "measure_translate_x", "staff_translate_y"):
        for delta in DELTAS:
            suffix = f"p{delta}" if delta > 0 else f"m{abs(delta)}"
            variants.append(
                {
                    "name": f"{family}_{suffix}",
                    "family": family,
                    "delta": delta,
                }
            )
    return variants


def _translate_interval(start: int, end: int, delta: int, limit: int) -> tuple[int, int]:
    width = max(1, end - start)
    shifted_start = start + delta
    shifted_end = end + delta
    if shifted_start < 0:
        shifted_end -= shifted_start
        shifted_start = 0
    if shifted_end > limit:
        overshoot = shifted_end - limit
        shifted_start -= overshoot
        shifted_end = limit
    shifted_start = max(0, shifted_start)
    shifted_end = min(limit, shifted_end)
    if shifted_end - shifted_start < width:
        shifted_start = max(0, min(limit - width, shifted_start))
        shifted_end = min(limit, shifted_start + width)
    return int(shifted_start), int(shifted_end)


def _perturb_measure_bbox(
    bbox: list[int], family: str, delta: int, image_width: int
) -> list[int]:
    x1, y1, x2, y2 = (int(value) for value in bbox)
    if family == "measure_x1":
        x1 = max(0, min(x2 - 2, x1 + delta))
    elif family == "measure_x2":
        x2 = min(image_width, max(x1 + 2, x2 + delta))
    elif family == "measure_translate_x":
        x1, x2 = _translate_interval(x1, x2, delta, image_width)
    return [x1, y1, x2, y2]


def _perturb_staff_bbox(
    bbox: list[int], family: str, delta: int, image_height: int
) -> list[int]:
    x1, y1, x2, y2 = (int(value) for value in bbox)
    if family == "staff_translate_y":
        y1, y2 = _translate_interval(y1, y2, delta, image_height)
    return [x1, y1, x2, y2]


def _perturb_support(
    support: Mapping[str, Any],
    variant: Mapping[str, Any],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    family = str(variant["family"])
    delta = int(variant["delta"])
    if family == "native":
        return deepcopy(dict(support))

    perturbed = deepcopy(dict(support))
    views = perturbed.get("views")
    if not isinstance(views, dict):
        raise ValueError("MMR support lacks views")

    for view in views.values():
        if not isinstance(view, dict):
            raise ValueError("Malformed MMR support view")
        pages = view.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("Malformed MMR support page")
        systems = pages[0].get("systems", [])
        for system in systems:
            if family.startswith("measure_"):
                for measure in system.get("measures", []):
                    measure["bbox"] = _perturb_measure_bbox(
                        measure["bbox"], family, delta, image_width
                    )
            if family == "staff_translate_y":
                for stave in system.get("staves", []):
                    stave["bbox"] = _perturb_staff_bbox(
                        stave["bbox"], family, delta, image_height
                    )
    return perturbed


def _semantic(overrides: list[Mapping[str, Any]]) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    for item in overrides:
        key = (int(item["system"]), int(item["measure"]))
        if key in result:
            raise RuntimeError(f"Duplicate MMR override: {key}")
        result[key] = int(item["skip"])
    return result


def _json_semantic(value: Mapping[tuple[int, int], int]) -> list[dict[str, int]]:
    return [
        {"system": system, "measure": measure, "skip": skip}
        for (system, measure), skip in sorted(value.items())
    ]


def _candidate_processor(
    model: Path,
    classifier: MMRClassifier,
    raw_ocr: Any,
) -> tuple[focused_probe.CandidatePolicyProcessor, base.CountingOCR]:
    counter = base.CountingOCR(raw_ocr)
    calibrated_processor = MMRProcessor(
        model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=calibrated_probe.CalibratedScaleRelativeOCREngine(
            ocr_engine=counter
        ),
    )
    processor = focused_probe.CandidatePolicyProcessor(
        model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=counter),
        calibrated_processor=calibrated_processor,
        counter=counter,
    )
    return processor, counter


def _reference_candidate_pages(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = base._load_json(path)
    if payload.get("status") != "completed":
        raise ValueError("Reference full68 artifact is not completed")
    if not bool(payload.get("gates", {}).get("all_pass")):
        raise ValueError("Reference full68 artifact did not pass all gates")
    pages = payload.get("pages")
    if not isinstance(pages, dict) or len(pages) != 68:
        raise ValueError("Reference full68 artifact must contain 68 pages")
    return pages, payload


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / base.DEFAULT_MANIFEST_REL).resolve()
    )
    accepted_path = args.accepted_rebase_report.resolve()
    reference_path = args.reference_full68.resolve()
    for path in (manifest_path, accepted_path, reference_path, args.model.resolve()):
        if not path.is_file():
            raise FileNotFoundError(path)

    started = time.perf_counter()
    manifest = base._load_json(manifest_path)
    matrix_pages = base._load_matrix_pages(manifest, issue294_root)
    accepted_pages, accepted_provenance = full_probe._accepted_pages(accepted_path)
    reference_pages, reference_payload = _reference_candidate_pages(reference_path)
    specs = base.build_page_specs()
    if len(specs) != 68:
        raise RuntimeError(f"Expected 68 page specs, got {len(specs)}")

    raw_ocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(raw_ocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDAExecutionProvider not confirmed: {providers}")
    classifier = MMRClassifier(args.model, torch.device("cuda"))

    prepared: dict[str, dict[str, Any]] = {}
    for spec in specs:
        page_id = str(spec.page_id)
        matrix_page = matrix_pages.get((str(spec.score), str(spec.page_name)))
        if matrix_page is None:
            raise KeyError(f"Matrix lacks {page_id}: {(spec.score, spec.page_name)}")
        page_data, image_path, support, mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        expected, expected_mappings = full_probe._rebase_expected(
            accepted_pages[page_id],
            page_data,
            global_page_index=int(spec.global_index),
        )
        prepared[page_id] = {
            "spec": spec,
            "page_data": page_data,
            "image_path": image_path,
            "image_width": int(image.shape[1]),
            "image_height": int(image.shape[0]),
            "support": support,
            "mapping_mode": mapping_mode,
            "expected": expected,
            "expected_mappings": expected_mappings,
        }

    variants: dict[str, Any] = {}
    native_maps: dict[str, dict[tuple[int, int], int]] | None = None
    native_totals: dict[str, int] | None = None

    for variant in _variant_specs():
        variant_name = str(variant["name"])
        processor, counter = _candidate_processor(args.model, classifier, raw_ocr)
        totals = {
            key: 0
            for key in ("expected", "detected", "tp", "fn", "mismatch", "fp")
        }
        pages: dict[str, Any] = {}
        zero_expected_detections = 0
        semantic_changes: list[dict[str, Any]] = []
        variant_started = time.perf_counter()

        for page_id in sorted(prepared):
            item = prepared[page_id]
            support = _perturb_support(
                item["support"],
                variant,
                item["image_width"],
                item["image_height"],
            )
            before = counter.calls
            page_started = time.perf_counter()
            overrides = processor.process_pages(
                [item["page_data"]],
                [item["image_path"]],
                support_data=[support],
            )[0]["measure_overrides"]
            seconds = time.perf_counter() - page_started
            calls = counter.calls - before
            detected = _semantic(overrides)
            score = full_probe._score(item["expected"], detected)
            full_probe._add(totals, score)
            if not item["expected"]:
                zero_expected_detections += len(detected)

            reference = _semantic(reference_pages[page_id]["candidate"]["overrides"])
            if variant_name == "native":
                compare_map = reference
            else:
                if native_maps is None:
                    raise RuntimeError("Native variant must run first")
                compare_map = native_maps[page_id]

            changed = []
            for key in sorted(set(compare_map) | set(detected)):
                if compare_map.get(key) != detected.get(key):
                    change = {
                        "system": key[0],
                        "measure": key[1],
                        "expected_skip": item["expected"].get(key),
                        "reference_skip": compare_map.get(key),
                        "variant_skip": detected.get(key),
                    }
                    changed.append(change)
                    semantic_changes.append({"page_id": page_id, **change})

            pages[page_id] = {
                "score": score,
                "ocr_calls": calls,
                "seconds": seconds,
                "overrides": _json_semantic(detected),
                "semantic_exact": not changed,
                "changed": changed,
            }

        if variant_name == "native":
            native_maps = {
                page_id: _semantic(pages[page_id]["overrides"])
                for page_id in pages
            }
            native_totals = dict(totals)

        target_results = []
        for page_id, system_idx, measure_idx in TARGETS:
            detected = _semantic(pages[page_id]["overrides"])
            expected_skip = prepared[page_id]["expected"].get(
                (system_idx, measure_idx)
            )
            target_results.append(
                {
                    "key": f"{page_id} s{system_idx} m{measure_idx}",
                    "expected_skip": expected_skip,
                    "variant_skip": detected.get((system_idx, measure_idx)),
                    "matches_expected": bool(
                        expected_skip is not None
                        and detected.get((system_idx, measure_idx)) == expected_skip
                    ),
                }
            )

        page_033_detected = _semantic(pages["page_033"]["overrides"])
        page_042_detected = _semantic(pages["page_042"]["overrides"])
        page_042_expected = prepared["page_042"]["expected"]
        semantic_exact = not semantic_changes
        totals_exact = native_totals is None or totals == native_totals
        gates = {
            "semantic_exact": semantic_exact,
            "totals_exact": totals_exact,
            "targets_pass": all(item["matches_expected"] for item in target_results),
            "no_fp": int(totals["fp"]) == 0,
            "zero_expected_detections_zero": zero_expected_detections == 0,
            "page_033_one_bar_veto": PAGE_033_ONE_BAR not in page_033_detected,
            "page_042_exact_expected": bool(
                page_042_detected == page_042_expected and len(page_042_expected) == 5
            ),
        }
        if variant_name == "native":
            gates["reference_totals_exact"] = bool(
                totals == reference_payload["totals"]["candidate"]
            )
            gates["reference_semantic_exact"] = semantic_exact
        gates["all_pass"] = all(gates.values())

        variants[variant_name] = {
            "family": variant["family"],
            "delta": variant["delta"],
            "totals": totals,
            "ocr_calls": counter.calls,
            "runtime_seconds": time.perf_counter() - variant_started,
            "zero_expected_detections": zero_expected_detections,
            "targets": target_results,
            "gates": gates,
            "semantic_change_count": len(semantic_changes),
            "semantic_changes": semantic_changes,
            "pages": pages,
        }

        if variant_name == "native" and not gates["all_pass"]:
            break

    expected_variant_count = len(_variant_specs())
    all_expected_variants = len(variants) == expected_variant_count
    perturbation_variants = [
        value for name, value in variants.items() if name != "native"
    ]
    all_perturbations_pass = bool(
        all_expected_variants
        and perturbation_variants
        and all(bool(value["gates"]["all_pass"]) for value in perturbation_variants)
    )

    return {
        "schema_version": "issue277.geometry_stability_envelope.v1",
        "status": "completed",
        "diagnostic_only": True,
        "retained_issue294": {
            "root": str(issue294_root),
            "manifest": str(manifest_path),
        },
        "accepted_rebase": accepted_provenance,
        "reference_full68": str(reference_path),
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
            "metamorphic_only": True,
        },
        "stability_domain": {
            "absolute_pixel_deltas": list(DELTAS),
            "families": [
                "measure_x1",
                "measure_x2",
                "measure_translate_x",
                "staff_translate_y",
            ],
            "observed_issue294_max_bbox_delta_px": 4,
            "semantic_gate": "final override map must match native exactly on every page",
        },
        "variant_count_expected": expected_variant_count,
        "variant_count_completed": len(variants),
        "native_totals": native_totals,
        "all_perturbations_pass": all_perturbations_pass,
        "all_pass": bool(
            all_expected_variants
            and variants.get("native", {}).get("gates", {}).get("all_pass")
            and all_perturbations_pass
        ),
        "runtime_seconds": time.perf_counter() - started,
        "variants": variants,
    }


def _summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    failed = []
    changes = []
    for name, variant in payload["variants"].items():
        if not bool(variant["gates"]["all_pass"]):
            failed.append(name)
        if variant["semantic_change_count"]:
            changes.append(
                {
                    "variant": name,
                    "count": variant["semantic_change_count"],
                    "first_changes": variant["semantic_changes"][:12],
                }
            )
    return {
        "status": payload["status"],
        "output": str(output),
        "variant_count_expected": payload["variant_count_expected"],
        "variant_count_completed": payload["variant_count_completed"],
        "native_totals": payload["native_totals"],
        "all_perturbations_pass": payload["all_perturbations_pass"],
        "all_pass": payload["all_pass"],
        "failed_variants": failed,
        "semantic_changes": changes,
        "runtime_seconds": payload["runtime_seconds"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue294-root", type=Path, default=base.DEFAULT_ISSUE294_ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--reference-full68", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=base.DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        args.output = (
            PROJECT_ROOT
            / "logs/issue277"
            / f"geometry_stability_envelope_{stamp}.json"
        )
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
    return 0 if bool(payload["all_pass"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
