#!/usr/bin/env python3
"""Evaluate original-image HOMR staff-mask grafting without rebuilding numbering.

This is an architecture experiment only.  It reads retained Issue #264 artifacts,
uses the production Issue #274 support mapper unchanged, and never invokes HOMR,
detector, SR, OMR-DLN, or a numbering pipeline.  O0 is the accepted #264
``numbering_mmr_geometry`` payload; O1 retains Phase-A topology/x and grafts
vertical geometry from the retained original-image current-HOMR staff mask.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Mapping

from src.pipeline.mmr_support_reuse import build_mmr_support_data
from src.pipeline.utils.io import load_json, write_json
from tools.issue274.validate_mmr_support_mapping import _visible_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACCEPTED_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
CURRENT_X4_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
OUTPUT_ROOT = PROJECT_ROOT / "logs/issue274_original_geometry_graft"
MODEL_PATH = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"

REPRESENTATIVE_PAGES = [
    "page_001",
    "page_013",
    "page_025",
    "page_033",
    "page_035",
    "page_039",
    "page_040",
    "page_042",
    "page_045",
    "page_055",
    "page_066",
    "page_067",
]
PHASE_B_LAYOUT_DIVERGENCE_PAGES = ["page_013", "page_045", "page_066", "page_067"]
TARGETS = {"page_025": (0, 0), "page_055": (1, 1)}


def _semantic(payload: Any) -> dict[tuple[int, int, int], int]:
    from tools.issue264.run_phase_c_mmr_regression import (
        index_overrides,
        normalise_overrides,
        override_skip,
    )

    return {
        tuple(int(part) for part in key): override_skip(item)
        for key, item in index_overrides(normalise_overrides(payload)).items()
    }


def _semantic_rows(payload: Any) -> list[dict[str, int]]:
    return [
        {"page": key[0], "system": key[1], "measure": key[2], "skip": skip}
        for key, skip in sorted(_semantic(payload).items())
    ]


def _page(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Expected one page payload")
    return pages[0]


def _systems(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    systems = _page(payload).get("systems")
    if not isinstance(systems, list):
        raise ValueError("Page payload lacks systems")
    return systems


def _bbox(item: Mapping[str, Any]) -> list[int]:
    value = item.get("bbox")
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("Expected a four-value bbox")
    return [int(part) for part in value]


def geometry_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return only geometry consumed by MMR, in a deterministic structure."""

    systems = _systems(payload)
    return {
        "system_count": len(systems),
        "staff_counts": [len(system.get("staves", [])) for system in systems],
        "measure_counts": [len(system.get("measures", [])) for system in systems],
        "staff_bboxes": [
            [_bbox(staff) for staff in system.get("staves", [])] for system in systems
        ],
        "measure_bboxes": [
            [_bbox(measure) for measure in system.get("measures", [])] for system in systems
        ],
    }


def compare_geometry(o0: Mapping[str, Any], o1: Mapping[str, Any]) -> dict[str, Any]:
    """Compare O1 support geometry to accepted O0 without accepting approximations."""

    expected, actual = geometry_snapshot(o0), geometry_snapshot(o1)
    topology_equal = all(
        expected[key] == actual[key] for key in ("system_count", "staff_counts", "measure_counts")
    )
    staff_bbox_exact = expected["staff_bboxes"] == actual["staff_bboxes"]
    measure_bbox_exact = expected["measure_bboxes"] == actual["measure_bboxes"]
    return {
        "topology_equal": topology_equal,
        "staff_bbox_exact": staff_bbox_exact,
        "measure_bbox_exact": measure_bbox_exact,
        "geometry_exact": topology_equal and staff_bbox_exact and measure_bbox_exact,
        "o0": expected,
        "o1": actual,
    }


def _target_geometry(payload: Mapping[str, Any], system: int, measure: int) -> dict[str, list[int]]:
    systems = _systems(payload)
    return {
        "measure_bbox": _bbox(systems[system]["measures"][measure]),
        "staff_bboxes": [_bbox(item) for item in systems[system].get("staves", [])],
    }


def _original_mask(page_id: str) -> Path:
    result_path = ACCEPTED_ROOT / "intermediate/mmr_staff_geometry" / page_id / "result.json"
    result = load_json(result_path)
    masks = result.get("staff_masks")
    if not isinstance(masks, Mapping) or len(masks) != 1:
        raise ValueError(f"{page_id}: expected one retained original-HOMR staff mask")
    mask_value = next(iter(masks.values()))
    if not isinstance(mask_value, str):
        raise ValueError(f"{page_id}: invalid retained original-HOMR staff mask")
    mask = _visible_path(mask_value, PROJECT_ROOT)
    if not mask.is_file():
        raise FileNotFoundError(mask)
    return mask


def _preflight() -> list[dict[str, Any]]:
    from tools.issue264.run_phase_c_mmr_regression import build_page_specs

    specs = build_page_specs()
    by_id = {spec.page_id: spec for spec in specs}
    expected_ids = [f"page_{index:03d}" for index in range(1, 69)]
    if [spec.page_id for spec in specs] != expected_ids:
        raise ValueError("Issue #264 page mapping is not page_001..page_068")
    rows: list[dict[str, Any]] = []
    for page_id in expected_ids:
        base = ACCEPTED_ROOT / "intermediate" / page_id / "numbering_base.json"
        o0 = ACCEPTED_ROOT / "intermediate" / page_id / "numbering_mmr_geometry.json"
        accepted = ACCEPTED_ROOT / "intermediate" / page_id / "overrides_mmr.json"
        current_x4 = CURRENT_X4_ROOT / "intermediate" / page_id / "overrides_mmr.json"
        mask = _original_mask(page_id)
        missing = [
            label
            for label, path in (
                ("numbering_base", base),
                ("numbering_mmr_geometry", o0),
                ("accepted_overrides", accepted),
                ("issue274_x4_overrides", current_x4),
                ("source_image", by_id[page_id].image),
                ("original_homr_staff_mask", mask),
            )
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(f"{page_id}: missing {', '.join(missing)}")
        rows.append(
            {
                "page_id": page_id,
                "base": base,
                "o0": o0,
                "accepted": accepted,
                "current_x4": current_x4,
                "image": by_id[page_id].image,
                "original_mask": mask,
            }
        )
    return rows


def _geometry_report(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    page_support: dict[str, dict[str, Any]] = {}
    page_reports = []
    topology_mismatches = []
    exact_by_view = {"primary": 0, "implicit_start_alternate": 0, "fallback": 0}

    for row in rows:
        page_id = row["page_id"]
        support = build_mmr_support_data(load_json(row["base"]), row["original_mask"])
        page_support[page_id] = support
        o0 = load_json(row["o0"])
        comparisons = {view: compare_geometry(o0, support["views"][view]) for view in exact_by_view}
        for view, comparison in comparisons.items():
            exact_by_view[view] += int(comparison["geometry_exact"])
        if not all(comparison["topology_equal"] for comparison in comparisons.values()):
            topology_mismatches.append(page_id)
        page_reports.append(
            {
                "page_id": page_id,
                "original_image_current_homr_staff_mask": str(row["original_mask"]),
                "mapping_provenance": support["provenance"],
                "comparisons": comparisons,
            }
        )

    by_page = {entry["page_id"]: entry for entry in page_reports}
    focused = {
        page_id: {
            "target": {"system": system, "measure": measure},
            "o0": _target_geometry(
                load_json(next(row for row in rows if row["page_id"] == page_id)["o0"]),
                system,
                measure,
            ),
            "o1_primary": _target_geometry(
                page_support[page_id]["views"]["primary"], system, measure
            ),
            "o1_implicit_start_alternate": _target_geometry(
                page_support[page_id]["views"]["implicit_start_alternate"], system, measure
            ),
            "o1_fallback": _target_geometry(
                page_support[page_id]["views"]["fallback"], system, measure
            ),
        }
        for page_id, (system, measure) in TARGETS.items()
    }
    phase_b_divergence = {
        page_id: {
            "o0_layout_source": "phase_a_base_fallback",
            "comparisons": by_page[page_id]["comparisons"],
        }
        for page_id in PHASE_B_LAYOUT_DIVERGENCE_PAGES
    }
    report = {
        "schema_version": "issue274.original_geometry_graft.geometry.v1",
        "variant": {
            "o0": "accepted_issue264_numbering_mmr_geometry",
            "o1": "phase_a_numbering_base + retained_original_image_current_homr_staff_mask",
            "mapping_algorithm": "src.pipeline.mmr_support_reuse.build_mmr_support_data",
            "topology_and_normal_x": "Phase-A numbering_base",
        },
        "scope": {
            "pages": len(rows),
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "numbering_reexecuted": False,
            "second_numbering_rebuild": 0,
        },
        "summary": {
            "topology_mismatch_pages": topology_mismatches,
            "topology_exact_pages": len(rows) - len(topology_mismatches),
            "geometry_exact_pages_by_view": exact_by_view,
        },
        "focused_targets": focused,
        "phase_b_layout_divergence_pages": phase_b_divergence,
        "pages": page_reports,
    }
    return report, page_support


def _representative_report(
    rows: list[dict[str, Any]], support_by_page: Mapping[str, dict[str, Any]]
) -> dict[str, Any]:
    import torch

    from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
    from src.measure_numbering.rapidocr_provider import (
        collect_rapidocr_providers,
        create_mmr_rapidocr,
        providers_include_cuda,
    )
    from src.pipeline.steps.numbering import run_mmr_batch

    by_id = {row["page_id"]: row for row in rows}
    selected = [by_id[page_id] for page_id in REPRESENTATIVE_PAGES]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Representative original-mask graft requires CUDA")
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(MODEL_PATH)

    started = time.perf_counter()
    classifier = MMRClassifier(MODEL_PATH, device)
    provider = create_mmr_rapidocr("cuda")
    ocr = MMROCREngine(ocr_engine=provider)
    setattr(ocr, "_rapidocr_provider_mode", "cuda")
    output_paths = [
        OUTPUT_ROOT / "intermediate" / row["page_id"] / "overrides_mmr.json" for row in selected
    ]
    support_stats: dict[str, int] = {}
    processor_state: dict[str, Any] = {}
    actual = run_mmr_batch(
        pages_data=[load_json(row["base"]) for row in selected],
        image_paths=[row["image"] for row in selected],
        output_paths=output_paths,
        model_path=MODEL_PATH,
        device=device,
        classifier=classifier,
        ocr_engine=ocr,
        rapidocr_provider="cuda",
        support_data=[support_by_page[row["page_id"]] for row in selected],
        support_stats=support_stats,
        processor_state=processor_state,
    )
    pages = []
    for row, o1_payload in zip(selected, actual):
        accepted = load_json(row["accepted"])
        x4_only = load_json(row["current_x4"])
        pages.append(
            {
                "page_id": row["page_id"],
                "accepted_issue264": _semantic_rows(accepted),
                "issue274_current_x4_only": _semantic_rows(x4_only),
                "o1_original_mask_graft": _semantic_rows(o1_payload),
                "o1_equals_accepted": _semantic(o1_payload) == _semantic(accepted),
            }
        )
    providers = collect_rapidocr_providers(provider)
    return {
        "schema_version": "issue274.original_geometry_graft.mmr.v1",
        "scope": {
            "pages": REPRESENTATIVE_PAGES,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "numbering_reexecuted": False,
            "second_numbering_rebuild": 0,
            "full68_mmr_scan": False,
        },
        "runtime": {
            "elapsed_sec": time.perf_counter() - started,
            "classifier_initialization_count": 1,
            "rapidocr_initialization_count": 1,
        },
        "rapidocr": {
            "providers": providers,
            "cuda_confirmed": providers_include_cuda(providers),
        },
        "support_stats": support_stats,
        "summary": {
            "page_count": len(pages),
            "exact_pages": sum(page["o1_equals_accepted"] for page in pages),
            "changed_pages": [page["page_id"] for page in pages if not page["o1_equals_accepted"]],
        },
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-only", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    rows = _preflight()
    geometry, support_by_page = _geometry_report(rows)
    geometry["runtime"] = {
        "elapsed_sec": time.perf_counter() - started,
        "classifier_initialization_count": 0,
        "rapidocr_initialization_count": 0,
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_ROOT / "issue274_original_geometry_graft_geometry.json", geometry)
    if geometry["summary"]["topology_mismatch_pages"]:
        write_json(
            OUTPUT_ROOT / "issue274_original_geometry_graft_mmr.json",
            {
                "schema_version": "issue274.original_geometry_graft.mmr.v1",
                "status": "skipped_topology_mismatch",
                "reason": "O1 support topology differs from accepted O0 geometry",
                "topology_mismatch_pages": geometry["summary"]["topology_mismatch_pages"],
                "scope": {
                    "representative_pages": REPRESENTATIVE_PAGES,
                    "full68_mmr_scan": False,
                    "mmr_invocations": 0,
                    "detector_reexecuted": False,
                    "homr_reexecuted": False,
                    "sr_reexecuted": False,
                    "omr_dln_reexecuted": False,
                    "numbering_reexecuted": False,
                },
                "runtime": {
                    "elapsed_sec": geometry["runtime"]["elapsed_sec"],
                    "classifier_initialization_count": 0,
                    "rapidocr_initialization_count": 0,
                },
            },
        )
        print("Geometry topology mismatch; representative MMR not run", flush=True)
        return
    if args.geometry_only:
        print("Geometry comparison complete; representative MMR not run", flush=True)
        return

    report = _representative_report(rows, support_by_page)
    write_json(OUTPUT_ROOT / "issue274_original_geometry_graft_mmr.json", report)
    if report["summary"]["exact_pages"] != len(REPRESENTATIVE_PAGES):
        raise SystemExit("O1 representative output differs from accepted #264; see report")


if __name__ == "__main__":
    main()
