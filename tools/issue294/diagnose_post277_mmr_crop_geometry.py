#!/usr/bin/env python3
"""Compare A/B/C MMR crop geometry for focused Issue #294 regressions.

This is a retained-artifact diagnostic only. It reconstructs numbering/support views
from the completed retained full68 manifest and reports geometry for logical MMR
events that differ on the degraded focused pages. It does not run CNN/OCR inference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import _load_json, _load_matrix_pages
from tools.issue294.run_post277_mapping_guarded_mmr import (
    DEFAULT_MANIFEST,
    _build_variant_inputs,
)

DEGRADED_PAGE_IDS = ("page_002", "page_034", "page_042")
VARIANTS = (
    ("A", "A_pinned", MeasureNumberingPipeline),
    ("B", "B_b377", MappingGuardedConnectorPositivePipeline),
    ("C", "C_latest", MappingGuardedConnectorPositivePipeline),
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


def _event_keys(page: Mapping[str, Any]) -> set[tuple[int, int]]:
    keys: set[tuple[int, int]] = set()
    for field in ("expected", "actual"):
        for item in page.get(field, []):
            keys.add((int(item["system"]), int(item["measure"])))
    return keys


def _bbox_at(payload: Mapping[str, Any], system_idx: int, measure_idx: int) -> list[int]:
    measure = payload["pages"][0]["systems"][system_idx]["measures"][measure_idx]
    return [int(value) for value in measure["bbox"]]


def _staff_bboxes(payload: Mapping[str, Any], system_idx: int) -> list[list[int]]:
    system = payload["pages"][0]["systems"][system_idx]
    return [[int(value) for value in staff["bbox"]] for staff in system.get("staves", [])]


def _compact_events(page: Mapping[str, Any], field: str) -> dict[tuple[int, int], int]:
    return {
        (int(item["system"]), int(item["measure"])): int(item["skip"])
        for item in page.get(field, [])
    }


def _delta(candidate: list[int], baseline: list[int]) -> list[int]:
    return [candidate[index] - baseline[index] for index in range(4)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    focused_path = (args.focused or _latest_focused()).resolve()
    manifest_path = args.manifest.resolve()
    focused = _load_json(focused_path)
    manifest = _load_json(manifest_path)
    matrix_pages = _load_matrix_pages(manifest)

    all_specs = {str(spec.page_id): spec for spec in build_page_specs()}
    specs = [all_specs[page_id] for page_id in DEGRADED_PAGE_IDS]

    reconstructed: dict[str, dict[str, Any]] = {}
    for short_name, label, factory in VARIANTS:
        bases, _images, supports, mapping_modes = _build_variant_inputs(
            specs=specs,
            matrix_pages=matrix_pages,
            label=label,
            pipeline_factory=factory,
        )
        reconstructed[short_name] = {
            str(spec.page_id): {
                "base": base,
                "support": support,
                "mapping_mode": mapping_mode,
            }
            for spec, base, support, mapping_mode in zip(specs, bases, supports, mapping_modes)
        }

    focused_variants = {
        "A": focused["variants"]["A_production"],
        "B": focused["variants"]["B_b377_mapping_guarded"],
        "C": focused["variants"]["C_latest_mapping_guarded"],
    }

    report: dict[str, Any] = {
        "focused_artifact": str(focused_path),
        "focused_artifact_git": focused.get("git"),
        "retained_manifest": str(manifest_path),
        "degraded_pages": {},
    }

    for page_id in DEGRADED_PAGE_IDS:
        scored_pages = {
            name: _page_by_id(variant, page_id) for name, variant in focused_variants.items()
        }
        keys: set[tuple[int, int]] = set()
        for page in scored_pages.values():
            keys.update(_event_keys(page))

        expected = {name: _compact_events(page, "expected") for name, page in scored_pages.items()}
        actual = {name: _compact_events(page, "actual") for name, page in scored_pages.items()}
        events: list[dict[str, Any]] = []

        for system_idx, measure_idx in sorted(keys):
            geometry: dict[str, Any] = {}
            for name in ("A", "B", "C"):
                item = reconstructed[name][page_id]
                base = item["base"]
                support = item["support"]
                primary = support["views"]["primary"]
                fallback = support["views"]["fallback"]
                alternate = support["views"]["implicit_start_alternate"]
                geometry[name] = {
                    "mapping_mode": item["mapping_mode"],
                    "expected_skip": expected[name].get((system_idx, measure_idx)),
                    "actual_skip": actual[name].get((system_idx, measure_idx)),
                    "base_measure_bbox": _bbox_at(base, system_idx, measure_idx),
                    "primary_measure_bbox": _bbox_at(primary, system_idx, measure_idx),
                    "alternate_measure_bbox": _bbox_at(alternate, system_idx, measure_idx),
                    "fallback_measure_bbox": _bbox_at(fallback, system_idx, measure_idx),
                    "primary_staff_bboxes": _staff_bboxes(primary, system_idx),
                    "fallback_staff_bboxes": _staff_bboxes(fallback, system_idx),
                }

            baseline = geometry["A"]
            for name in ("B", "C"):
                geometry[name]["delta_vs_A"] = {
                    "base_measure_bbox": _delta(
                        geometry[name]["base_measure_bbox"], baseline["base_measure_bbox"]
                    ),
                    "primary_measure_bbox": _delta(
                        geometry[name]["primary_measure_bbox"], baseline["primary_measure_bbox"]
                    ),
                    "alternate_measure_bbox": _delta(
                        geometry[name]["alternate_measure_bbox"], baseline["alternate_measure_bbox"]
                    ),
                    "fallback_measure_bbox": _delta(
                        geometry[name]["fallback_measure_bbox"], baseline["fallback_measure_bbox"]
                    ),
                }

            events.append(
                {
                    "system": system_idx,
                    "measure": measure_idx,
                    "variants": geometry,
                }
            )

        report["degraded_pages"][page_id] = {
            "scoring": {
                name: page["scoring"]["counts"] for name, page in scored_pages.items()
            },
            "events": events,
        }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
