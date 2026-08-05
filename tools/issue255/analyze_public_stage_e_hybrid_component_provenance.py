#!/usr/bin/env python3
"""Trace Stage E row-band divergence to retained hybrid input components.

This analysis is offline. It reads retained public and historical baseline, SR,
OMR-DLN, and hybrid box artifacts. Historical artifacts are comparison inputs
only and are never connected to detector execution.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box, target_metrics, write_json
from tools.issue255.inspect_stage_e_historical_upstream import (
    _inventory,
    _single_box_record,
)
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    _resolve_repo_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "logs/issue255_stage_e_public_baseline/issue255_public_stage_e_01"
DEFAULT_HISTORICAL_COMPARISON = (
    ROOT
    / "logs/issue255_stage_e_focused/issue255_stage_e_focused_03"
    / "stage_e_historical_input_comparison.json"
)
PUBLIC_REPORT_NAME = "public_baseline_stage_e_reconstruction_report.json"
ROW_BAND_REPORT_NAME = "public_stage_e_row_band_suppression.json"
OUTPUT_NAME = "public_stage_e_hybrid_component_provenance.json"
STAGES = ("baseline", "sr", "omr", "hybrid")
PUBLIC_ARTIFACT_KEYS = {
    "baseline": "public_baseline",
    "sr": "current_sr",
    "omr": "current_omr",
    "hybrid": "public_hybrid",
}
ACCEPTED_IOU = 0.5


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _path(value: Any, name: str) -> Path:
    if isinstance(value, Mapping):
        value = value.get("path")
    if not isinstance(value, (str, Path)):
        raise ValueError(f"Missing path for {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_file():
        raise FileNotFoundError(f"Missing artifact for {name}: {path}")
    return path


def _directory(value: Any, name: str) -> Path:
    if isinstance(value, Mapping):
        value = value.get("path")
    if not isinstance(value, (str, Path)):
        raise ValueError(f"Missing directory for {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_dir():
        raise FileNotFoundError(f"Missing directory for {name}: {path}")
    return path


def _boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [normalize_box(box) for box in load_json_boxes(path)]


def _component_comparison(
    historical: Sequence[tuple[int, int, int, int]],
    public: Sequence[tuple[int, int, int, int]],
) -> dict[str, Any]:
    historical_set = set(historical)
    public_set = set(public)
    historical_only = sorted(historical_set - public_set)
    public_only = sorted(public_set - historical_set)
    return {
        "historical_count": len(historical_set),
        "public_count": len(public_set),
        "exact_common_count": len(historical_set & public_set),
        "historical_only_count": len(historical_only),
        "public_only_count": len(public_only),
        "exact_match": not historical_only and not public_only,
    }


def _stage_match(
    reference: Sequence[int | float],
    boxes: Sequence[tuple[int, int, int, int]],
) -> dict[str, Any]:
    metrics = target_metrics(normalize_box(reference), boxes, accepted_iou=ACCEPTED_IOU)
    best = metrics.get("best")
    return {
        "accepted": bool(metrics.get("accepted")),
        "best": dict(best) if isinstance(best, Mapping) else None,
    }


def _stage_provenance(
    bbox: Sequence[int | float],
    components: Mapping[str, Sequence[tuple[int, int, int, int]]],
) -> dict[str, Any]:
    return {stage: _stage_match(bbox, components[stage]) for stage in STAGES}


def _unique_cluster_members(
    false_positives: Sequence[Mapping[str, Any]], side: str
) -> list[tuple[int, int, int, int]]:
    key = f"{side}_cluster"
    result: set[tuple[int, int, int, int]] = set()
    for row in false_positives:
        cluster = row.get(key)
        members = cluster.get("members") if isinstance(cluster, Mapping) else None
        if not isinstance(members, list):
            continue
        for member in members:
            bbox = member.get("bbox") if isinstance(member, Mapping) else None
            if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)):
                result.add(normalize_box(bbox))
    return sorted(result)


def _unique_blockers(
    false_positives: Sequence[Mapping[str, Any]], side: str
) -> list[tuple[int, int, int, int]]:
    key = f"{side}_existing_suppression_matches"
    result: set[tuple[int, int, int, int]] = set()
    for row in false_positives:
        blockers = row.get(key)
        if not isinstance(blockers, list):
            continue
        for blocker in blockers:
            bbox = blocker.get("bbox") if isinstance(blocker, Mapping) else None
            if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)):
                result.add(normalize_box(bbox))
    return sorted(result)


def _historical_components(
    record: Mapping[str, Any], label: str
) -> tuple[dict[str, Path], dict[str, list[tuple[int, int, int, int]]]]:
    run_dir = _directory(record.get("run_dir"), f"{label}.historical_run_dir")
    rows = _inventory(run_dir)
    paths: dict[str, Path] = {}
    components: dict[str, list[tuple[int, int, int, int]]] = {}
    for stage in STAGES:
        stage_record = _single_box_record(rows, stage)
        if stage_record is None:
            raise ValueError(f"Expected one historical {stage} artifact for {label}: {run_dir}")
        path = _path(stage_record.get("path"), f"{label}.historical_{stage}")
        paths[stage] = path
        components[stage] = _boxes(path)
    return paths, components


def _public_components(
    artifacts: Mapping[str, Any], label: str
) -> tuple[dict[str, Path], dict[str, list[tuple[int, int, int, int]]]]:
    paths: dict[str, Path] = {}
    components: dict[str, list[tuple[int, int, int, int]]] = {}
    for stage, artifact_key in PUBLIC_ARTIFACT_KEYS.items():
        path = _path(artifacts.get(artifact_key), f"{label}.public_{stage}")
        paths[stage] = path
        components[stage] = _boxes(path)
    return paths, components


def _member_rows(
    boxes: Sequence[tuple[int, int, int, int]],
    own_components: Mapping[str, Sequence[tuple[int, int, int, int]]],
    counterpart_components: Mapping[str, Sequence[tuple[int, int, int, int]]],
) -> list[dict[str, Any]]:
    return [
        {
            "bbox": list(box),
            "own_component_matches": _stage_provenance(box, own_components),
            "counterpart_component_matches": _stage_provenance(box, counterpart_components),
        }
        for box in boxes
    ]


def build_report(run_root: Path, historical_comparison: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    public_path = run_root / PUBLIC_REPORT_NAME
    row_band_path = run_root / ROW_BAND_REPORT_NAME
    public = _load(public_path)
    row_band = _load(row_band_path)
    historical = _load(historical_comparison.resolve())
    for name, payload in (
        ("public Stage E report", public),
        ("row-band suppression report", row_band),
        ("historical comparison", historical),
    ):
        if not isinstance(payload, Mapping) or payload.get("status") != "completed":
            raise ValueError(f"Incomplete {name}")

    public_pages = public.get("pages")
    row_pages = row_band.get("pages")
    historical_pages = historical.get("pages")
    if not all(isinstance(value, Mapping) for value in (public_pages, row_pages, historical_pages)):
        raise ValueError("One or more source reports lack pages")

    pages: dict[str, Any] = {}
    for label, row_page in row_pages.items():
        if not isinstance(row_page, Mapping):
            continue
        public_page = public_pages.get(label)
        historical_page = historical_pages.get(label)
        if not isinstance(public_page, Mapping) or not isinstance(historical_page, Mapping):
            raise ValueError(f"Missing source page: {label}")
        artifacts = public_page.get("artifacts")
        historical_record = historical_page.get("historical_inventory_record")
        false_positives = row_page.get("false_positives")
        if not isinstance(artifacts, Mapping) or not isinstance(historical_record, Mapping):
            raise ValueError(f"Missing component metadata: {label}")
        if not isinstance(false_positives, list):
            raise ValueError(f"Invalid false-positive rows: {label}")

        historical_paths, historical_components = _historical_components(
            historical_record, str(label)
        )
        public_paths, public_components = _public_components(artifacts, str(label))
        comparisons = {
            stage: _component_comparison(historical_components[stage], public_components[stage])
            for stage in STAGES
        }
        differing_components = [stage for stage in STAGES if not comparisons[stage]["exact_match"]]
        public_members = _unique_cluster_members(false_positives, "public")
        historical_members = _unique_cluster_members(false_positives, "historical")
        public_blockers = _unique_blockers(false_positives, "public")
        historical_blockers = _unique_blockers(false_positives, "historical")

        pages[str(label)] = {
            "score": row_page.get("score"),
            "page": row_page.get("page"),
            "false_positive_count": row_page.get("false_positive_count"),
            "component_paths": {
                "historical": {stage: str(path) for stage, path in historical_paths.items()},
                "public": {stage: str(path) for stage, path in public_paths.items()},
            },
            "component_comparisons": comparisons,
            "differing_components": differing_components,
            "first_persisted_divergence": (
                differing_components[0] if differing_components else None
            ),
            "row_cluster_members": {
                "public": _member_rows(public_members, public_components, historical_components),
                "historical": _member_rows(
                    historical_members, historical_components, public_components
                ),
            },
            "suppression_blockers": {
                "public_band_matches": _member_rows(
                    public_blockers, public_components, historical_components
                ),
                "historical_band_matches": _member_rows(
                    historical_blockers, historical_components, public_components
                ),
            },
        }

    return {
        "schema_version": "issue255.public_stage_e_hybrid_component_provenance.v1",
        "status": "completed",
        "analysis_only": True,
        "source_run": str(run_root),
        "source_public_report": str(public_path),
        "source_row_band_report": str(row_band_path),
        "source_historical_comparison": str(historical_comparison.resolve()),
        "historical_artifacts_used_for_analysis_only": True,
        "accepted_iou": ACCEPTED_IOU,
        "pages": pages,
        "next_gpu_run_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument(
        "--historical-comparison",
        type=Path,
        default=DEFAULT_HISTORICAL_COMPARISON,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.run_root, args.historical_comparison)
    output = args.output or args.run_root / OUTPUT_NAME
    write_json(output.resolve(), report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output.resolve()),
                "pages": {
                    label: {
                        "differing_components": page["differing_components"],
                        "first_persisted_divergence": page["first_persisted_divergence"],
                    }
                    for label, page in report["pages"].items()
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
