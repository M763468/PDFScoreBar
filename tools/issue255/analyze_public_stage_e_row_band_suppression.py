#!/usr/bin/env python3
"""Trace public Stage E false positives to row-band existing-box suppression.

This analysis is offline. It reads retained public and historical hybrid boxes
plus the prior false-positive source analysis. It does not run upstream
inference, consensus, probe generation, filtering, Issue53, or CNN scoring.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from src.pipeline.probe_detector.bands import cluster_by_y_distance
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box, write_json
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    _resolve_repo_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = (
    ROOT / "logs/issue255_stage_e_public_baseline/issue255_public_stage_e_01"
)
SOURCE_NAME = "public_stage_e_fp_source_analysis.json"
OUTPUT_NAME = "public_stage_e_row_band_suppression.json"
CLUSTER_MAX_DIST = 25.0
MIN_ROW_COUNT = 1
X_MERGE_TOL = 4.0


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _path(value: Any, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"Missing path for {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_file():
        raise FileNotFoundError(f"Missing artifact for {name}: {path}")
    return path


def _boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [normalize_box(box) for box in load_json_boxes(path)]


def _cluster_records(
    boxes: Sequence[tuple[int, int, int, int]],
) -> list[dict[str, Any]]:
    if not boxes:
        return []
    centers = np.array([(box[1] + box[3]) / 2.0 for box in boxes])
    clusters, _ = cluster_by_y_distance(
        centers,
        max_distance=CLUSTER_MAX_DIST,
        min_cluster_size=MIN_ROW_COUNT,
    )
    records = []
    for cluster_id, indices in clusters.items():
        members = [boxes[index] for index in indices]
        member_rows = sorted(
            (
                {
                    "bbox": list(box),
                    "x_center": (box[0] + box[2]) / 2.0,
                    "y_center": (box[1] + box[3]) / 2.0,
                }
                for box in members
            ),
            key=lambda row: (row["y_center"], row["x_center"]),
        )
        band = [
            int(np.median([box[1] for box in members])),
            int(np.median([box[3] for box in members])),
        ]
        records.append(
            {
                "cluster_id": int(cluster_id),
                "band": band,
                "member_count": len(member_rows),
                "y_center_min": min(row["y_center"] for row in member_rows),
                "y_center_max": max(row["y_center"] for row in member_rows),
                "members": member_rows,
            }
        )
    return records


def _find_cluster(
    records: Sequence[Mapping[str, Any]],
    band: Sequence[int | float] | None,
) -> dict[str, Any] | None:
    if band is None:
        return None
    target = [int(band[0]), int(band[1])]
    for record in records:
        if record.get("band") == target:
            return dict(record)
    target_center = sum(target) / 2.0
    if not records:
        return None
    nearest = min(
        records,
        key=lambda record: abs(
            target_center - (sum(record.get("band", [0, 0])) / 2.0)
        ),
    )
    return dict(nearest)


def _suppression_matches(
    boxes: Sequence[tuple[int, int, int, int]],
    band: Sequence[int | float] | None,
    x_center: float,
) -> list[dict[str, Any]]:
    if band is None:
        return []
    y1, y2 = float(band[0]), float(band[1])
    rows = []
    for box in boxes:
        bx = (box[0] + box[2]) / 2.0
        by = (box[1] + box[3]) / 2.0
        dx = abs(bx - x_center)
        if y1 <= by <= y2 and dx <= X_MERGE_TOL:
            rows.append(
                {
                    "bbox": list(box),
                    "x_center": bx,
                    "y_center": by,
                    "x_center_distance": dx,
                }
            )
    return sorted(rows, key=lambda row: (row["x_center_distance"], row["y_center"]))


def _classification(
    public_blockers: Sequence[Any], historical_blockers: Sequence[Any]
) -> str:
    if not public_blockers and historical_blockers:
        return "row_band_geometry_changes_existing_suppression"
    if public_blockers and historical_blockers:
        return "suppression_blocker_present_in_both"
    if public_blockers and not historical_blockers:
        return "suppression_blocker_only_in_public"
    return "no_existing_box_suppression_blocker"


def build_report(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    source_path = run_root / SOURCE_NAME
    source = _load(source_path)
    if not isinstance(source, Mapping) or source.get("status") != "completed":
        raise ValueError(f"Incomplete FP source analysis: {source_path}")
    source_pages = source.get("pages")
    if not isinstance(source_pages, Mapping):
        raise ValueError("FP source analysis lacks pages")

    pages: dict[str, Any] = {}
    for label, page in source_pages.items():
        if not isinstance(page, Mapping):
            continue
        paths = page.get("source_paths")
        false_positives = page.get("false_positives")
        if not isinstance(paths, Mapping) or not isinstance(false_positives, list):
            raise ValueError(f"Incomplete FP source page: {label}")

        public_path = _path(paths.get("public_hybrid"), f"{label}.public_hybrid")
        historical_path = _path(
            paths.get("historical_hybrid"), f"{label}.historical_hybrid"
        )
        public_boxes = _boxes(public_path)
        historical_boxes = _boxes(historical_path)
        public_clusters = _cluster_records(public_boxes)
        historical_clusters = _cluster_records(historical_boxes)

        rows = []
        for item in false_positives:
            if not isinstance(item, Mapping):
                continue
            bbox = normalize_box(item["prediction_bbox"])
            x_center = (bbox[0] + bbox[2]) / 2.0
            public_row = item.get("public_row_band")
            historical_row = item.get("historical_row_band")
            if not isinstance(public_row, Mapping) or not isinstance(
                historical_row, Mapping
            ):
                raise ValueError(f"FP row lacks band analysis: {label}/{bbox}")
            public_band = public_row.get("nearest_band")
            historical_band = historical_row.get("nearest_band")
            public_blockers = _suppression_matches(
                public_boxes, public_band, x_center
            )
            historical_blockers = _suppression_matches(
                historical_boxes, historical_band, x_center
            )
            rows.append(
                {
                    "prediction_bbox": list(bbox),
                    "cnn_score": item.get("cnn_score"),
                    "public_band": public_band,
                    "historical_band": historical_band,
                    "public_probe_ratio": public_row.get("probe_ratio_at_x"),
                    "historical_probe_ratio": historical_row.get(
                        "probe_ratio_at_x"
                    ),
                    "public_cluster": _find_cluster(public_clusters, public_band),
                    "historical_cluster": _find_cluster(
                        historical_clusters, historical_band
                    ),
                    "public_existing_suppression_matches": public_blockers,
                    "historical_existing_suppression_matches": historical_blockers,
                    "classification": _classification(
                        public_blockers, historical_blockers
                    ),
                }
            )

        pages[str(label)] = {
            "score": page.get("score"),
            "page": page.get("page"),
            "public_hybrid": str(public_path),
            "historical_hybrid": str(historical_path),
            "public_cluster_count": len(public_clusters),
            "historical_cluster_count": len(historical_clusters),
            "false_positive_count": len(rows),
            "false_positives": rows,
        }

    classifications = [
        row["classification"]
        for page in pages.values()
        for row in page["false_positives"]
    ]
    return {
        "schema_version": "issue255.public_stage_e_row_band_suppression.v1",
        "status": "completed",
        "analysis_only": True,
        "source_run": str(run_root),
        "source_analysis": str(source_path),
        "row_band_contract": {
            "cluster_max_dist": CLUSTER_MAX_DIST,
            "min_row_count": MIN_ROW_COUNT,
            "existing_box_x_merge_tolerance": X_MERGE_TOL,
            "existing_box_center_must_be_inside_band": True,
        },
        "pages": pages,
        "summary": {
            "false_positive_count": len(classifications),
            "classifications": {
                value: classifications.count(value)
                for value in sorted(set(classifications))
            },
        },
        "historical_artifacts_used_for_analysis_only": True,
        "next_gpu_run_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.run_root)
    output = args.output or args.run_root / OUTPUT_NAME
    write_json(output.resolve(), report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output.resolve()),
                "summary": report["summary"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
