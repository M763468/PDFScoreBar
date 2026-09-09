#!/usr/bin/env python3
"""Probe candidate-native normalized MMR OCR regions for Issue #277.

This focused experiment is intended for the residual cases left after retained
candidate anchoring/consensus.  It reruns RapidOCR only on normalized regions derived
from the candidate-native measure span and staff height.  It does not rerun CNN,
detector, HOMR, SR, OMR-DLN, numbering, or full68 MMR, and it never uses frozen-A
coordinates.

The matrix is deliberately diagnostic: several scale-relative horizontal insets,
masked/unmasked inputs, and the existing preprocessing modes are compared.  A later
production candidate must choose a bounded contract and validate it independently;
this probe itself is not production logic.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2

from src.measure_numbering.mmr import MMROCREngine
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from tools.issue277.diagnose_retained_mmr_ocr_provenance import (
    _load_json,
    _load_matrix_pages,
    _resolve_shared_path,
    rank_numeric_candidates,
)

HORIZONTAL_POLICIES = {
    "full": (0.00, 1.00),
    "inner90": (0.05, 0.95),
    "inner80": (0.10, 0.90),
    "inner70": (0.15, 0.85),
}
PREPROCESS_MODES = ("standard", "no_dilate", "heavy_dilate")
MASK_MODES = ("masked", "unmasked")
UPPER_STAFF_MARGIN_RATIO = 0.5


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalized_roi_bounds(
    measure_bbox: Sequence[float],
    staff_bbox: Sequence[float],
    image_width: int,
    image_height: int,
    left_fraction: float,
    right_fraction: float,
) -> list[int]:
    """Return a scale-relative OCR ROI anchored to the measure span and staff."""

    mx1, _my1, mx2, _my2 = (float(value) for value in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (float(value) for value in staff_bbox)
    measure_width = max(1.0, mx2 - mx1)
    staff_height = max(1.0, sy2 - sy1)
    x1 = int(round(mx1 + left_fraction * measure_width))
    x2 = int(round(mx1 + right_fraction * measure_width))
    y1 = int(round(sy1 - UPPER_STAFF_MARGIN_RATIO * staff_height))
    y2 = int(round(sy2))
    return [
        max(0, min(image_width, x1)),
        max(0, min(image_height, y1)),
        max(0, min(image_width, x2)),
        max(0, min(image_height, y2)),
    ]


def aggregate_staff_results(staff_runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [run for run in staff_runs if run.get("selected_num") is not None]
    if not selected:
        return {"found_num": None, "support": 0, "best_score": 0.0}
    votes = Counter(int(run["selected_num"]) for run in selected)
    max_support = max(votes.values())
    tied = [value for value, count in votes.items() if count == max_support]
    best_by_value = {
        value: max(
            float(run["selected_score"])
            for run in selected
            if int(run["selected_num"]) == value
        )
        for value in tied
    }
    found_num = max(tied, key=lambda value: best_by_value[value])
    return {
        "found_num": found_num,
        "support": int(max_support),
        "best_score": float(best_by_value[found_num]),
        "vote_counts": {str(value): int(count) for value, count in sorted(votes.items())},
    }


def consensus_across_modes(mode_results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    values = [
        int(result["found_num"])
        for result in mode_results.values()
        if result.get("found_num") is not None
    ]
    if not values:
        return {"found_num": None, "support": 0, "vote_counts": {}}
    votes = Counter(values)
    max_support = max(votes.values())
    tied = [value for value, count in votes.items() if count == max_support]
    if len(tied) == 1:
        found_num = tied[0]
    else:
        found_num = max(
            tied,
            key=lambda value: max(
                float(result.get("best_score", 0.0))
                for result in mode_results.values()
                if result.get("found_num") == value
            ),
        )
    return {
        "found_num": found_num,
        "support": int(max_support),
        "vote_counts": {str(value): int(count) for value, count in sorted(votes.items())},
    }


def _run_staff_roi(
    engine: MMROCREngine,
    image,
    measure_bbox: Sequence[float],
    staff_bbox: Sequence[float],
    policy: tuple[float, float],
    mask_mode: str,
    preprocess_mode: str,
) -> dict[str, Any]:
    h_img, w_img = image.shape[:2]
    roi = normalized_roi_bounds(
        measure_bbox,
        staff_bbox,
        w_img,
        h_img,
        policy[0],
        policy[1],
    )
    x1, y1, x2, y2 = roi
    crop = image[y1:y2, x1:x2]
    if crop is None or crop.size == 0:
        return {
            "roi": roi,
            "selected_num": None,
            "selected_score": 0.0,
            "raw_items": [],
            "ranked_numeric_candidates": [],
        }

    if mask_mode == "masked":
        staff_top_rel = float(staff_bbox[1]) - y1
        staff_height = float(staff_bbox[3]) - float(staff_bbox[1])
        crop = engine.mask_hbar_candidates(crop, staff_top_rel, staff_height)
    processed = engine.preprocess_variant(crop, mode=preprocess_mode, angle=0)
    if processed is None:
        return {
            "roi": roi,
            "selected_num": None,
            "selected_score": 0.0,
            "raw_items": [],
            "ranked_numeric_candidates": [],
        }

    raw, _ = engine.ocr_engine(processed)
    raw = raw or []
    ranked = rank_numeric_candidates(engine, list(raw), processed.shape[1], processed.shape[0])
    selected_num, selected_score, selected_debug = engine.select_best_candidate(
        list(raw), processed.shape[1], processed.shape[0]
    )
    return {
        "roi": roi,
        "processed_shape": list(processed.shape[:2]),
        "selected_num": selected_num,
        "selected_score": float(selected_score),
        "selected_debug": str(selected_debug),
        "raw_items": [
            {
                "points": [[float(value) for value in point] for point in item[0]],
                "text": str(item[1]),
                "confidence_diagnostic_only": float(item[2]),
            }
            for item in raw
        ],
        "ranked_numeric_candidates": ranked,
    }


def run(
    provenance_path: Path,
    manifest_path: Path,
    output_path: Path,
    provider_mode: str,
) -> dict[str, Any]:
    provenance = _load_json(provenance_path)
    manifest = _load_json(manifest_path)
    if not isinstance(provenance, Mapping) or provenance.get("status") != "completed":
        raise ValueError("OCR provenance report is not completed")
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("Full68 manifest is not completed")
    if provenance.get("source_variant_match_failures"):
        raise RuntimeError("OCR provenance report has source replay mismatches")

    rapidocr = create_mmr_rapidocr(provider_mode)
    providers = collect_rapidocr_providers(rapidocr)
    if provider_mode == "cuda" and not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDA was requested but not confirmed: {providers}")
    engine = MMROCREngine(ocr_engine=rapidocr)
    matrix_pages = _load_matrix_pages(manifest)

    records_out: list[dict[str, Any]] = []
    config_hits: Counter[str] = Counter()
    config_total: Counter[str] = Counter()

    for record in provenance.get("records", []):
        if not isinstance(record, Mapping):
            continue
        zero = next(
            point for point in record.get("sweep", []) if abs(float(point["fraction"])) < 1e-12
        )
        matrix_key = (str(record["score"]), str(record["page_name"]))
        matrix_page = matrix_pages.get(matrix_key)
        if matrix_page is None:
            raise RuntimeError(f"Full68 matrix lacks {record['page_id']}: {matrix_key}")
        image_path = _resolve_shared_path(str(matrix_page["image"]))
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)

        expected_num = int(record["expected_skip"]) + 1
        staff_bboxes = record["native_reference"]["primary_staff_bboxes"]
        policy_results: dict[str, Any] = {}
        for policy_name, fractions in HORIZONTAL_POLICIES.items():
            for mask_mode in MASK_MODES:
                mode_results: dict[str, Any] = {}
                for preprocess_mode in PREPROCESS_MODES:
                    staff_runs = [
                        _run_staff_roi(
                            engine,
                            image,
                            zero["measure_bbox"],
                            staff_bbox,
                            fractions,
                            mask_mode,
                            preprocess_mode,
                        )
                        for staff_bbox in staff_bboxes
                    ]
                    aggregate = aggregate_staff_results(staff_runs)
                    mode_results[preprocess_mode] = {
                        **aggregate,
                        "staff_runs": staff_runs,
                    }
                consensus = consensus_across_modes(mode_results)
                config_name = f"{policy_name}_{mask_mode}"
                hit = consensus.get("found_num") == expected_num
                config_total[config_name] += 1
                if hit:
                    config_hits[config_name] += 1
                policy_results[config_name] = {
                    "horizontal_fractions": list(fractions),
                    "upper_staff_margin_ratio": UPPER_STAFF_MARGIN_RATIO,
                    "consensus": consensus,
                    "expected_hit": hit,
                    "modes": mode_results,
                }

        records_out.append(
            {
                "page_id": record["page_id"],
                "score": record["score"],
                "page_name": record["page_name"],
                "key": record["key"],
                "expected_num": expected_num,
                "source_native_num": zero.get("source_found_num"),
                "source_native_skip": zero.get("source_skip"),
                "native_measure_bbox": list(zero["measure_bbox"]),
                "native_staff_bboxes": staff_bboxes,
                "policy_results": policy_results,
            }
        )

    config_summary = {
        name: {
            "hits": int(config_hits[name]),
            "total": int(config_total[name]),
            "all_controls_exact": config_hits[name] == config_total[name] and config_total[name] > 0,
        }
        for name in sorted(config_total)
    }
    payload = {
        "schema_version": "issue277.retained_mmr_normalized_roi_probe.v1",
        "status": "completed",
        "execution_contract": {
            "production_code_modified": False,
            "focused_rapidocr_reexecuted": True,
            "cnn_reexecuted": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "numbering_reexecuted": False,
            "full68_mmr_reexecuted": False,
            "frozen_A_geometry_used": False,
            "geometry": "candidate-native zero-offset measure/staff only",
        },
        "runtime": {
            "rapidocr_provider_mode": provider_mode,
            "providers": providers,
        },
        "matrix": {
            "horizontal_policies": {name: list(value) for name, value in HORIZONTAL_POLICIES.items()},
            "upper_staff_margin_ratio": UPPER_STAFF_MARGIN_RATIO,
            "mask_modes": list(MASK_MODES),
            "preprocess_modes": list(PREPROCESS_MODES),
            "note": "diagnostic search matrix; not a production threshold contract",
        },
        "config_summary": config_summary,
        "all_control_exact_configs": [
            name for name, result in config_summary.items() if result["all_controls_exact"]
        ],
        "records": records_out,
    }
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--full68-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=("auto", "cpu", "cuda"), default="cuda")
    args = parser.parse_args()
    payload = run(args.provenance, args.full68_manifest, args.output, args.provider)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "all_control_exact_configs": payload["all_control_exact_configs"],
                "config_summary": payload["config_summary"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
