#!/usr/bin/env python3
"""Audit retained Issue #294 full68 outputs without rerunning expensive inference.

This host-only tool answers three remaining questions after ``issue294_full68_refresh_02``:

1. Do exact-source B detector-material coordinate deltas survive hybrid consensus?
2. On A/B ``count_only`` pages, do internal measure x-boundaries stay aligned?
3. What concrete staff bboxes explain the remaining page_052 membership difference?

It does not run detector, HOMR, SR, OMR, CNN, OCR, or MMR.  For page_052 only it
reconstructs MeasureNumberingPipeline from already-retained final barlines, staff
masks, and connector masks so staff component/system membership can be inspected.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _resolve_project_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.exists():
        return raw
    if not raw.is_absolute():
        candidate = PROJECT_ROOT / raw
        if candidate.exists():
            return candidate
    parts = raw.parts
    if "ws_PDFScoreBar" in parts:
        index = parts.index("ws_PDFScoreBar")
        candidate = PROJECT_ROOT.joinpath(*parts[index + 1 :])
        if candidate.exists():
            return candidate
    if "/workspace/" in str(raw):
        suffix = str(raw).split("/workspace/", 1)[1]
        candidate = PROJECT_ROOT / suffix
        if candidate.exists():
            return candidate
    raise FileNotFoundError(raw)


def _boxes(path: str | Path) -> list[tuple[int, int, int, int]]:
    return [tuple(int(v) for v in box) for box in load_json_boxes(_resolve_project_path(path))]


def _normalise_boxes(value: Any) -> list[tuple[int, int, int, int]]:
    if isinstance(value, (str, Path)):
        return _boxes(value)
    if not isinstance(value, list):
        raise ValueError(f"Expected barline list/path, got {type(value).__name__}")
    boxes: list[tuple[int, int, int, int]] = []
    for item in value:
        if isinstance(item, Mapping):
            raw = item.get("orig_bbox", item.get("bbox"))
        else:
            raw = item
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            raise ValueError(f"Malformed barline box: {item!r}")
        boxes.append(tuple(int(v) for v in raw))
    return boxes


def _box_delta(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> int:
    return max(abs(a - b) for a, b in zip(left, right))


def _nearest(
    box: tuple[int, int, int, int], candidates: list[tuple[int, int, int, int]]
) -> dict[str, Any]:
    if not candidates:
        return {"box": None, "max_abs_delta": None}
    other = min(candidates, key=lambda candidate: _box_delta(box, candidate))
    return {"box": list(other), "max_abs_delta": _box_delta(box, other)}


def _multiset_difference(
    left: list[tuple[int, int, int, int]],
    right: list[tuple[int, int, int, int]],
) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int, int, int]]]:
    left_counter = Counter(left)
    right_counter = Counter(right)
    return list((left_counter - right_counter).elements()), list(
        (right_counter - left_counter).elements()
    )


def _report_page_key(page: Mapping[str, Any]) -> tuple[str, str]:
    image = Path(str(page["image"]))
    return image.parent.name, image.stem


def _load_matrix_pages(manifest: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    pages: dict[tuple[str, str], Mapping[str, Any]] = {}
    chunks = manifest.get("completed_chunks")
    if not isinstance(chunks, list):
        raise ValueError("Full68 manifest lacks completed_chunks")
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            raise ValueError("Malformed completed chunk")
        report_path = _resolve_project_path(str(chunk["matrix_report"]))
        report = _load_json(report_path)
        report_pages = report.get("pages") if isinstance(report, Mapping) else None
        if not isinstance(report_pages, list):
            raise ValueError(f"Matrix report lacks pages: {report_path}")
        for page in report_pages:
            if not isinstance(page, Mapping):
                raise ValueError(f"Malformed matrix page: {report_path}")
            key = _report_page_key(page)
            if key in pages:
                raise RuntimeError(f"Duplicate matrix page: {key}")
            pages[key] = page
    if len(pages) != 68:
        raise RuntimeError(f"Expected 68 matrix pages, got {len(pages)}")
    return pages


def _manifest_page_by_id(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = manifest.get("pages")
    if not isinstance(raw, list) or len(raw) != 68:
        raise ValueError("Full68 manifest lacks 68 page summaries")
    return {str(item["global_page_id"]): item for item in raw if isinstance(item, Mapping)}


def _matrix_for_summary(
    summary: Mapping[str, Any], matrix_pages: Mapping[tuple[str, str], Mapping[str, Any]]
) -> Mapping[str, Any]:
    key = (str(summary["score"]), str(summary["page_name"]))
    page = matrix_pages.get(key)
    if page is None:
        raise RuntimeError(f"Matrix page not found: {key}")
    return page


def _adapter_hybrid_audit(page: Mapping[str, Any]) -> dict[str, Any]:
    native_b = page["modes"]["candidate_native_geometry"]["variants"]["B_b377"]
    full_boxes = _boxes(str(native_b["baseline_detection"]))
    adapter_boxes = _boxes(str(page["B_material"]["artifacts"]["detections"]))
    full_only, adapter_only = _multiset_difference(full_boxes, adapter_boxes)

    support = _load_json(_resolve_project_path(str(page["fixed_inputs"]["support_result"])))
    current_boxes = _boxes(str(support["current_sr_detection"]))
    omr_boxes = _boxes(str(support["current_omr"]))

    adapter_hybrid = [
        tuple(int(v) for v in box)
        for box in apply_hybrid_consensus_filter(
            baseline_boxes=[list(box) for box in adapter_boxes],
            sr_boxes=[list(box) for box in current_boxes],
            omr_boxes=[list(box) for box in omr_boxes],
        )
    ]
    retained_hybrid = _boxes(str(native_b["hybrid_path"]))
    hybrid_full_only, hybrid_adapter_only = _multiset_difference(retained_hybrid, adapter_hybrid)
    final_boxes = _normalise_boxes(native_b["final_barlines"])

    return {
        "full_count": len(full_boxes),
        "adapter_count": len(adapter_boxes),
        "raw_multiset_exact": Counter(full_boxes) == Counter(adapter_boxes),
        "raw_full_only": [list(box) for box in full_only],
        "raw_adapter_only": [list(box) for box in adapter_only],
        "retained_full_hybrid_count": len(retained_hybrid),
        "recomputed_adapter_hybrid_count": len(adapter_hybrid),
        "hybrid_multiset_exact": Counter(retained_hybrid) == Counter(adapter_hybrid),
        "hybrid_full_only": [
            {"box": list(box), "nearest_final": _nearest(box, final_boxes)}
            for box in hybrid_full_only
        ],
        "hybrid_adapter_only": [list(box) for box in hybrid_adapter_only],
    }


def _nonempty_systems(variant: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    pages = variant["numbering"]["pages"]
    systems = [system for page in pages for system in page["systems"]]
    return [system for system in systems if int(system["measure_count"]) > 0]


def _internal_x_boundaries(variant: Mapping[str, Any]) -> list[list[int]]:
    systems: list[list[int]] = []
    for system in _nonempty_systems(variant):
        bboxes = system["measure_bboxes"]
        # x2 of every measure except the final measure is an internal logical
        # boundary.  Excluding first x1 and final x2 avoids staff-derived ghost
        # system-start/end geometry.
        systems.append([int(bbox[2]) for bbox in bboxes[:-1]])
    return systems


def _internal_x_compare(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    left = _internal_x_boundaries(a)
    right = _internal_x_boundaries(b)
    if [len(item) for item in left] != [len(item) for item in right]:
        return {
            "comparable": False,
            "A_counts": [len(item) for item in left],
            "B_counts": [len(item) for item in right],
        }
    deltas: list[int] = []
    changed: list[dict[str, int]] = []
    for system_index, (left_system, right_system) in enumerate(zip(left, right)):
        for boundary_index, (x_a, x_b) in enumerate(zip(left_system, right_system)):
            delta = int(x_b - x_a)
            deltas.append(abs(delta))
            if delta:
                changed.append(
                    {
                        "system": system_index,
                        "boundary": boundary_index,
                        "A_x": x_a,
                        "B_x": x_b,
                        "delta": delta,
                    }
                )
    return {
        "comparable": True,
        "boundary_count": len(deltas),
        "exact": not changed,
        "changed_boundary_count": len(changed),
        "max_abs_delta": max(deltas, default=0),
        "changed": changed,
    }


def _score_detail(
    *,
    page: Mapping[str, Any],
    label: str,
) -> dict[str, Any]:
    variant = page["modes"]["candidate_native_geometry"]["variants"][label]
    image_path = _resolve_project_path(str(page["image"]))
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    support = _load_json(_resolve_project_path(str(page["fixed_inputs"]["support_result"])))
    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    score = MeasureNumberingPipeline().run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": (width, height),
                "page_number": 1,
                "connector_mask_paths": {
                    "symbols": str(_resolve_project_path(str(support["connector_symbols"]))),
                    "brace_dot": str(_resolve_project_path(str(support["connector_brace_dot"]))),
                },
            }
        ]
    )
    page_score = score.pages[0]
    systems: list[dict[str, Any]] = []
    for system_index, system in enumerate(page_score.systems):
        systems.append(
            {
                "index": system_index,
                "staff_count": len(system.staves),
                "staff_bboxes": [
                    [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]
                    for staff in system.staves
                ],
                "measure_numbers": [measure.number for measure in system.measures],
                "measure_bboxes": [
                    [measure.bbox.x1, measure.bbox.y1, measure.bbox.x2, measure.bbox.y2]
                    for measure in system.measures
                ],
            }
        )
    return {
        "label": label,
        "staff_mask": str(staff_mask),
        "systems": systems,
    }


def _system_containing(detail: Mapping[str, Any], number: int) -> Mapping[str, Any] | None:
    systems = detail.get("systems")
    if not isinstance(systems, list):
        return None
    for system in systems:
        if isinstance(system, Mapping) and number in system.get("measure_numbers", []):
            return system
    return None


def run(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")
    matrix_pages = _load_matrix_pages(manifest)
    summaries = _manifest_page_by_id(manifest)

    adapter: dict[str, Any] = {}
    count_only: dict[str, Any] = {}
    for page_id, summary in summaries.items():
        matrix_page = _matrix_for_summary(summary, matrix_pages)
        fidelity = summary["B_full_vs_detector_material"]
        if not bool(fidelity["boxes_exact"]):
            adapter[page_id] = _adapter_hybrid_audit(matrix_page)

        comparison = summary["candidate_native_geometry"]["B_vs_A"]
        if (
            bool(comparison["total_measures_equal"])
            and bool(comparison["system_measure_topology_equal"])
            and bool(comparison["numbering_equal"])
            and not bool(comparison["final_barline_count_equal"])
        ):
            native = matrix_page["modes"]["candidate_native_geometry"]["variants"]
            count_only[page_id] = _internal_x_compare(native["A_pinned"], native["B_b377"])

    page_052_summary = summaries.get("page_052")
    if page_052_summary is None:
        raise RuntimeError("Full68 manifest lacks page_052")
    page_052 = _matrix_for_summary(page_052_summary, matrix_pages)
    page_052_details = {
        label: _score_detail(page=page_052, label=label)
        for label in ("A_pinned", "B_b377", "C_latest")
    }
    page_052_target = {
        label: _system_containing(detail, 11) for label, detail in page_052_details.items()
    }

    payload = {
        "schema_version": "issue294.full68_retained_semantic_audit.v1",
        "status": "completed",
        "full68_manifest": str(manifest_path.resolve()),
        "execution_contract": {
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "cnn_reexecuted": False,
            "ocr_reexecuted": False,
            "mmr_reexecuted": False,
            "page_052_numbering_reconstructed_from_retained_inputs": True,
        },
        "B_full_vs_adapter_hybrid": adapter,
        "count_only_internal_x_boundaries": {
            "page_count": len(count_only),
            "pages": count_only,
            "all_comparable": all(bool(item.get("comparable")) for item in count_only.values()),
            "max_abs_delta": max(
                (int(item.get("max_abs_delta", 0)) for item in count_only.values()),
                default=0,
            ),
        },
        "page_052": {
            "target_measure": 11,
            "target_systems": page_052_target,
            "all_systems": page_052_details,
        },
    }
    _write_json(output_path, payload)
    print(
        json.dumps(
            {
                "status": "completed",
                "adapter_hybrid": {
                    page_id: {
                        "hybrid_multiset_exact": item["hybrid_multiset_exact"],
                        "hybrid_full_only": len(item["hybrid_full_only"]),
                        "hybrid_adapter_only": len(item["hybrid_adapter_only"]),
                    }
                    for page_id, item in adapter.items()
                },
                "count_only": {
                    "pages": len(count_only),
                    "all_comparable": payload["count_only_internal_x_boundaries"]["all_comparable"],
                    "max_abs_delta": payload["count_only_internal_x_boundaries"]["max_abs_delta"],
                },
                "page_052_target_systems": page_052_target,
                "report": str(output_path.resolve()),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full68-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.full68_manifest, args.output)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
