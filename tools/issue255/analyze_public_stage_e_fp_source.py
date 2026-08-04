#!/usr/bin/env python3
"""Trace public-baseline Stage E false positives to historical source bands.

This analysis is offline. It reads retained public/historical hybrid predictions,
dense candidates, filters, and the original image. It does not execute HOMR,
SR, OMR-DLN, consensus, probe generation, filtering, Issue53, or CNN inference.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box, target_metrics, write_json
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
RESIDUAL_REPORT_NAME = "public_baseline_stage_e_residuals.json"
OUTPUT_NAME = "public_stage_e_fp_source_analysis.json"
CLUSTER_MAX_DIST = 25.0
MIN_ROW_COUNT = 1
INK_THRESHOLD = 240
MIN_RATIO = 0.6
PROBE_WIDTH = 4


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


def _boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [normalize_box(box) for box in load_json_boxes(path)]


def _exact(reference: Sequence[int | float], boxes: Sequence[Any]) -> bool:
    box = normalize_box(reference)
    return box in {normalize_box(candidate) for candidate in boxes}


def _nearest(reference: Sequence[int | float], boxes: Sequence[Any]) -> dict[str, Any] | None:
    metrics = target_metrics(normalize_box(reference), boxes, accepted_iou=0.5)
    best = metrics.get("best")
    return dict(best) if isinstance(best, Mapping) else None


def _bands(boxes: Sequence[tuple[int, int, int, int]]) -> list[tuple[int, int]]:
    stats = build_row_stats(
        boxes,
        cluster_max_dist=CLUSTER_MAX_DIST,
        min_row_count=MIN_ROW_COUNT,
    )
    return [(int(stat["top"]), int(stat["bottom"])) for stat in stats]


def _band_relation(bbox: Sequence[int | float], bands: Sequence[tuple[int, int]]) -> dict[str, Any]:
    box = normalize_box(bbox)
    cy = (box[1] + box[3]) / 2.0
    containing = [band for band in bands if band[0] <= cy <= band[1]]
    nearest = None
    if bands:
        nearest = min(
            bands,
            key=lambda band: abs(cy - ((band[0] + band[1]) / 2.0)),
        )
    return {
        "candidate_y_center": cy,
        "containing_bands": [list(band) for band in containing],
        "nearest_band": list(nearest) if nearest is not None else None,
    }


def _probe_ratio(
    image: np.ndarray,
    band: Sequence[int] | None,
    bbox: Sequence[int | float],
) -> float | None:
    if band is None:
        return None
    y1, y2 = int(band[0]), int(band[1])
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = (gray < INK_THRESHOLD).astype(np.uint8)
    y1 = max(0, min(y1, ink.shape[0] - 1))
    y2 = max(0, min(y2, ink.shape[0] - 1))
    if y2 < y1:
        return None
    col_sums = ink[y1 : y2 + 1, :].sum(axis=0)
    stripe_sums = np.convolve(
        col_sums,
        np.ones(PROBE_WIDTH, dtype=np.int32),
        mode="same",
    )
    box = normalize_box(bbox)
    x = int(round((box[0] + box[2]) / 2.0))
    x = max(0, min(x, stripe_sums.size - 1))
    band_h = max(1, y2 - y1 + 1)
    return float(stripe_sums[x] / float(band_h * PROBE_WIDTH))


def _classification(
    *,
    historical_raw_exact: bool,
    public_hybrid_exact: bool,
    historical_hybrid_exact: bool,
    public_band: Sequence[int] | None,
    historical_band: Sequence[int] | None,
    public_ratio: float | None,
    historical_ratio: float | None,
) -> str:
    if historical_raw_exact:
        return "present_in_historical_dense_raw"
    if public_hybrid_exact and not historical_hybrid_exact:
        return "introduced_as_public_hybrid_existing_box"
    if public_band != historical_band:
        if (
            public_ratio is not None
            and historical_ratio is not None
            and public_ratio >= MIN_RATIO
            and historical_ratio < MIN_RATIO
        ):
            return "row_band_geometry_crosses_probe_threshold"
        return "row_band_geometry_differs"
    return "probe_candidate_differs_with_same_nearest_band"


def build_report(run_root: Path, historical_comparison: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    public_report_path = run_root / PUBLIC_REPORT_NAME
    residual_report_path = run_root / RESIDUAL_REPORT_NAME
    public_report = _load(public_report_path)
    residual_report = _load(residual_report_path)
    historical = _load(historical_comparison.resolve())
    for name, payload in (
        ("public replay", public_report),
        ("residual analysis", residual_report),
        ("historical comparison", historical),
    ):
        if not isinstance(payload, Mapping) or payload.get("status") != "completed":
            raise ValueError(f"Incomplete {name} report")

    public_pages = public_report.get("pages")
    residual_pages = residual_report.get("pages")
    historical_pages = historical.get("pages")
    if not all(
        isinstance(value, Mapping) for value in (public_pages, residual_pages, historical_pages)
    ):
        raise ValueError("One or more reports lack page mappings")

    pages: dict[str, Any] = {}
    for label, residual_page in residual_pages.items():
        if not isinstance(residual_page, Mapping):
            continue
        false_positives = residual_page.get("false_positive_residuals")
        if not isinstance(false_positives, list):
            raise ValueError(f"Invalid false-positive rows: {label}")
        public_page = public_pages.get(label)
        historical_page = historical_pages.get(label)
        if not isinstance(public_page, Mapping) or not isinstance(historical_page, Mapping):
            raise ValueError(f"Missing source page: {label}")

        artifacts = public_page.get("artifacts")
        historical_inventory = historical_page.get("historical_inventory_record")
        layers = historical_page.get("layer_comparisons")
        if not all(
            isinstance(value, Mapping) for value in (artifacts, historical_inventory, layers)
        ):
            raise ValueError(f"Incomplete source metadata: {label}")

        image_path = _path(artifacts.get("image"), f"{label}.image")
        public_hybrid_path = _path(artifacts.get("public_hybrid"), f"{label}.public_hybrid")
        public_raw_path = _path(artifacts.get("dense_raw"), f"{label}.public_raw")
        public_filtered_path = _path(artifacts.get("filtered"), f"{label}.public_filtered")
        historical_hybrid_path = _path(
            historical_inventory.get("hybrid_predictions"),
            f"{label}.historical_hybrid",
        )
        dense_comparison = layers.get("dense_raw")
        filter_comparison = layers.get("clef_filtered")
        if not isinstance(dense_comparison, Mapping) or not isinstance(filter_comparison, Mapping):
            raise ValueError(f"Historical layer paths missing: {label}")
        historical_raw_path = _path(
            dense_comparison.get("historical_path"),
            f"{label}.historical_raw",
        )
        historical_filtered_path = _path(
            filter_comparison.get("historical_path"),
            f"{label}.historical_filtered",
        )

        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Failed to read image: {image_path}")
        public_hybrid = _boxes(public_hybrid_path)
        historical_hybrid = _boxes(historical_hybrid_path)
        public_raw = _boxes(public_raw_path)
        historical_raw = _boxes(historical_raw_path)
        public_filtered = _boxes(public_filtered_path)
        historical_filtered = _boxes(historical_filtered_path)
        public_bands = _bands(public_hybrid)
        historical_bands = _bands(historical_hybrid)

        rows = []
        for item in false_positives:
            if not isinstance(item, Mapping):
                continue
            bbox = normalize_box(item["prediction_bbox"])
            public_relation = _band_relation(bbox, public_bands)
            historical_relation = _band_relation(bbox, historical_bands)
            public_band = public_relation["nearest_band"]
            historical_band = historical_relation["nearest_band"]
            public_ratio = _probe_ratio(image, public_band, bbox)
            historical_ratio = _probe_ratio(image, historical_band, bbox)
            historical_raw_exact = _exact(bbox, historical_raw)
            public_hybrid_exact = _exact(bbox, public_hybrid)
            historical_hybrid_exact = _exact(bbox, historical_hybrid)
            rows.append(
                {
                    "prediction_bbox": list(bbox),
                    "cnn_score": item.get("cnn_score"),
                    "nearest_accepted": item.get("nearest_accepted"),
                    "presence": {
                        "public_hybrid_exact": public_hybrid_exact,
                        "historical_hybrid_exact": historical_hybrid_exact,
                        "public_dense_raw_exact": _exact(bbox, public_raw),
                        "historical_dense_raw_exact": historical_raw_exact,
                        "public_filtered_exact": _exact(bbox, public_filtered),
                        "historical_filtered_exact": _exact(bbox, historical_filtered),
                    },
                    "public_row_band": {
                        **public_relation,
                        "probe_ratio_at_x": public_ratio,
                    },
                    "historical_row_band": {
                        **historical_relation,
                        "probe_ratio_at_x": historical_ratio,
                    },
                    "nearest_sources": {
                        "public_hybrid": _nearest(bbox, public_hybrid),
                        "historical_hybrid": _nearest(bbox, historical_hybrid),
                        "historical_dense_raw": _nearest(bbox, historical_raw),
                        "historical_filtered": _nearest(bbox, historical_filtered),
                    },
                    "classification": _classification(
                        historical_raw_exact=historical_raw_exact,
                        public_hybrid_exact=public_hybrid_exact,
                        historical_hybrid_exact=historical_hybrid_exact,
                        public_band=public_band,
                        historical_band=historical_band,
                        public_ratio=public_ratio,
                        historical_ratio=historical_ratio,
                    ),
                }
            )

        pages[str(label)] = {
            "score": residual_page.get("score"),
            "page": residual_page.get("page"),
            "false_positive_count": len(rows),
            "row_band_contract": {
                "band_source": "row_stats",
                "cluster_max_dist": CLUSTER_MAX_DIST,
                "min_row_count": MIN_ROW_COUNT,
                "ink_threshold": INK_THRESHOLD,
                "probe_width": PROBE_WIDTH,
                "min_ratio": MIN_RATIO,
            },
            "source_paths": {
                "image": str(image_path),
                "public_hybrid": str(public_hybrid_path),
                "historical_hybrid": str(historical_hybrid_path),
                "public_dense_raw": str(public_raw_path),
                "historical_dense_raw": str(historical_raw_path),
                "public_filtered": str(public_filtered_path),
                "historical_filtered": str(historical_filtered_path),
            },
            "source_counts": {
                "public_hybrid": len(public_hybrid),
                "historical_hybrid": len(historical_hybrid),
                "public_row_bands": len(public_bands),
                "historical_row_bands": len(historical_bands),
                "public_dense_raw": len(public_raw),
                "historical_dense_raw": len(historical_raw),
            },
            "false_positives": rows,
        }

    classifications = [
        row["classification"] for page in pages.values() for row in page["false_positives"]
    ]
    return {
        "schema_version": "issue255.public_stage_e_fp_source_analysis.v1",
        "status": "completed",
        "analysis_only": True,
        "source_run": str(run_root),
        "source_public_report": str(public_report_path),
        "source_residual_report": str(residual_report_path),
        "source_historical_comparison": str(historical_comparison.resolve()),
        "historical_artifacts_used_for_analysis_only": True,
        "pages": pages,
        "summary": {
            "false_positive_count": len(classifications),
            "classifications": {
                value: classifications.count(value) for value in sorted(set(classifications))
            },
        },
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
                "summary": report["summary"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
