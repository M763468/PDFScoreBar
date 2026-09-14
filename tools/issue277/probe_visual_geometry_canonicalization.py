#!/usr/bin/env python3
"""Probe visual canonicalization of MMR geometry for Issue #277.

Experiment-only and OCR-free. The geometry-stability work showed that both OCR and
MMR classifier probabilities can change under only +/-1/2/4 px support-geometry
perturbations. Rather than adding more OCR voting, this probe asks whether the
perturbed candidate-native geometry can first be snapped back to stable image
features:

* measure x boundaries -> nearby vertical barline ink;
* staff y translation -> nearby long horizontal staff-line ink.

The input bbox is only a narrow search seed. Search radii are staff-scale-relative
and bounded. No historical-A geometry or expected fixture value is used. The same
25 native/perturbed variants are replayed, but no classifier/OCR inference occurs.

If this layer cannot make geometry invariant by itself, it is not suitable as the
basis for a production robustness change.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Mapping

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import probe_geometry_stability_envelope as stability_probe
import probe_hbar_anchored_roi as hbar_probe
import probe_native_geometry_robustness as base

SNAP_RADIUS_MIN = 4
SNAP_RADIUS_MAX = 8
SNAP_RADIUS_STAFF_RATIO = 0.05
VERTICAL_HALF_WIDTH = 1
STAFF_X_INSET_FRACTION = 0.10
VIEW_NAMES = ("primary", "implicit_start_alternate", "fallback")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _binary(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, result = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    return result


def _clip(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _radius(staff_height: float) -> int:
    return max(
        SNAP_RADIUS_MIN,
        min(SNAP_RADIUS_MAX, int(round(SNAP_RADIUS_STAFF_RATIO * staff_height))),
    )


def _peak_center(scores: list[tuple[int, float]]) -> tuple[int, float]:
    if not scores:
        raise ValueError("empty snap score set")
    best = max(score for _coord, score in scores)
    # Center a thick visual line instead of choosing one arbitrary edge pixel.
    threshold = best * 0.92
    strong = [coord for coord, score in scores if score >= threshold]
    if not strong:
        coord, score = max(scores, key=lambda item: item[1])
        return int(coord), float(score)
    center = int(round(float(median(strong))))
    center_score = max(score for coord, score in scores if coord == center)
    return center, float(center_score)


def _snap_vertical_boundary(
    ink: np.ndarray,
    x: int,
    staves: list[Mapping[str, Any]],
    staff_height: float,
) -> tuple[int, float]:
    image_h, image_w = ink.shape[:2]
    radius = _radius(staff_height)
    scores: list[tuple[int, float]] = []
    for candidate in range(max(0, x - radius), min(image_w - 1, x + radius) + 1):
        total = 0
        possible = 0
        cx1 = max(0, candidate - VERTICAL_HALF_WIDTH)
        cx2 = min(image_w, candidate + VERTICAL_HALF_WIDTH + 1)
        for stave in staves:
            _sx1, sy1, _sx2, sy2 = (int(v) for v in stave["bbox"])
            pad = max(1, int(round(0.08 * max(1, sy2 - sy1))))
            y1 = _clip(sy1 - pad, 0, image_h)
            y2 = _clip(sy2 + pad, 0, image_h)
            if y2 <= y1:
                continue
            total += int(np.count_nonzero(ink[y1:y2, cx1:cx2]))
            possible += (y2 - y1) * max(1, cx2 - cx1)
        score = float(total / max(1, possible))
        scores.append((candidate, score))
    return _peak_center(scores)


def _snap_staff_translation(
    ink: np.ndarray,
    staff_bbox: list[int],
    measure_bbox: list[int],
) -> tuple[list[int], float, int]:
    image_h, image_w = ink.shape[:2]
    sx1, sy1, sx2, sy2 = (int(v) for v in staff_bbox)
    mx1, _my1, mx2, _my2 = (int(v) for v in measure_bbox)
    staff_height = max(1.0, float(sy2 - sy1))
    center = (sy1 + sy2) / 2.0
    radius = _radius(staff_height)

    measure_width = max(2, mx2 - mx1)
    inset = max(1, int(round(STAFF_X_INSET_FRACTION * measure_width)))
    x1 = _clip(mx1 + inset, 0, image_w)
    x2 = _clip(mx2 - inset, 0, image_w)
    if x2 <= x1:
        x1 = _clip(mx1, 0, image_w)
        x2 = _clip(mx2, 0, image_w)

    scores: list[tuple[int, float]] = []
    center_i = int(round(center))
    for candidate in range(max(0, center_i - radius), min(image_h - 1, center_i + radius) + 1):
        if x2 <= x1:
            score = 0.0
        else:
            score = float(np.count_nonzero(ink[candidate : candidate + 1, x1:x2]))
            score /= max(1, x2 - x1)
        scores.append((candidate, score))
    snapped_center, score = _peak_center(scores)
    dy = int(round(snapped_center - center))
    ny1 = _clip(sy1 + dy, 0, image_h - 1)
    ny2 = _clip(sy2 + dy, ny1 + 1, image_h)
    # Preserve staff bbox height when clipping near an image edge.
    height = sy2 - sy1
    if ny2 - ny1 != height:
        ny1 = max(0, min(image_h - height, ny1))
        ny2 = min(image_h, ny1 + height)
    return [sx1, ny1, sx2, ny2], score, dy


def _canonical_geometry(
    image: np.ndarray,
    measure_bbox: list[int],
    staves: list[Mapping[str, Any]],
) -> dict[str, Any]:
    ink = _binary(image)
    heights = [max(1, int(s["bbox"][3]) - int(s["bbox"][1])) for s in staves]
    typical_height = float(median(heights)) if heights else 160.0
    x1, y1, x2, y2 = (int(v) for v in measure_bbox)
    sx1, left_score = _snap_vertical_boundary(ink, x1, staves, typical_height)
    sx2, right_score = _snap_vertical_boundary(ink, x2, staves, typical_height)
    if sx2 <= sx1 + 1:
        sx1, sx2 = x1, x2
    snapped_measure = [sx1, y1, sx2, y2]

    snapped_staves = []
    staff_scores = []
    staff_dys = []
    for stave in staves:
        snapped, score, dy = _snap_staff_translation(
            ink,
            [int(v) for v in stave["bbox"]],
            snapped_measure,
        )
        snapped_staves.append(snapped)
        staff_scores.append(score)
        staff_dys.append(dy)

    return {
        "measure_bbox": snapped_measure,
        "staff_bboxes": snapped_staves,
        "measure_dx1": sx1 - x1,
        "measure_dx2": sx2 - x2,
        "staff_dys": staff_dys,
        "vertical_scores": [left_score, right_score],
        "staff_scores": staff_scores,
    }


def _view_geometry(
    image: np.ndarray,
    support: Mapping[str, Any],
    view_name: str,
    system_idx: int,
    measure_idx: int,
) -> dict[str, Any]:
    view = support["views"][view_name]
    system = view["pages"][0]["systems"][system_idx]
    measure = system["measures"][measure_idx]
    return _canonical_geometry(
        image,
        [int(v) for v in measure["bbox"]],
        list(system.get("staves", [])),
    )


def _signature(item: Mapping[str, Any]) -> tuple[Any, ...]:
    measure = item["measure_bbox"]
    staves = item["staff_bboxes"]
    return (
        int(measure[0]),
        int(measure[2]),
        tuple((int(b[1]), int(b[3])) for b in staves),
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    stability_path = args.stability_artifact.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / base.DEFAULT_MANIFEST_REL).resolve()
    )
    for path in (stability_path, manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    started = time.perf_counter()
    stability = _load(stability_path)
    sensitive = hbar_probe._sensitive_keys(stability)
    variants = stability_probe._variant_specs()
    matrix_pages = base._load_matrix_pages(_load(manifest_path), issue294_root)
    specs = {str(spec.page_id): spec for spec in base.build_page_specs()}

    by_page: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for item in sensitive:
        by_page[str(item["page_id"])].append(
            (int(item["system"]), int(item["measure"]), str(item["key"]))
        )

    prepared: dict[str, dict[str, Any]] = {}
    for page_id in sorted(by_page):
        spec = specs[page_id]
        matrix_page = matrix_pages[(str(spec.score), str(spec.page_name))]
        _page_data, image_path, support, _mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        prepared[page_id] = {
            "image": image,
            "support": support,
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        }

    native: dict[str, dict[str, tuple[Any, ...]]] = {}
    observations: dict[str, dict[str, Any]] = defaultdict(dict)
    family_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"comparisons": 0, "exact": 0}
    )

    for variant in variants:
        variant_name = str(variant["name"])
        family = str(variant["family"])
        for page_id in sorted(by_page):
            item = prepared[page_id]
            support = stability_probe._perturb_support(
                item["support"], variant, item["width"], item["height"]
            )
            for system_idx, measure_idx, key in sorted(by_page[page_id]):
                views: dict[str, Any] = {}
                for view_name in VIEW_NAMES:
                    canonical = _view_geometry(
                        item["image"], support, view_name, system_idx, measure_idx
                    )
                    views[view_name] = canonical

                signatures = {
                    name: _signature(value) for name, value in views.items()
                }
                if variant_name == "native":
                    native[key] = signatures
                    exact = True
                else:
                    exact = all(
                        signatures[name] == native[key][name] for name in VIEW_NAMES
                    )
                    family_totals[family]["comparisons"] += 1
                    family_totals[family]["exact"] += int(exact)

                observations[key][variant_name] = {
                    "family": family,
                    "delta": int(variant["delta"]),
                    "exact_to_native": exact,
                    "views": views,
                }

    key_summary = []
    for key in sorted(observations):
        values = observations[key]
        failed = [
            name
            for name, value in values.items()
            if name != "native" and not value["exact_to_native"]
        ]
        native_views = values["native"]["views"]
        key_summary.append(
            {
                "key": key,
                "all_perturbations_exact": not failed,
                "failed_variants": failed,
                "native_displacement": {
                    name: {
                        "measure_dx1": int(view["measure_dx1"]),
                        "measure_dx2": int(view["measure_dx2"]),
                        "staff_dys": [int(v) for v in view["staff_dys"]],
                    }
                    for name, view in native_views.items()
                },
            }
        )

    family_summary = {
        family: {
            **value,
            "exact_fraction": (
                value["exact"] / value["comparisons"]
                if value["comparisons"]
                else 1.0
            ),
        }
        for family, value in sorted(family_totals.items())
    }
    exact_keys = sum(item["all_perturbations_exact"] for item in key_summary)

    return {
        "schema_version": "issue277.visual_geometry_canonicalization.v1",
        "status": "completed",
        "diagnostic_only": True,
        "contract": {
            "historical_a_geometry_used": False,
            "expected_values_used": False,
            "ocr_or_classifier_run": False,
            "image_content_is_final_anchor": True,
        },
        "sensitive_page_count": len(by_page),
        "sensitive_measure_count": len(key_summary),
        "variant_count": len(variants),
        "all_perturbations_exact_keys": exact_keys,
        "all_keys_exact": exact_keys == len(key_summary),
        "family_summary": family_summary,
        "key_summary": key_summary,
        "observations": observations,
        "runtime_seconds": time.perf_counter() - started,
    }


def summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    return {
        "status": payload["status"],
        "output": str(output),
        "sensitive_measure_count": payload["sensitive_measure_count"],
        "variant_count": payload["variant_count"],
        "all_perturbations_exact_keys": payload["all_perturbations_exact_keys"],
        "all_keys_exact": payload["all_keys_exact"],
        "family_summary": payload["family_summary"],
        "failed_keys": [
            {
                "key": item["key"],
                "failed_variants": item["failed_variants"],
                "native_displacement": item["native_displacement"],
            }
            for item in payload["key_summary"]
            if not item["all_perturbations_exact"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--issue294-root", type=Path, default=base.DEFAULT_ISSUE294_ROOT
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--stability-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    try:
        payload = run(args)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary(payload, output), indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic CLI
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
