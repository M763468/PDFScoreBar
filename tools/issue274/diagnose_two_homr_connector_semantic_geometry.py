#!/usr/bin/env python3
"""Inspect connector-semantic geometry for Issue #274 topology residuals.

Post-hoc and CPU-only. No HOMR, SR, detector, CNN, MMR, OCR, or model inference
is rerun.

Important production contract: connector-mask paths imply a sibling current-HOMR
``*_staff_mask.png``, but ``MeasureNumberingPipeline._connector_evidence_staves``
uses that semantic geometry only when its extracted staff count matches the
A/Proxy numbering geometry. Otherwise production falls back to the A/Proxy staves.
This diagnostic reports that resolution explicitly. The older v1 diagnostic
bypassed this fallback in its cross matrix and must not be used as production
replay evidence.
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


def staff_bboxes(staves: list[Any]) -> list[list[int]]:
    return [[staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2] for staff in staves]


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


def resolve_production_evidence(
    *,
    pipeline: MeasureNumberingPipeline,
    geometry_staves: list[Any],
    geometry_staff_path: Path,
    image_size: tuple[int, int],
    connector_paths: Mapping[str, Path],
) -> tuple[list[Any], dict[str, Any], str]:
    resolved_staves = pipeline._connector_evidence_staves(  # noqa: SLF001
        geometry_staves,
        geometry_staff_path,
        image_size,
        connector_paths,
    )
    mode = "a_proxy_fallback" if resolved_staves is geometry_staves else "current_homr_semantic"
    evidence = pipeline.connector_extractor.extract_from_mask_maps(
        resolved_staves,
        image_size,
        connector_mask_paths=connector_paths,
    )
    return resolved_staves, evidence, mode


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
        args.output or (run_root / "two_homr_connector_semantic_geometry_diagnosis_v2.json"),
        workspace,
    )
    diagnosis = load_json(diagnosis_path)

    pages: list[dict[str, Any]] = []
    for row in diagnosis.get("residuals", []):
        if not isinstance(row, Mapping):
            continue
        paths = row.get("paths") or {}
        retained_barlines = to_workspace(str(paths["retained_barlines"]), workspace)
        geometry_staff_path = to_workspace(str(paths["retained_staff"]), workspace)
        image_path = to_workspace(str(paths["image"]), workspace)
        retained_connectors = {
            key: to_workspace(path, workspace)
            for key, path in read_connector_paths(row, "retained_connector_paths").items()
        }
        fresh_connectors = {
            key: to_workspace(path, workspace)
            for key, path in read_connector_paths(row, "fresh_connector_paths").items()
        }
        retained_semantic_path = semantic_staff_path(retained_connectors["symbols"])
        fresh_semantic_path = semantic_staff_path(fresh_connectors["symbols"])

        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)
        height, width = image.shape[:2]
        image_size = (width, height)

        pipeline = MeasureNumberingPipeline()
        geometry_staves = pipeline.extractor.extract(geometry_staff_path, image_size)
        retained_semantic_staves = pipeline.extractor.extract(retained_semantic_path, image_size)
        fresh_semantic_staves = pipeline.extractor.extract(fresh_semantic_path, image_size)

        retained_resolved, retained_evidence, retained_mode = resolve_production_evidence(
            pipeline=pipeline,
            geometry_staves=geometry_staves,
            geometry_staff_path=geometry_staff_path,
            image_size=image_size,
            connector_paths=retained_connectors,
        )
        fresh_resolved, fresh_evidence, fresh_mode = resolve_production_evidence(
            pipeline=pipeline,
            geometry_staves=geometry_staves,
            geometry_staff_path=geometry_staff_path,
            image_size=image_size,
            connector_paths=fresh_connectors,
        )

        retained_compact = compact_evidence(retained_evidence)
        fresh_compact = compact_evidence(fresh_evidence)
        pages.append(
            {
                "score": row.get("score"),
                "page": row.get("page"),
                "connector_masks_same": all(
                    sha256(retained_connectors[key]) == sha256(fresh_connectors[key])
                    for key in ("symbols", "brace_dot")
                ),
                "authoritative_geometry": {
                    "path": str(geometry_staff_path),
                    "staff_count": len(geometry_staves),
                    "bboxes": staff_bboxes(geometry_staves),
                },
                "semantic_staff": {
                    "retained": {
                        "path": str(retained_semantic_path),
                        "sha256": sha256(retained_semantic_path),
                        "staff_count": len(retained_semantic_staves),
                        "bboxes": staff_bboxes(retained_semantic_staves),
                    },
                    "fresh": {
                        "path": str(fresh_semantic_path),
                        "sha256": sha256(fresh_semantic_path),
                        "staff_count": len(fresh_semantic_staves),
                        "bboxes": staff_bboxes(fresh_semantic_staves),
                    },
                },
                "production_resolution": {
                    "retained_mode": retained_mode,
                    "fresh_mode": fresh_mode,
                    "retained_resolved_staff_count": len(retained_resolved),
                    "fresh_resolved_staff_count": len(fresh_resolved),
                    "retained_evidence": retained_compact,
                    "fresh_evidence": fresh_compact,
                    "changed_pairs": evidence_diff(retained_compact, fresh_compact),
                },
                "topology_signatures": {
                    "retained_production_resolution": run_with_evidence(
                        barlines_path=retained_barlines,
                        geometry_staff_path=geometry_staff_path,
                        image_path=image_path,
                        evidence=retained_evidence,
                    ),
                    "fresh_production_resolution": run_with_evidence(
                        barlines_path=retained_barlines,
                        geometry_staff_path=geometry_staff_path,
                        image_path=image_path,
                        evidence=fresh_evidence,
                    ),
                },
            }
        )

    result = {
        "schema_version": "issue274.two_homr_connector_semantic_geometry.v2",
        "status": "completed",
        "source_diagnosis": str(diagnosis_path),
        "page_count": len(pages),
        "pages": pages,
        "contract": {
            "production_staff_count_fallback_replayed": True,
            "v1_cross_matrix_superseded": True,
            "rerun_inference": False,
            "rerun_numbering_cpu_only": True,
        },
    }
    write_json(output, result)
    print(
        json.dumps(
            {
                "page_count": len(pages),
                "resolution_modes": [
                    {
                        "score": page["score"],
                        "page": page["page"],
                        "retained": page["production_resolution"]["retained_mode"],
                        "fresh": page["production_resolution"]["fresh_mode"],
                    }
                    for page in pages
                ],
                "output": str(output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
