#!/usr/bin/env python3
"""Diagnose the Issue #274 OCR border-frame change on retained MMR artifacts only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REUSE_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
ACCEPTED_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
MODEL_PATH = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
OUTPUT_ROOT = PROJECT_ROOT / "logs/issue274_ocr_frame_causal"
CHANGED = ("page_001", "page_025", "page_039", "page_055", "page_064")
CONTROLS = ("page_033", "page_035", "page_040", "page_042")
MATRIX_TARGETS = {"page_025": (0, 0), "page_055": (1, 1)}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _normalise(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("measure_overrides", "overrides"):
            items = payload.get(key)
            if isinstance(items, list):
                return [dict(item) for item in items if isinstance(item, Mapping)]
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    return []


def _semantic(payload: Any) -> dict[tuple[int, int, int], int]:
    return {
        (int(item["page"]), int(item["system"]), int(item["measure"])): int(item.get("skip") or 0)
        for item in _normalise(payload)
    }


def _semantic_items(payload: Any) -> list[dict[str, int]]:
    return [
        {"page": page, "system": system, "measure": measure, "skip": skip}
        for (page, system, measure), skip in sorted(_semantic(payload).items())
    ]


def legacy_frame_dimensions(img_width: int, img_height: int) -> tuple[int, int]:
    """Recreate the pre-border contract for a 20px border on every edge."""

    return max(1, img_width - 40), max(1, img_height - 40)


def _legacy_frame_select(original_select):
    def legacy_frame_select(self, ocr_result, img_width, img_height):
        legacy_width, legacy_height = legacy_frame_dimensions(img_width, img_height)
        return original_select(self, ocr_result, legacy_width, legacy_height)

    return legacy_frame_select


def _preflight(selected_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    from tools.issue264.run_phase_c_mmr_regression import build_page_specs

    specs = {spec.page_id: spec for spec in build_page_specs()}
    if len(specs) != 68:
        raise ValueError("Expected 68 unique evaluation page specs")
    pages = []
    for page_id in selected_ids:
        spec = specs.get(page_id)
        if spec is None:
            raise ValueError(f"Unresolved page spec: {page_id}")
        paths = {
            "numbering_base": ACCEPTED_ROOT / "intermediate" / page_id / "numbering_base.json",
            "mmr_support": REUSE_ROOT / "intermediate" / page_id / "mmr_support.json",
            "accepted": ACCEPTED_ROOT / "intermediate" / page_id / "overrides_mmr.json",
            "current": REUSE_ROOT / "intermediate" / page_id / "overrides_mmr.json",
            "image": spec.image,
        }
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"{page_id}: missing {', '.join(missing)}")
        pages.append({"page_id": page_id, **paths})
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(MODEL_PATH)
    return pages


def _comparison(page_id: str, accepted: Any, current: Any, legacy: Any) -> dict[str, Any]:
    accepted_semantic = _semantic(accepted)
    current_semantic = _semantic(current)
    legacy_semantic = _semantic(legacy)
    return {
        "page_id": page_id,
        "accepted_issue264": _semantic_items(accepted),
        "current_issue274": _semantic_items(current),
        "legacy_frame_diagnostic": _semantic_items(legacy),
        "legacy_exact_vs_accepted": legacy_semantic == accepted_semantic,
        "current_exact_vs_accepted": current_semantic == accepted_semantic,
        "legacy_changed_vs_current": legacy_semantic != current_semantic,
    }


def _variant_from_debug(debug: str) -> str | None:
    marker = "variant="
    return debug.rsplit(marker, 1)[1] if marker in debug else None


def _probe_matrix_condition(
    *,
    processor,
    image,
    system: Mapping[str, Any],
    measure: Mapping[str, Any],
    use_legacy_frame: bool,
    original_select,
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    x1, y1, x2, y2 = measure["bbox"]
    margin = 20
    cx1, cy1 = int(max(0, x1 - margin)), int(max(0, y1 - margin))
    cx2, cy2 = int(min(image_width, x2 + margin)), int(min(image_height, y2 + margin))
    probability = processor.classifier.predict(image[cy1:cy2, cx1:cx2])
    if use_legacy_frame:
        type(processor.ocr).select_best_candidate = _legacy_frame_select(original_select)
    try:
        found_number, score, debug, one_bar_evidence = processor._detect_number_with_evidence(
            image, system, x1, y1, x2, y2, probability, image_width, image_height
        )
    finally:
        if use_legacy_frame:
            type(processor.ocr).select_best_candidate = original_select
    return {
        "measure_bbox": measure["bbox"],
        "staff_bboxes": [staff["bbox"] for staff in system.get("staves", [])],
        "cnn_probability": probability,
        "selected_found_num": found_number,
        "selected_score": score,
        "debug_candidate": debug,
        "ocr_variant": _variant_from_debug(debug),
        "one_bar_evidence": one_bar_evidence,
    }


def run_h2_matrix(output_root: Path = OUTPUT_ROOT) -> Path:
    import cv2
    import torch

    from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import create_mmr_rapidocr

    matrix_pages = _preflight(tuple(MATRIX_TARGETS))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for the H2 causal MMR matrix")
    classifier = MMRClassifier(MODEL_PATH, device)
    ocr = MMROCREngine(ocr_engine=create_mmr_rapidocr("cuda"))
    processor = MMRProcessor(
        model_path=MODEL_PATH,
        device=device,
        classifier=classifier,
        ocr_engine=ocr,
    )
    original_select = MMROCREngine.select_best_candidate
    matrix: dict[str, Any] = {}

    for item in matrix_pages:
        page_id = item["page_id"]
        system_index, measure_index = MATRIX_TARGETS[page_id]
        image = cv2.imread(str(item["image"]))
        if image is None:
            raise RuntimeError(f"Could not read image: {item['image']}")
        image_height, image_width = image.shape[:2]
        support = _load_json(item["mmr_support"])
        accepted_geometry = _load_json(
            ACCEPTED_ROOT / "intermediate" / page_id / "numbering_mmr_geometry.json"
        )
        geometries = {
            "G1_issue274_primary": support["views"]["primary"]["pages"][0]["systems"][system_index],
            "G2_phase_a_fallback": support["views"]["fallback"]["pages"][0]["systems"][
                system_index
            ],
            "G3_accepted_issue264": accepted_geometry["pages"][0]["systems"][system_index],
        }
        conditions = []
        for geometry_name, system in geometries.items():
            measure = system["measures"][measure_index]
            for frame_name, use_legacy_frame in (
                ("F1_current_proc_dimensions", False),
                ("F2_legacy_pre_border_dimensions", True),
            ):
                conditions.append(
                    {
                        "geometry": geometry_name,
                        "frame": frame_name,
                        **_probe_matrix_condition(
                            processor=processor,
                            image=image,
                            system=system,
                            measure=measure,
                            use_legacy_frame=use_legacy_frame,
                            original_select=original_select,
                            image_width=image_width,
                            image_height=image_height,
                        ),
                    }
                )
        key = (int(page_id.split("_")[1]) - 1, system_index, measure_index)
        accepted_found_num = _semantic(_load_json(item["accepted"])).get(key)
        current_found_num = _semantic(_load_json(item["current"])).get(key)
        matrix[page_id] = {
            "target_key": list(key),
            "accepted_found_num": None if accepted_found_num is None else accepted_found_num + 1,
            "issue274_full68_found_num": None
            if current_found_num is None
            else current_found_num + 1,
            "conditions": conditions,
            "expectations": {
                "G1_F1_reproduces_issue274": next(
                    condition["selected_found_num"]
                    for condition in conditions
                    if condition["geometry"] == "G1_issue274_primary"
                    and condition["frame"] == "F1_current_proc_dimensions"
                )
                == (None if current_found_num is None else current_found_num + 1),
                "G3_F2_reproduces_accepted_issue264": next(
                    condition["selected_found_num"]
                    for condition in conditions
                    if condition["geometry"] == "G3_accepted_issue264"
                    and condition["frame"] == "F2_legacy_pre_border_dimensions"
                )
                == (None if accepted_found_num is None else accepted_found_num + 1),
            },
        }

    report_path = output_root / "issue274_ocr_frame_causal.json"
    report = _load_json(report_path)
    report["h2_causal_matrix"] = {
        "geometry": {
            "G1_issue274_primary": "Issue #274 current primary support view",
            "G2_phase_a_fallback": "Issue #274 Phase-A fallback support view",
            "G3_accepted_issue264": "Accepted #264 numbering_mmr_geometry",
        },
        "frame": {
            "F1_current_proc_dimensions": "processed image dimensions with the 20px border on each edge",
            "F2_legacy_pre_border_dimensions": "processed image dimensions minus 40px total per axis",
        },
        "mmr_classifier_initializations": 1,
        "rapidocr_initializations": 1,
        "pages": matrix,
    }
    _write_json(report_path, report)
    print(
        json.dumps(
            {"matrix_expectations": {key: value["expectations"] for key, value in matrix.items()}},
            indent=2,
        )
    )
    return report_path


def run(output_root: Path = OUTPUT_ROOT) -> Path:
    import torch

    from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import (
        collect_rapidocr_providers,
        create_mmr_rapidocr,
        providers_include_cuda,
    )

    selected_ids = CHANGED + CONTROLS
    pages = _preflight(selected_ids)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for the 9-page causal MMR diagnostic")

    classifier = MMRClassifier(MODEL_PATH, device)
    provider = create_mmr_rapidocr("cuda")
    ocr = MMROCREngine(ocr_engine=provider)
    processor = MMRProcessor(
        model_path=MODEL_PATH,
        device=device,
        classifier=classifier,
        ocr_engine=ocr,
    )
    pages_data = [_load_json(item["numbering_base"]) for item in pages]
    image_paths = [item["image"] for item in pages]
    support_data = [_load_json(item["mmr_support"]) for item in pages]

    original_select = MMROCREngine.select_best_candidate
    MMROCREngine.select_best_candidate = _legacy_frame_select(original_select)
    try:
        legacy_outputs = processor.process_pages(pages_data, image_paths, support_data=support_data)
    finally:
        MMROCREngine.select_best_candidate = original_select

    comparisons = []
    for item, legacy in zip(pages, legacy_outputs):
        _write_json(
            output_root / "intermediate" / item["page_id"] / "legacy_frame_overrides_mmr.json",
            legacy,
        )
        comparisons.append(
            _comparison(
                item["page_id"],
                _load_json(item["accepted"]),
                _load_json(item["current"]),
                legacy,
            )
        )

    comparison_by_id = {item["page_id"]: item for item in comparisons}
    changed_exact = [
        page_id for page_id in CHANGED if comparison_by_id[page_id]["legacy_exact_vs_accepted"]
    ]
    control_exact = [
        page_id for page_id in CONTROLS if comparison_by_id[page_id]["legacy_exact_vs_accepted"]
    ]
    h1 = len(changed_exact) == len(CHANGED) and len(control_exact) == len(CONTROLS)
    report = {
        "schema_version": "issue274.ocr_frame_causal.v1",
        "evaluation_contract": {
            "diagnostic_only_monkeypatch": True,
            "production_source_modified": False,
            "mmr_full68_reexecuted": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "numbering_reexecuted": False,
            "mmr_classifier_initializations": 1,
            "rapidocr_initializations": 1,
            "ocr_frame_contract": "proc_img dimensions minus 40px, preserving Issue #264 pre-border dimensions",
        },
        "pages": list(selected_ids),
        "changed_pages_vs_accepted": [
            page_id
            for page_id in CHANGED
            if not comparison_by_id[page_id]["current_exact_vs_accepted"]
        ],
        "exact_pages_vs_accepted": [
            item["page_id"] for item in comparisons if item["legacy_exact_vs_accepted"]
        ],
        "h1_all_changed_and_controls_return_to_accepted": h1,
        "conclusion": "H1" if h1 else "H2",
        "page_025_result": comparison_by_id["page_025"],
        "page_055_result": comparison_by_id["page_055"],
        "page_039_result": comparison_by_id["page_039"],
        "page_033_focused_result": comparison_by_id["page_033"],
        "page_042_five_overrides": {
            **comparison_by_id["page_042"],
            "legacy_override_count": len(
                _normalise(legacy_outputs[selected_ids.index("page_042")])
            ),
        },
        "support_stats": processor.support_stats,
        "rapidocr": {
            "providers": collect_rapidocr_providers(provider),
            "cuda_confirmed": providers_include_cuda(collect_rapidocr_providers(provider)),
        },
        "comparisons": comparisons,
    }
    output_path = output_root / "issue274_ocr_frame_causal.json"
    _write_json(output_path, report)
    print(
        json.dumps(
            {
                "conclusion": report["conclusion"],
                "changed_exact": changed_exact,
                "control_exact": control_exact,
                "support_stats": processor.support_stats,
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
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--h2-matrix", action="store_true")
    args = parser.parse_args()
    if args.preflight_only:
        pages = _preflight(CHANGED + CONTROLS)
        print(f"PREFLIGHT OK: {len(pages)} retained pages, no MMR invoked")
        return 0
    if args.h2_matrix:
        run_h2_matrix(args.output_root)
        return 0
    run(args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
