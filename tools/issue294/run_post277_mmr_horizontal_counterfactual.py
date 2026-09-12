#!/usr/bin/env python3
"""Run a diagnostic MMR replay with maintained-HOMR topology but production measure X geometry.

This is experiment-only and targets the three focused pages that regressed after #277.
It keeps B's reconstructed topology/numbering and current-x4 vertical support, replaces only
measure x1/x2 with the corresponding production-A values, then reruns the current MMR CNN/OCR.
No thresholds, production dispatch, or candidate grouping logic are changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

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
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue294._mapping_guarded_candidate_mmr_rescore import _accepted_rebase_pages
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import _load_json, _load_matrix_pages
from tools.issue294.run_post277_mapping_guarded_mmr import (
    DEFAULT_ACCEPTED_REBASE,
    DEFAULT_MANIFEST,
    DEFAULT_MODEL,
    _build_variant_inputs,
    _score_variant,
)

PAGE_IDS = ("page_002", "page_034", "page_042")


def _replace_measure_x(candidate: dict[str, Any], production: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(candidate)
    candidate_pages = result.get("pages", [])
    production_pages = production.get("pages", [])
    if len(candidate_pages) != 1 or len(production_pages) != 1:
        raise ValueError("Counterfactual expects one-page numbering payloads")
    candidate_systems = candidate_pages[0].get("systems", [])
    production_systems = production_pages[0].get("systems", [])
    if len(candidate_systems) != len(production_systems):
        raise ValueError("A/B system topology differs")
    for sys_idx, (candidate_system, production_system) in enumerate(
        zip(candidate_systems, production_systems)
    ):
        candidate_measures = candidate_system.get("measures", [])
        production_measures = production_system.get("measures", [])
        if len(candidate_measures) != len(production_measures):
            raise ValueError(f"A/B measure topology differs in system {sys_idx}")
        for candidate_measure, production_measure in zip(candidate_measures, production_measures):
            candidate_bbox = list(candidate_measure["bbox"])
            production_bbox = list(production_measure["bbox"])
            candidate_bbox[0] = int(production_bbox[0])
            candidate_bbox[2] = int(production_bbox[2])
            candidate_measure["bbox"] = candidate_bbox
    return result


def _page_summary(scored: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(page["page_id"]): {
            "counts": page["scoring"]["counts"],
            "expected": page["expected"],
            "actual": page["actual"],
            "row_start_semantic_equal": page["row_start_semantic_equal"],
            "numbering_shape": page["numbering_shape"],
        }
        for page in scored["pages"]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--accepted-rebase-report", type=Path, default=DEFAULT_ACCEPTED_REBASE)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    accepted_rebase_path = args.accepted_rebase_report.resolve()
    model_path = args.model.resolve()
    for required in (manifest_path, accepted_rebase_path, model_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    manifest = _load_json(manifest_path)
    matrix_pages = _load_matrix_pages(manifest)
    accepted_pages, accepted_provenance = _accepted_rebase_pages(accepted_rebase_path)
    specs_by_id = {str(spec.page_id): spec for spec in build_page_specs()}
    specs = [specs_by_id[page_id] for page_id in PAGE_IDS]

    a_bases, images, _a_supports, _a_modes = _build_variant_inputs(
        specs=specs,
        matrix_pages=matrix_pages,
        label="A_pinned",
        pipeline_factory=MeasureNumberingPipeline,
    )
    b_bases, b_images, b_supports, b_modes = _build_variant_inputs(
        specs=specs,
        matrix_pages=matrix_pages,
        label="B_b377",
        pipeline_factory=MappingGuardedConnectorPositivePipeline,
    )
    if [str(path) for path in images] != [str(path) for path in b_images]:
        raise RuntimeError("A/B image inputs differ")

    counterfactual_bases: list[dict[str, Any]] = []
    counterfactual_supports: list[dict[str, Any]] = []
    x_deltas: dict[str, list[dict[str, Any]]] = {}
    for spec, a_base, b_base, b_support in zip(specs, a_bases, b_bases, b_supports):
        cf_base = _replace_measure_x(b_base, a_base)
        support_mask = Path(str(b_support["provenance"]["current_homr_staff_mask"]))
        cf_support = build_mmr_support_data(cf_base, support_mask)
        counterfactual_bases.append(cf_base)
        counterfactual_supports.append(cf_support)

        page_deltas: list[dict[str, Any]] = []
        for sys_idx, (a_system, b_system) in enumerate(
            zip(a_base["pages"][0]["systems"], b_base["pages"][0]["systems"])
        ):
            for measure_idx, (a_measure, b_measure) in enumerate(
                zip(a_system.get("measures", []), b_system.get("measures", []))
            ):
                a_bbox = [int(v) for v in a_measure["bbox"]]
                b_bbox = [int(v) for v in b_measure["bbox"]]
                if a_bbox[0] != b_bbox[0] or a_bbox[2] != b_bbox[2]:
                    page_deltas.append(
                        {
                            "system": sys_idx,
                            "measure": measure_idx,
                            "A_x": [a_bbox[0], a_bbox[2]],
                            "B_x": [b_bbox[0], b_bbox[2]],
                            "delta": [b_bbox[0] - a_bbox[0], b_bbox[2] - a_bbox[2]],
                        }
                    )
        x_deltas[str(spec.page_id)] = page_deltas

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Counterfactual MMR replay requires CUDA")
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
    actual = processor.process_pages(
        counterfactual_bases,
        images,
        support_data=counterfactual_supports,
    )
    scored = _score_variant(
        name="B_b377_topology_with_A_measure_x",
        specs=specs,
        bases=counterfactual_bases,
        actual=actual,
        mapping_modes=b_modes,
        accepted_pages=accepted_pages,
    )

    output = {
        "schema_version": "issue294.post277_mmr_horizontal_counterfactual.v1",
        "status": "completed",
        "diagnostic_only": True,
        "pages": list(PAGE_IDS),
        "inputs": {
            "manifest": str(manifest_path),
            "accepted_rebase_report": str(accepted_rebase_path),
            "model": str(model_path),
        },
        "contract": {
            "topology_and_numbering": "B_b377_mapping_guarded",
            "measure_y": "B_b377_mapping_guarded",
            "measure_x": "A_production_corresponding_measure",
            "vertical_mmr_support": "current_x4_staff_mask_rebuilt_from_counterfactual_base",
            "threshold_changes": False,
            "production_dispatch_changes": False,
        },
        "runtime": {
            "device": str(device),
            "rapidocr_providers": providers,
            "support_stats": dict(processor.support_stats),
        },
        "accepted_issue264_rebase": accepted_provenance,
        "x_deltas_B_vs_A": x_deltas,
        "totals": scored["totals"],
        "gates": scored["gates"],
        "page_results": _page_summary(scored),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
