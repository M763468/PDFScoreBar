#!/usr/bin/env python3
"""Diagnose retained MMR OCR candidate provenance for Issue #277.

This forensic helper consumes the Issue #294 visual-stability report plus the
retained full68 manifest. It does not rerun detector/HOMR/SR/OMR-DLN/full68 MMR
and does not modify production code. It reruns only RapidOCR for the recorded
candidate-native sweep geometries, records raw/merged numeric candidates with
production-equivalent spatial scoring, and exports selected-variant overlays.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMROCREngine
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)

PRIMARY_VARIANTS = (
    "standard",
    "no_dilate",
    "heavy_dilate",
)
FALLBACK_VARIANTS = (
    "unmasked_fallback_standard",
    "left_wide_unmasked_fallback_standard",
)
VARIANT_SPECS: dict[str, dict[str, Any]] = {
    "standard": {
        "masked": True,
        "mode": "standard",
        "margin_y": 80,
        "dx1": -30,
        "dx2": 30,
        "min_prob": 0.0,
    },
    "no_dilate": {
        "masked": True,
        "mode": "no_dilate",
        "margin_y": 80,
        "dx1": -30,
        "dx2": 30,
        "min_prob": 0.5,
    },
    "heavy_dilate": {
        "masked": True,
        "mode": "heavy_dilate",
        "margin_y": 80,
        "dx1": -30,
        "dx2": 30,
        "min_prob": 0.5,
    },
    "unmasked_fallback_standard": {
        "masked": False,
        "mode": "standard",
        "margin_y": 80,
        "dx1": -30,
        "dx2": 30,
        "min_prob": 0.1,
    },
    "left_wide_unmasked_fallback_standard": {
        "masked": False,
        "mode": "standard",
        "margin_y": 120,
        "dx1": -180,
        "dx2": 60,
        "min_prob": 0.5,
    },
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _resolve_shared_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_file():
        return raw
    if not raw.is_absolute():
        candidate = PROJECT_ROOT / raw
        if candidate.is_file():
            return candidate
    parts = raw.parts
    for marker in ("logs", "data", "datasets"):
        if marker in parts:
            index = parts.index(marker)
            candidate = PROJECT_ROOT.joinpath(*parts[index:])
            if candidate.is_file():
                return candidate
    if "/workspace/" in str(raw):
        suffix = str(raw).split("/workspace/", 1)[1]
        candidate = PROJECT_ROOT / suffix
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(raw)


def _report_page_key(page: Mapping[str, Any]) -> tuple[str, str]:
    image = Path(str(page["image"]))
    return image.parent.name, image.stem


def _load_matrix_pages(manifest: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    chunks = manifest.get("completed_chunks")
    if not isinstance(chunks, list):
        raise ValueError("Full68 manifest lacks completed_chunks")
    pages: dict[tuple[str, str], Mapping[str, Any]] = {}
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            raise ValueError("Malformed completed chunk")
        report_path = _resolve_shared_path(str(chunk["matrix_report"]))
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
    return pages


def _ocr_item_payload(item: Sequence[Any]) -> dict[str, Any]:
    points, text, confidence = item
    return {
        "points": [[float(value) for value in point] for point in points],
        "text": str(text),
        "confidence": float(confidence),
    }


def rank_numeric_candidates(
    engine: MMROCREngine,
    ocr_result: list,
    img_width: int,
    img_height: int,
) -> list[dict[str, Any]]:
    """Mirror production candidate scoring while retaining candidate provenance."""

    candidates: list[dict[str, Any]] = []
    center_x = img_width / 2.0
    for item, source in engine._candidate_items(list(ocr_result)):
        box_points, text, confidence = item
        clean_text = re.sub(r"^[EP](\d)", r"\1", str(text))
        clean_text = re.sub(r"[.,;]", "", clean_text)
        blacklisted = engine._has_blacklisted_text(str(text))
        nums_found = engine._extract_numeric_candidates(clean_text, blacklisted)
        xs = [float(point[0]) for point in box_points]
        ys = [float(point[1]) for point in box_points]
        if not xs or not ys:
            continue
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        box_h = y_max - y_min
        box_center_x = (x_min + x_max) / 2.0
        box_center_y = (y_min + y_max) / 2.0
        dist_x_norm = abs(box_center_x - center_x) / max(1, img_width)
        dist_y_norm = abs(box_center_y - (img_height / 2.0)) / max(1, img_height)
        h_ratio = box_h / max(1, img_height)
        for n_str in nums_found:
            try:
                value = int(n_str)
            except ValueError:
                continue
            if value < 2:
                continue
            score = 100 - dist_x_norm * 200 - dist_y_norm * 100
            if 0.4 <= h_ratio <= 0.95:
                score += 20
            elif h_ratio < 0.3:
                score -= 30
            if "=" in str(text):
                parts = str(text).split("=")
                if len(parts) > 1 and n_str in parts[1]:
                    score -= 80
            if value > 100:
                score -= 50
            if value > 20 and img_width < 100:
                score -= 200
            candidates.append(
                {
                    "value": value,
                    "score": float(score),
                    "source": source,
                    "text": str(text),
                    "confidence": float(confidence),
                    "bbox": [x_min, y_min, x_max, y_max],
                    "dist_x_norm": float(dist_x_norm),
                    "dist_y_norm": float(dist_y_norm),
                    "height_ratio": float(h_ratio),
                    "blacklisted_text": bool(blacklisted),
                }
            )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def selected_variant_name(debug: str) -> str | None:
    match = re.search(r"variant=([^,:]+):0", str(debug))
    return match.group(1) if match else None


def interesting_sweep_indices(sweep: Sequence[Mapping[str, Any]]) -> list[int]:
    if not sweep:
        return []
    selected = {0, len(sweep) - 1}
    for index, item in enumerate(sweep):
        if abs(float(item.get("fraction", 1.0))) < 1e-12:
            selected.add(index)
        if index > 0 and item.get("skip") != sweep[index - 1].get("skip"):
            selected.add(index - 1)
            selected.add(index)
    return sorted(selected)


def _variant_allowed(name: str, probability: float) -> bool:
    return probability > float(VARIANT_SPECS[name]["min_prob"])


def _run_variant_for_staff(
    engine: MMROCREngine,
    image: np.ndarray,
    measure_bbox: Sequence[int],
    staff_bbox: Sequence[int],
    variant_name: str,
) -> tuple[dict[str, Any], np.ndarray]:
    spec = VARIANT_SPECS[variant_name]
    x1, _y1, x2, _y2 = (int(value) for value in measure_bbox)
    sx1, sy1, sx2, sy2 = (int(value) for value in staff_bbox)
    h_img, w_img = image.shape[:2]
    margin_y = int(spec["margin_y"])
    ox1 = max(0, x1 + int(spec["dx1"]))
    ox2 = min(w_img, x2 + int(spec["dx2"]))
    oy1 = max(0, sy1 - margin_y)
    oy2 = min(h_img, sy2 + margin_y)
    crop = image[oy1:oy2, ox1:ox2]
    if crop is None or crop.size == 0:
        raise RuntimeError(f"Empty OCR crop for {variant_name}: {measure_bbox} / {staff_bbox}")

    if bool(spec["masked"]):
        crop = engine.mask_hbar_candidates(crop, margin_y, sy2 - sy1)
    processed = engine.preprocess_variant(crop, mode=str(spec["mode"]), angle=0)
    if processed is None or processed.size == 0:
        raise RuntimeError(f"Empty preprocessed crop for {variant_name}")
    raw, _ = engine.ocr_engine(processed)
    raw = raw or []
    ranked = rank_numeric_candidates(engine, list(raw), processed.shape[1], processed.shape[0])
    selected_num, selected_score, selected_debug = engine.select_best_candidate(
        list(raw), processed.shape[1], processed.shape[0]
    )
    payload = {
        "crop_bounds": [ox1, oy1, ox2, oy2],
        "processed_shape": list(processed.shape),
        "raw_items": [_ocr_item_payload(item) for item in raw],
        "merged_items": [
            _ocr_item_payload(item)
            for item in engine.merge_ocr_results(list(raw))
            if item not in raw
        ],
        "ranked_numeric_candidates": ranked,
        "selected_num": selected_num,
        "selected_score": float(selected_score),
        "selected_debug": str(selected_debug),
    }
    return payload, processed


def _aggregate_variant(staff_runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [run for run in staff_runs if run.get("selected_num") is not None]
    if not selected:
        return {"found_num": None, "score": 0.0, "staff_index": None}
    counts = Counter(int(run["selected_num"]) for run in selected)
    found_num = counts.most_common(1)[0][0]
    candidates = [
        (index, run)
        for index, run in enumerate(staff_runs)
        if run.get("selected_num") == found_num
    ]
    staff_index, best = max(candidates, key=lambda item: float(item[1]["selected_score"]))
    return {
        "found_num": found_num,
        "score": float(best["selected_score"]),
        "staff_index": staff_index,
        "debug": str(best["selected_debug"]),
    }


def _draw_overlay(processed: np.ndarray, raw_items: Sequence[Mapping[str, Any]]) -> np.ndarray:
    if len(processed.shape) == 2:
        canvas = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
    else:
        canvas = processed.copy()
    for item in raw_items:
        points = np.asarray(item["points"], dtype=np.int32)
        if points.ndim != 2 or points.shape[0] < 2:
            continue
        cv2.polylines(canvas, [points], True, (0, 0, 255), 1, cv2.LINE_AA)
        x = int(points[:, 0].min())
        y = max(12, int(points[:, 1].min()) - 4)
        label = f"{item['text']} {float(item['confidence']):.2f}"
        cv2.putText(canvas, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    return canvas


def run(
    stability_path: Path,
    manifest_path: Path,
    output_dir: Path,
    output_json: Path,
    provider_mode: str,
) -> dict[str, Any]:
    stability = _load_json(stability_path)
    manifest = _load_json(manifest_path)
    if not isinstance(stability, Mapping) or stability.get("status") != "completed":
        raise ValueError("Visual-stability report is not completed")
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("Full68 manifest is not completed")

    rapidocr = create_mmr_rapidocr(provider_mode)
    providers = collect_rapidocr_providers(rapidocr)
    if provider_mode == "cuda" and not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDA was requested but not confirmed: {providers}")
    engine = MMROCREngine(ocr_engine=rapidocr)
    matrix_pages = _load_matrix_pages(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)

    records_out: list[dict[str, Any]] = []
    source_variant_match_failures: list[dict[str, Any]] = []
    for record in stability.get("records", []):
        if not isinstance(record, Mapping):
            continue
        page_id = str(record["page_id"])
        matrix_key = (str(record["score"]), str(record["page_name"]))
        matrix_page = matrix_pages.get(matrix_key)
        if matrix_page is None:
            raise RuntimeError(f"Full68 matrix lacks {page_id}: {matrix_key}")
        image_path = _resolve_shared_path(str(matrix_page["image"]))
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        staff_bboxes = record["native_reference"]["primary_staff_bboxes"]
        sweep = record.get("sweep", [])
        interesting = set(interesting_sweep_indices(sweep))
        sweep_out: list[dict[str, Any]] = []

        for index, point in enumerate(sweep):
            probability = float(point["cnn_probability"])
            variant_runs: dict[str, Any] = {}
            processed_images: dict[tuple[str, int], np.ndarray] = {}
            for variant_name in (*PRIMARY_VARIANTS, *FALLBACK_VARIANTS):
                if not _variant_allowed(variant_name, probability):
                    continue
                staff_runs = []
                for staff_index, staff_bbox in enumerate(staff_bboxes):
                    staff_payload, processed = _run_variant_for_staff(
                        engine,
                        image,
                        point["measure_bbox"],
                        staff_bbox,
                        variant_name,
                    )
                    staff_runs.append(staff_payload)
                    processed_images[(variant_name, staff_index)] = processed
                variant_runs[variant_name] = {
                    "aggregate": _aggregate_variant(staff_runs),
                    "staff_runs": staff_runs,
                    "production_reachability": (
                        "primary"
                        if variant_name in PRIMARY_VARIANTS
                        else "fallback_only_if_primary_has_no_numeric_result"
                    ),
                }

            source_debug = str(point.get("debug", ""))
            source_variant = selected_variant_name(source_debug)
            source_match: bool | None = None
            if source_variant in variant_runs and "j2_consensus=" not in source_debug:
                source_match = (
                    variant_runs[source_variant]["aggregate"]["found_num"]
                    == point.get("found_num")
                )
                if not source_match:
                    source_variant_match_failures.append(
                        {
                            "page_id": page_id,
                            "fraction": point["fraction"],
                            "source_found_num": point.get("found_num"),
                            "diagnostic_found_num": variant_runs[source_variant]["aggregate"]["found_num"],
                            "source_variant": source_variant,
                        }
                    )

            overlays: list[str] = []
            if index in interesting and source_variant in variant_runs:
                aggregate = variant_runs[source_variant]["aggregate"]
                staff_index = aggregate.get("staff_index")
                if staff_index is not None:
                    staff_run = variant_runs[source_variant]["staff_runs"][staff_index]
                    overlay = _draw_overlay(
                        processed_images[(source_variant, staff_index)],
                        staff_run["raw_items"],
                    )
                    fraction_token = f"{float(point['fraction']):+.2f}".replace("+", "p").replace("-", "m").replace(".", "p")
                    overlay_path = output_dir / page_id / f"f_{fraction_token}_{source_variant}.png"
                    overlay_path.parent.mkdir(parents=True, exist_ok=True)
                    if not cv2.imwrite(str(overlay_path), overlay):
                        raise RuntimeError(f"Failed to write OCR overlay: {overlay_path}")
                    overlays.append(str(overlay_path))

            sweep_out.append(
                {
                    "fraction": point["fraction"],
                    "dx1": point["dx1"],
                    "measure_bbox": point["measure_bbox"],
                    "cnn_probability_reused": probability,
                    "expected_hit": point["expected_hit"],
                    "source_found_num": point.get("found_num"),
                    "source_skip": point.get("skip"),
                    "source_score": point.get("score"),
                    "source_debug": source_debug,
                    "source_variant": source_variant,
                    "source_variant_aggregate_match": source_match,
                    "variant_runs": variant_runs,
                    "overlays": overlays,
                }
            )

        records_out.append(
            {
                "page_id": page_id,
                "score": record["score"],
                "page_name": record["page_name"],
                "key": record["key"],
                "expected_skip": record["expected_skip"],
                "native_reference": record["native_reference"],
                "sweep": sweep_out,
                "interesting_sweep_indices": sorted(interesting),
            }
        )

    report = {
        "schema_version": "issue277.retained_mmr_ocr_provenance.v1",
        "status": "completed",
        "execution_contract": {
            "production_code_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "full68_mmr_reexecuted": False,
            "cnn_reexecuted": False,
            "recorded_cnn_probability_reused": True,
            "focused_rapidocr_reexecuted": True,
            "input_geometry": "candidate-native sweep from Issue #294 retained visual-stability report",
        },
        "source_stability_report": str(stability_path),
        "source_full68_manifest": str(manifest_path),
        "runtime": {"rapidocr_provider_mode": provider_mode, "providers": providers},
        "records": records_out,
        "source_variant_match_failures": source_variant_match_failures,
        "gates": {
            "record_count_nonzero": bool(records_out),
            "source_variant_matches_when_directly_replayable": not source_variant_match_failures,
        },
    }
    _write_json(output_json, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stability-report", type=Path, required=True)
    parser.add_argument("--full68-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--provider", choices=("auto", "cpu", "cuda"), default="cuda")
    args = parser.parse_args()
    payload = run(
        args.stability_report,
        args.full68_manifest,
        args.output_dir,
        args.output_json,
        args.provider,
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "record_count": len(payload["records"]),
                "source_variant_match_failures": payload["source_variant_match_failures"],
                "output": str(args.output_json),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
