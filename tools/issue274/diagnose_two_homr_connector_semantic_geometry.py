#!/usr/bin/env python3
"""Isolate connector-semantic geometry in the two Issue #274 topology residuals.

Post-hoc and CPU-only. No HOMR, SR, detector, CNN, MMR, OCR, or model inference
is rerun. The previous residual diagnostic established that accepted barlines,
A/original numbering staff masks, and connector symbol/brace-dot mask bytes are
identical between retained and fresh runs, while switching only the connector
artifact path changes topology.

Numbering derives connector-evidence staff ROIs from the current-HOMR staff mask
stored beside ``*_connector_symbols.png``. This diagnostic compares that hidden
path-dependent input and the resulting staff-pair evidence explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import cv2

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score
from tools.issue274.analyze_b_downstream_semantic_equivalence import load_boxes, to_workspace


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_staff_path(symbols_path: Path) -> Path:
    suffix = "_connector_symbols.png"
    if not symbols_path.name.endswith(suffix):
        raise ValueError(f"Unexpected connector symbols path: {symbols_path}")
    stem = symbols_path.name[: -len(suffix)]
    return symbols_path.with_name(f"{stem}_staff_mask.png")


def staff_bboxes(
    pipeline: MeasureNumberingPipeline,
    mask_path: Path,
    image_size: tuple[int, int],
) -> list[list[int]]:
    return [
        [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]
        for staff in pipeline.extractor.extract(mask_path, image_size)
    ]


def compact_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in payload.get("staff_pairs", []):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "staff_pair": row.get("staff_pair"),
                "left_connector_present": row.get("left_connector_present"),
                "symbols_vertical_open_density": row.get("symbols_vertical_open_density"),
                "brace_dot_vertical_open_density": row.get("brace_dot_vertical_open_density"),
                "symbols_roi": (row.get("symbols") or {}).get("roi_xyxy"),
                "brace_dot_roi": (row.get("brace_dot") or {}).get("roi_xyxy"),
            }
        )
    return {
        "source": payload.get("source"),
        "include_absent_pairs": payload.get("include_absent_pairs"),
        "staff_pairs": rows,
    }


def evidence_diff(a: Mapping[str, Any], b: Mapping[str, Any]) -> list[dict[str, Any]]:
    a_rows = {
        tuple(row.get("staff_pair", [])): row
        for row in a.get("staff_pairs", [])
        if isinstance(row, Mapping)
    }
    b_rows = {
        tuple(row.get("staff_pair", [])): row
        for row in b.get("staff_pairs", [])
        if isinstance(row, Mapping)
    }
    changed: list[dict[str, Any]] = []
    for pair in sorted(set(a_rows) | set(b_rows)):
        left = a_rows.get(pair)
        right = b_rows.get(pair)
        if left != right:
            changed.append(
                {
                    "staff_pair": list(pair),
                    "retained": left,
                    "fresh": right,
                }
            )
    return changed


def active_signature(page: Any) -> tuple[Any, ...]:
    systems = [system for system in page.systems if system.measures]
    return (
        len(systems),
        tuple(len(system.staves) for system in systems),
        tuple(len(system.measures) for system in systems),
        sum(len(system.measures) for system in systems),
        tuple(tuple(measure.number for measure in system.measures) for system in systems),
    )


def run_with_evidence(
    *,
    barlines_path: Path,
    geometry_staff_path: Path,
    image_path: Path,
    evidence: Mapping[str, Any],
) -> tuple[Any, ...]:
    boxes = load_boxes(barlines_path)
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    pipeline = MeasureNumberingPipeline()
    page = pipeline.process_page(
        [list(box) for box in boxes],
        geometry_staff_path,
        (width, height),
        page_number=1,
        image=image,
        connector_evidence=dict(evidence),
    )
    score = Score(pages=[page])
    pipeline.numberer.number_score(score, start_number=1)
    return active_signature(page)


def read_connector_paths(row: Mapping[str, Any], key: str) -> dict[str, Path]:
    payload = row.get(key)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Missing {key}")
    result: dict[str, Path] = {}
    for name in ("symbols", "brace_dot"):
        entry = payload.get(name)
        if not isinstance(entry, Mapping) or not entry.get("path"):
            raise ValueError(f"Missing {key}.{name}.path")
        result[name] = Path(str(entry["path"]))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--diagnosis", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    run_root = to_workspace(args.run_root, workspace)
    diagnosis_path = to_workspace(
        args.diagnosis or (run_root / "two_homr_full68_topology_residual_diagnosis.json"),
        workspace,
    )
    output = to_workspace(
        args.output or (run_root / "two_homr_connector_semantic_geometry_diagnosis.json"),
        workspace,
    )
    diagnosis = load_json(diagnosis_path)

    pages: list[dict[str, Any]] = []
    for row in diagnosis.get("residuals", []):
        if not isinstance(row, Mapping):
            continue
        paths = row.get("paths") or {}
        retained_barlines = to_workspace(str(paths["retained_barlines"]), workspace)
        retained_geometry_staff = to_workspace(str(paths["retained_staff"]), workspace)
        image_path = to_workspace(str(paths["image"]), workspace)
        retained_connectors = {
            key: to_workspace(path, workspace)
            for key, path in read_connector_paths(row, "retained_connector_paths").items()
        }
        fresh_connectors = {
            key: to_workspace(path, workspace)
            for key, path in read_connector_paths(row, "fresh_connector_paths").items()
        }
        retained_semantic_staff = semantic_staff_path(retained_connectors["symbols"])
        fresh_semantic_staff = semantic_staff_path(fresh_connectors["symbols"])

        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)
        height, width = image.shape[:2]
        image_size = (width, height)

        pipeline = MeasureNumberingPipeline()
        retained_semantic_bboxes = staff_bboxes(pipeline, retained_semantic_staff, image_size)
        fresh_semantic_bboxes = staff_bboxes(pipeline, fresh_semantic_staff, image_size)
        retained_semantic_staves = pipeline.extractor.extract(retained_semantic_staff, image_size)
        fresh_semantic_staves = pipeline.extractor.extract(fresh_semantic_staff, image_size)

        retained_evidence = pipeline.connector_extractor.extract_from_mask_maps(
            retained_semantic_staves,
            image_size,
            connector_mask_paths=retained_connectors,
        )
        fresh_evidence = pipeline.connector_extractor.extract_from_mask_maps(
            fresh_semantic_staves,
            image_size,
            connector_mask_paths=fresh_connectors,
        )
        fresh_masks_retained_geometry = pipeline.connector_extractor.extract_from_mask_maps(
            retained_semantic_staves,
            image_size,
            connector_mask_paths=fresh_connectors,
        )
        retained_masks_fresh_geometry = pipeline.connector_extractor.extract_from_mask_maps(
            fresh_semantic_staves,
            image_size,
            connector_mask_paths=retained_connectors,
        )

        signatures = {
            "retained_evidence": run_with_evidence(
                barlines_path=retained_barlines,
                geometry_staff_path=retained_geometry_staff,
                image_path=image_path,
                evidence=retained_evidence,
            ),
            "fresh_evidence": run_with_evidence(
                barlines_path=retained_barlines,
                geometry_staff_path=retained_geometry_staff,
                image_path=image_path,
                evidence=fresh_evidence,
            ),
            "fresh_masks_retained_semantic_geometry": run_with_evidence(
                barlines_path=retained_barlines,
                geometry_staff_path=retained_geometry_staff,
                image_path=image_path,
                evidence=fresh_masks_retained_geometry,
            ),
            "retained_masks_fresh_semantic_geometry": run_with_evidence(
                barlines_path=retained_barlines,
                geometry_staff_path=retained_geometry_staff,
                image_path=image_path,
                evidence=retained_masks_fresh_geometry,
            ),
        }

        pages.append(
            {
                "score": row.get("score"),
                "page": row.get("page"),
                "connector_masks_same": all(
                    sha256(retained_connectors[key]) == sha256(fresh_connectors[key])
                    for key in ("symbols", "brace_dot")
                ),
                "semantic_staff": {
                    "retained_path": str(retained_semantic_staff),
                    "fresh_path": str(fresh_semantic_staff),
                    "retained_sha256": sha256(retained_semantic_staff),
                    "fresh_sha256": sha256(fresh_semantic_staff),
                    "same_sha256": (
                        sha256(retained_semantic_staff) == sha256(fresh_semantic_staff)
                    ),
                    "retained_staff_count": len(retained_semantic_bboxes),
                    "fresh_staff_count": len(fresh_semantic_bboxes),
                    "retained_bboxes": retained_semantic_bboxes,
                    "fresh_bboxes": fresh_semantic_bboxes,
                    "same_bboxes": retained_semantic_bboxes == fresh_semantic_bboxes,
                },
                "evidence": {
                    "retained": compact_evidence(retained_evidence),
                    "fresh": compact_evidence(fresh_evidence),
                    "changed_pairs": evidence_diff(
                        compact_evidence(retained_evidence),
                        compact_evidence(fresh_evidence),
                    ),
                    "fresh_masks_retained_semantic_geometry": compact_evidence(
                        fresh_masks_retained_geometry
                    ),
                    "retained_masks_fresh_semantic_geometry": compact_evidence(
                        retained_masks_fresh_geometry
                    ),
                },
                "topology_signatures": signatures,
                "interpretation_guard": (
                    "If connector mask bytes are equal and swapping only semantic staff "
                    "geometry swaps evidence/topology, the residual is caused by the "
                    "path-derived current-HOMR staff geometry rather than barline or "
                    "connector-mask content."
                ),
            }
        )

    result = {
        "schema_version": "issue274.two_homr_connector_semantic_geometry.v1",
        "status": "completed",
        "source_diagnosis": str(diagnosis_path),
        "page_count": len(pages),
        "pages": pages,
        "rerun": {
            "homr": False,
            "sr": False,
            "detector": False,
            "cnn": False,
            "mmr": False,
            "ocr": False,
            "numbering_cpu_only": True,
        },
    }
    write_json(output, result)
    print(
        json.dumps(
            {
                "page_count": len(pages),
                "semantic_staff_same_count": sum(
                    int(bool(page["semantic_staff"]["same_sha256"])) for page in pages
                ),
                "output": str(output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
