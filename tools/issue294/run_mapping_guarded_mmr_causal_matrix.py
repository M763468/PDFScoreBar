#!/usr/bin/env python3
"""Run a focused Issue #294 MMR causal matrix on the retained differing keys.

This experiment reuses the completed full68 detector/HOMR/SR/OMR artifacts and
reconstructs only the mapping-guarded numbering/MMR support geometry.  It reruns
CNN/OCR only for the small set of measure keys whose retained MMR overrides differ
between candidate-native and frozen-A geometry.  B/C were already proven geometry
and retained-MMR exact, so B_b377 is the single causal representative.

The matrix isolates primary/alternate/fallback support-view source and then splits
primary-view changes into target-measure bbox vs system-staff bbox contributions.
Production source is not modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
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
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from tools.issue294.diagnose_mapping_guarded_mmr_geometry_deltas import _numbering
from tools.issue294.rescore_full68_mmr_audit import (
    _load_json,
    _load_matrix_pages,
    _resolve_project_path,
)

DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
VIEW_NAMES = ("primary", "implicit_start_alternate", "fallback")
CONDITIONS = (
    "frozen_all",
    "native_all",
    "primary_native_only",
    "alternate_native_only",
    "fallback_native_only",
    "primary_measure_native_only",
    "primary_staff_native_only",
    "native_revert_primary_measure",
    "native_revert_primary_staff",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _condition_systems(
    frozen_support: Mapping[str, Any],
    native_support: Mapping[str, Any],
    *,
    system_index: int,
    measure_index: int,
    condition: str,
) -> dict[str, dict[str, Any]]:
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown causal condition: {condition}")

    def system(support: Mapping[str, Any], view: str) -> dict[str, Any]:
        return deepcopy(support["views"][view]["pages"][0]["systems"][system_index])

    frozen = {view: system(frozen_support, view) for view in VIEW_NAMES}
    native = {view: system(native_support, view) for view in VIEW_NAMES}

    if condition == "frozen_all":
        return frozen
    if condition == "native_all":
        return native

    result = deepcopy(frozen)
    if condition == "primary_native_only":
        result["primary"] = native["primary"]
    elif condition == "alternate_native_only":
        result["implicit_start_alternate"] = native["implicit_start_alternate"]
    elif condition == "fallback_native_only":
        result["fallback"] = native["fallback"]
    elif condition == "primary_measure_native_only":
        result["primary"]["measures"][measure_index]["bbox"] = deepcopy(
            native["primary"]["measures"][measure_index]["bbox"]
        )
    elif condition == "primary_staff_native_only":
        result["primary"]["staves"] = deepcopy(native["primary"].get("staves", []))
    elif condition == "native_revert_primary_measure":
        result = deepcopy(native)
        result["primary"]["measures"][measure_index]["bbox"] = deepcopy(
            frozen["primary"]["measures"][measure_index]["bbox"]
        )
    elif condition == "native_revert_primary_staff":
        result = deepcopy(native)
        result["primary"]["staves"] = deepcopy(frozen["primary"].get("staves", []))
    return result


def _detect(
    processor: MMRProcessor,
    *,
    image,
    system: Mapping[str, Any],
    measure: Mapping[str, Any],
    probability: float,
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    x1, y1, x2, y2 = measure["bbox"]
    found_num, score, debug, evidence = processor._detect_number_with_evidence(
        image,
        system,
        x1,
        y1,
        x2,
        y2,
        probability,
        image_width,
        image_height,
    )
    valid, status, vetoed = processor._valid_status(found_num, probability, score, evidence)
    return {
        "found_num": found_num,
        "skip": None if found_num is None else int(found_num) - 1,
        "score": float(score),
        "debug": str(debug),
        "one_bar_evidence": int(evidence),
        "valid": bool(valid),
        "status": str(status),
        "vetoed": bool(vetoed),
    }


def _probe_condition(
    processor: MMRProcessor,
    *,
    image,
    systems: Mapping[str, Mapping[str, Any]],
    measure_index: int,
) -> dict[str, Any]:
    image_height, image_width = image.shape[:2]
    primary_system = systems["primary"]
    alternate_system = systems["implicit_start_alternate"]
    fallback_system = systems["fallback"]
    primary_measure = primary_system["measures"][measure_index]
    x1, y1, x2, y2 = primary_measure["bbox"]
    margin = 20
    cx1, cy1 = int(max(0, x1 - margin)), int(max(0, y1 - margin))
    cx2, cy2 = int(min(image_width, x2 + margin)), int(min(image_height, y2 + margin))
    probability = float(processor.classifier.predict(image[cy1:cy2, cx1:cx2]))

    primary = _detect(
        processor,
        image=image,
        system=primary_system,
        measure=primary_measure,
        probability=probability,
        image_width=image_width,
        image_height=image_height,
    )
    found_num = primary["found_num"]
    valid = bool(primary["valid"])
    status = str(primary["status"])
    vetoed = bool(primary["vetoed"])
    selected_stage = "primary"
    alternate = None
    fallback = None

    alternate_measure = alternate_system["measures"][measure_index]
    if valid and alternate_measure["bbox"][0] != primary_measure["bbox"][0]:
        alternate = _detect(
            processor,
            image=image,
            system=alternate_system,
            measure=alternate_measure,
            probability=probability,
            image_width=image_width,
            image_height=image_height,
        )
        if alternate["vetoed"]:
            valid, status, vetoed = False, "one_bar_veto", True
            selected_stage = "alternate_veto"

    if found_num is None and probability > processor.threshold:
        fallback_measure = fallback_system["measures"][measure_index]
        fallback = _detect(
            processor,
            image=image,
            system=fallback_system,
            measure=fallback_measure,
            probability=probability,
            image_width=image_width,
            image_height=image_height,
        )
        found_num = fallback["found_num"]
        valid = bool(fallback["valid"])
        status = str(fallback["status"])
        vetoed = bool(fallback["vetoed"])
        selected_stage = "fallback"

    return {
        "cnn_probability": probability,
        "primary_measure_bbox": list(primary_measure["bbox"]),
        "primary_staff_bboxes": [list(staff["bbox"]) for staff in primary_system.get("staves", [])],
        "primary": primary,
        "alternate": alternate,
        "fallback": fallback,
        "selected_stage": selected_stage,
        "final_found_num": found_num if valid else None,
        "final_skip": (int(found_num) - 1) if valid and found_num is not None else None,
        "final_status": status,
        "final_vetoed": vetoed,
    }


def _classify(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    frozen = results["frozen_all"]["final_skip"]
    native = results["native_all"]["final_skip"]
    singles = {
        name: results[name]["final_skip"]
        for name in ("primary_native_only", "alternate_native_only", "fallback_native_only")
    }
    components = {
        name: results[name]["final_skip"]
        for name in (
            "primary_measure_native_only",
            "primary_staff_native_only",
            "native_revert_primary_measure",
            "native_revert_primary_staff",
        )
    }
    return {
        "frozen_final_skip": frozen,
        "native_final_skip": native,
        "single_view_sufficient_for_native": [
            name for name, value in singles.items() if frozen != native and value == native
        ],
        "single_view_results": singles,
        "primary_component_results": components,
        "reverting_primary_measure_restores_frozen": (
            frozen != native and components["native_revert_primary_measure"] == frozen
        ),
        "reverting_primary_staff_restores_frozen": (
            frozen != native and components["native_revert_primary_staff"] == frozen
        ),
    }


def run(
    manifest_path: Path,
    geometry_path: Path,
    model_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    geometry = _load_json(geometry_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("Full68 manifest is not completed")
    if not isinstance(geometry, Mapping) or geometry.get("status") != "completed":
        raise ValueError("Geometry diagnostic is not completed")
    if not geometry.get("B_C_differing_page_sets_equal") or not geometry.get(
        "B_C_geometry_diagnostic_exact"
    ):
        raise RuntimeError(
            "B/C geometry equivalence gate failed; one-label causal probe is invalid"
        )
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Focused Issue #294 MMR causal matrix requires CUDA")
    classifier = MMRClassifier(model_path, device)
    provider = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(provider)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR did not activate CUDA: {providers}")
    processor = MMRProcessor(
        model_path=model_path,
        device=device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=provider),
    )

    matrix_pages = _load_matrix_pages(manifest)
    pages = geometry["labels"]["B_b377"]["pages"]
    records: list[dict[str, Any]] = []
    reproduction_failures: list[dict[str, Any]] = []

    for page_record in pages:
        page_id = str(page_record["page_id"])
        matrix_key = (str(page_record["score"]), str(page_record["page_name"]))
        matrix_page = matrix_pages.get(matrix_key)
        if matrix_page is None:
            raise RuntimeError(f"Full68 matrix lacks {page_id}: {matrix_key}")
        image_path = _resolve_project_path(str(matrix_page["image"]))
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        fixed = _load_json(
            _resolve_project_path(str(matrix_page["fixed_inputs"]["support_result"]))
        )
        current_staff_mask = _resolve_project_path(str(fixed["current_homr_staff_mask"]))
        global_index = int(page_id.removeprefix("page_")) - 1

        numbering_by_mode: dict[str, dict[str, Any]] = {}
        support_by_mode: dict[str, dict[str, Any]] = {}
        for mode in ("frozen_A_geometry", "candidate_native_geometry"):
            numbering, _mapping_mode = _numbering(
                matrix_page,
                mode=mode,
                label="B_b377",
                page_number=global_index + 1,
            )
            numbering_by_mode[mode] = numbering
            support_by_mode[mode] = build_mmr_support_data(numbering, current_staff_mask)

        for key_record in page_record["keys"]:
            key = tuple(int(value) for value in key_record["key"])
            _page, system_index, measure_index = key
            condition_results: dict[str, Any] = {}
            for condition in CONDITIONS:
                systems = _condition_systems(
                    support_by_mode["frozen_A_geometry"],
                    support_by_mode["candidate_native_geometry"],
                    system_index=system_index,
                    measure_index=measure_index,
                    condition=condition,
                )
                condition_results[condition] = _probe_condition(
                    processor,
                    image=image,
                    systems=systems,
                    measure_index=measure_index,
                )

            retained_frozen = key_record["retained_actual"]["frozen_A_geometry"]
            retained_native = key_record["retained_actual"]["candidate_native_geometry"]
            frozen_ok = condition_results["frozen_all"]["final_skip"] == retained_frozen
            native_ok = condition_results["native_all"]["final_skip"] == retained_native
            if not frozen_ok or not native_ok:
                reproduction_failures.append(
                    {
                        "page_id": page_id,
                        "key": list(key),
                        "retained_frozen": retained_frozen,
                        "probed_frozen": condition_results["frozen_all"]["final_skip"],
                        "retained_native": retained_native,
                        "probed_native": condition_results["native_all"]["final_skip"],
                    }
                )
            records.append(
                {
                    "page_id": page_id,
                    "score": page_record["score"],
                    "page_name": page_record["page_name"],
                    "key": list(key),
                    "expected": key_record["expected"],
                    "retained_actual": key_record["retained_actual"],
                    "reproduction": {"frozen": frozen_ok, "native": native_ok},
                    "classification": _classify(condition_results),
                    "conditions": condition_results,
                }
            )

    report = {
        "schema_version": "issue294.mapping_guarded_mmr_causal_matrix.v1",
        "status": "completed",
        "execution_contract": {
            "production_code_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "numbering_reconstructed": True,
            "full68_mmr_reexecuted": False,
            "focused_cnn_ocr_reexecuted": True,
            "one_classifier_initialization": True,
            "one_rapidocr_initialization": True,
            "causal_label": "B_b377 because B/C retained geometry and MMR deltas are exact",
        },
        "source_manifest": str(manifest_path),
        "source_geometry_diagnostic": str(geometry_path),
        "runtime": {"device": str(device), "rapidocr_providers": providers},
        "conditions": list(CONDITIONS),
        "records": records,
        "reproduction_failures": reproduction_failures,
        "gates": {
            "B_C_equivalence_precondition": True,
            "all_frozen_native_retained_deltas_reproduced": not reproduction_failures,
            "record_count_nonzero": bool(records),
        },
    }
    _write_json(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full68-manifest",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/full68_host.json",
    )
    parser.add_argument(
        "--geometry-diagnostic",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/"
        "mapping_guarded_mmr_geometry_delta_diagnostic_01.json",
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/"
        "mapping_guarded_mmr_causal_matrix_01.json",
    )
    args = parser.parse_args()
    payload = run(args.full68_manifest, args.geometry_diagnostic, args.model, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "record_count": len(payload["records"]),
                "reproduction_failures": payload["reproduction_failures"],
                "gates": payload["gates"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if all(payload["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
