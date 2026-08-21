#!/usr/bin/env python3
"""Diagnose the two real Issue #274 fresh-vs-retained topology residuals.

This is a post-hoc CPU-only diagnostic. It does not rerun HOMR, SR, detector,
CNN, MMR, or OCR. It first canonicalizes the v4 topology comparison by
discarding zero-measure systems, which production serialization places under
``empty_systems`` rather than ``systems``. It then reconstructs only the
remaining substantive pages while crossing retained/fresh barlines, staff
geometry, and connector semantic masks.

The output is intended to distinguish a verifier representation artifact from
an actual production-input difference without weakening the acceptance gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2

from src.common.connector_artifacts import (
    connector_mask_paths_for_numbering,
    describe_connector_artifacts,
)
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score
from tools.issue274.analyze_b_downstream_semantic_equivalence import (
    AB_DEFAULT,
    CANDIDATE_ROOT_DEFAULT,
    candidate_accepted_path,
    discover_a_staff_mask,
    load_boxes,
    to_workspace,
)


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


def canonical_signature(signature: Sequence[Any]) -> tuple[Any, ...]:
    if len(signature) != 5:
        return tuple(signature)
    staves = list(signature[1])
    measures = list(signature[2])
    numbers = list(signature[4])
    active = [
        (int(staff_count), int(measure_count), tuple(measure_numbers))
        for staff_count, measure_count, measure_numbers in zip(
            staves, measures, numbers, strict=True
        )
        if int(measure_count) > 0
    ]
    return (
        len(active),
        tuple(item[0] for item in active),
        tuple(item[1] for item in active),
        sum(item[1] for item in active),
        tuple(item[2] for item in active),
    )


def page_active_signature(page: Any) -> tuple[Any, ...]:
    active_systems = [system for system in page.systems if system.measures]
    return (
        len(active_systems),
        tuple(len(system.staves) for system in active_systems),
        tuple(len(system.measures) for system in active_systems),
        sum(len(system.measures) for system in active_systems),
        tuple(tuple(measure.number for measure in system.measures) for system in active_systems),
    )


def run_numbering(
    *,
    barline_path: Path,
    staff_mask: Path,
    image_path: Path,
    connector_paths: Mapping[str, Path] | None,
) -> tuple[Any, ...]:
    boxes = load_boxes(barline_path)
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    pipeline = MeasureNumberingPipeline()
    page = pipeline.process_page(
        [list(box) for box in boxes],
        staff_mask,
        (width, height),
        page_number=1,
        image=image,
        connector_mask_paths=connector_paths,
    )
    score = Score(pages=[page])
    pipeline.numberer.number_score(score, start_number=1)
    return page_active_signature(page)


def manifest_page(run_root: Path, score: str, page: str) -> Mapping[str, Any]:
    manifest_path = run_root / "runs" / score / "manifest.json"
    manifest = load_json(manifest_path)
    for row in manifest.get("pages", []):
        if isinstance(row, Mapping) and str(row.get("page_id")) == page:
            return row
    raise KeyError(f"Manifest page not found: {score}/{page}")


def path_map(paths: Mapping[str, Path] | None) -> dict[str, dict[str, Any]]:
    if not paths:
        return {}
    return {
        key: {
            "path": str(path),
            "exists": path.is_file(),
            "sha256": sha256(path),
        }
        for key, path in paths.items()
    }


def box_comparison(retained_path: Path, fresh_path: Path) -> dict[str, Any]:
    retained = load_boxes(retained_path)
    fresh = load_boxes(fresh_path)
    retained_set = set(retained)
    fresh_set = set(fresh)
    return {
        "retained_count": len(retained),
        "fresh_count": len(fresh),
        "exact_ordered": retained == fresh,
        "exact_set": retained_set == fresh_set,
        "retained_only_count": len(retained_set - fresh_set),
        "fresh_only_count": len(fresh_set - retained_set),
        "retained_only": sorted(retained_set - fresh_set),
        "fresh_only": sorted(fresh_set - retained_set),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--v4-summary", type=Path)
    parser.add_argument("--ab-report", type=Path, default=AB_DEFAULT)
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=CANDIDATE_ROOT_DEFAULT,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    run_root = to_workspace(args.run_root, workspace)
    v4_path = to_workspace(
        args.v4_summary or (run_root / "two_homr_full68_fresh_summary_v4.json"),
        workspace,
    )
    ab_path = to_workspace(args.ab_report, workspace)
    candidate_root = to_workspace(args.candidate_root, workspace)
    output = to_workspace(
        args.output or (run_root / "two_homr_full68_topology_residual_diagnosis.json"),
        workspace,
    )

    v4 = load_json(v4_path)
    changed = (v4.get("fresh_numbering_base") or {}).get("topology_changed_pages", [])
    representation_only: list[dict[str, str]] = []
    substantive: list[dict[str, Any]] = []
    for row in changed:
        if not isinstance(row, Mapping):
            continue
        fresh = canonical_signature(row["fresh_signature"])
        retained = canonical_signature(row["retained_b_signature"])
        identity = {
            "score": str(row["score"]),
            "page": str(row["page"]),
        }
        if fresh == retained:
            representation_only.append(identity)
        else:
            substantive.append(
                {
                    **identity,
                    "fresh_active_signature": fresh,
                    "retained_active_signature": retained,
                }
            )

    ab = load_json(ab_path)
    ab_records = {(str(row["score"]), str(row["page"])): row for row in ab["hybrid_ab"]["pages"]}

    residuals: list[dict[str, Any]] = []
    for item in substantive:
        score = item["score"]
        page = item["page"]
        record = ab_records[(score, page)]
        fresh_manifest = manifest_page(run_root, score, page)

        retained_a_path = to_workspace(str(record["a_path"]), workspace)
        retained_staff = discover_a_staff_mask(retained_a_path, page)
        fresh_staff = to_workspace(str(fresh_manifest["staff_mask"]), workspace)
        retained_barlines = candidate_accepted_path(candidate_root, score, page)
        fresh_barlines = to_workspace(str(fresh_manifest["barlines_json"]), workspace)
        image_path = to_workspace(str(fresh_manifest["image_path"]), workspace)

        retained_connectors = connector_mask_paths_for_numbering(retained_staff)
        fresh_connectors = connector_mask_paths_for_numbering(fresh_staff)

        matrix_specs = {
            "retained_all": (
                retained_barlines,
                retained_staff,
                retained_connectors,
            ),
            "fresh_barlines_only": (
                fresh_barlines,
                retained_staff,
                retained_connectors,
            ),
            "fresh_staff_only": (
                retained_barlines,
                fresh_staff,
                retained_connectors,
            ),
            "fresh_connectors_only": (
                retained_barlines,
                retained_staff,
                fresh_connectors,
            ),
            "fresh_staff_and_connectors": (
                retained_barlines,
                fresh_staff,
                fresh_connectors,
            ),
            "fresh_all": (
                fresh_barlines,
                fresh_staff,
                fresh_connectors,
            ),
        }
        matrix: dict[str, Any] = {}
        for name, (barlines, staff, connectors) in matrix_specs.items():
            signature = run_numbering(
                barline_path=barlines,
                staff_mask=staff,
                image_path=image_path,
                connector_paths=connectors,
            )
            matrix[name] = {
                "signature": signature,
                "equals_retained_v4": (signature == item["retained_active_signature"]),
                "equals_fresh_v4": (signature == item["fresh_active_signature"]),
            }

        retained_staff_sha = sha256(retained_staff)
        fresh_staff_sha = sha256(fresh_staff)
        residuals.append(
            {
                **item,
                "paths": {
                    "retained_barlines": str(retained_barlines),
                    "fresh_barlines": str(fresh_barlines),
                    "retained_staff": str(retained_staff),
                    "fresh_staff": str(fresh_staff),
                    "image": str(image_path),
                },
                "barlines": box_comparison(retained_barlines, fresh_barlines),
                "staff_masks": {
                    "retained_sha256": retained_staff_sha,
                    "fresh_sha256": fresh_staff_sha,
                    "same_sha256": retained_staff_sha == fresh_staff_sha,
                },
                "retained_connector_evidence": describe_connector_artifacts(retained_staff),
                "fresh_connector_evidence_manifest": fresh_manifest.get("connector_evidence"),
                "retained_connector_paths": path_map(retained_connectors),
                "fresh_connector_paths": path_map(fresh_connectors),
                "reconstruction_matrix": matrix,
            }
        )

    result = {
        "schema_version": "issue274.two_homr_full68_topology_residual.v1",
        "status": "completed",
        "run_root": str(run_root),
        "source_v4": str(v4_path),
        "original_changed_page_count": len(changed),
        "representation_only_page_count": len(representation_only),
        "representation_only_pages": representation_only,
        "substantive_page_count": len(substantive),
        "substantive_pages": substantive,
        "residuals": residuals,
        "interpretation": {
            "representation_only": (
                "retained audit counted zero-measure page.systems that "
                "production score_to_dict serializes under empty_systems"
            ),
            "substantive": (
                "active system/measure topology differs after removing "
                "zero-measure systems and requires causal input comparison"
            ),
        },
        "rerun": {
            "homr": False,
            "sr": False,
            "detector": False,
            "cnn": False,
            "mmr": False,
            "ocr": False,
            "numbering_cpu_pages": len(substantive),
        },
    }
    write_json(output, result)
    print(
        json.dumps(
            {
                "representation_only_page_count": len(representation_only),
                "substantive_page_count": len(substantive),
                "substantive_pages": substantive,
                "output": str(output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
