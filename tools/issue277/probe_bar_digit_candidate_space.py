#!/usr/bin/env python3
"""Trace the content-anchored MMR candidate space for Issue #277.

Experiment-only diagnostic. The bar+digit-component probe made most sensitive keys
geometry-invariant, but several keys became stably wrong or stably unreadable. This
probe separates candidate generation from candidate selection on native maintained-B
geometry:

* select all failed keys from the previous component-anchor artifact plus stable
  success controls;
* enumerate every retained bar cluster, every staff bar, and every plausible digit
  component group;
* OCR both the original tight group crop and a horizontal-suppressed isolated bitmap;
* record simple rest-bar shape evidence, but do not use it for selection;
* use expected fixture values only after inference to report whether the correct
  number exists anywhere in the generated candidate space.

No production source is modified.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional

import cv2
import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)

import probe_bar_digit_component_anchor as component_probe
import probe_full68_candidate_policy as full_probe
import probe_native_geometry_robustness as base

MAX_CONTROLS = 4
MAX_GROUPS_PER_BAR = 6
ENDCAP_X_HALF_STAFF = 0.10
ENDCAP_Y_HALF_STAFF = 0.35
ISOLATED_PAD_STAFF = 0.10


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_key(value: str) -> tuple[str, int, int]:
    match = re.fullmatch(r"(page_\d{3}) s(\d+) m(\d+)", value)
    if match is None:
        raise ValueError(f"Malformed key: {value!r}")
    return match.group(1), int(match.group(2)), int(match.group(3))


def _selected_keys(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = payload.get("key_summary")
    if not isinstance(summary, list):
        # CLI summary output uses `keys`, full artifact uses `key_summary`.
        summary = payload.get("keys")
    if not isinstance(summary, list):
        raise ValueError("component artifact lacks key summary")

    failures: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for item in summary:
        if not isinstance(item, Mapping):
            continue
        normalized = dict(item)
        if bool(item.get("all_variants_expected")):
            controls.append(normalized)
        else:
            failures.append(normalized)
    return failures + controls[:MAX_CONTROLS]


def _clip(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _serialize_ocr(result: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if not result:
        return output
    for item in result:
        try:
            points, text, confidence = item
            output.append(
                {
                    "points": [[float(p[0]), float(p[1])] for p in points],
                    "text": str(text),
                    "confidence": float(confidence),
                }
            )
        except (TypeError, ValueError, IndexError):
            output.append({"raw": repr(item)})
    return output


def _run_ocr_image(
    image: np.ndarray,
    *,
    staff_height: float,
    ocr: MMROCREngine,
) -> dict[str, Any]:
    if image is None or image.size == 0:
        return {
            "number": None,
            "skip": None,
            "score": 0.0,
            "debug": "empty_image",
            "raw": [],
        }

    scale = component_probe.REFERENCE_STAFF_HEIGHT / max(1.0, float(staff_height))
    target_w = max(8, int(round(image.shape[1] * scale)))
    target_h = max(8, int(round(image.shape[0] * scale)))
    interpolation = cv2.INTER_CUBIC if scale >= 1.0 else cv2.INTER_AREA
    normalized = cv2.resize(image, (target_w, target_h), interpolation=interpolation)
    processed = ocr.preprocess_variant(
        normalized,
        mode="no_dilate",
        angle=0,
        staff_height=component_probe.REFERENCE_STAFF_HEIGHT,
        use_staff_relative_geometry=True,
    )
    if processed is None or processed.size == 0:
        return {
            "number": None,
            "skip": None,
            "score": 0.0,
            "debug": "empty_preprocess",
            "raw": [],
        }
    raw, _ = ocr.ocr_engine(processed)
    number, score, debug = ocr.select_best_candidate(
        raw or [], processed.shape[1], processed.shape[0]
    )
    selected = None if number is None or int(number) < 2 else int(number)
    return {
        "number": selected,
        "skip": None if selected is None else selected - 1,
        "score": float(score) if selected is not None else 0.0,
        "debug": str(debug),
        "processed_shape": [int(processed.shape[0]), int(processed.shape[1])],
        "raw": _serialize_ocr(raw),
    }


def _original_group_image(
    image: np.ndarray,
    bar: Mapping[str, Any],
    group: Mapping[str, Any],
) -> tuple[np.ndarray, list[int]]:
    height, width = image.shape[:2]
    staff_height = float(bar["staff_height"])
    pad = max(1, int(round(component_probe.DIGIT_PAD_STAFF * staff_height)))
    gx1, gy1, gx2, gy2 = (int(v) for v in group["bbox"])
    x1 = _clip(gx1 - pad, 0, width)
    y1 = _clip(gy1 - pad, 0, height)
    x2 = _clip(gx2 + pad, 0, width)
    y2 = _clip(gy2 + pad, 0, height)
    return image[y1:y2, x1:x2], [x1, y1, x2, y2]


def _isolated_group_image(
    image: np.ndarray,
    bar: Mapping[str, Any],
    group: Mapping[str, Any],
) -> tuple[np.ndarray, list[int], dict[str, Any]]:
    height, width = image.shape[:2]
    staff_height = float(bar["staff_height"])
    pad = max(1, int(round(ISOLATED_PAD_STAFF * staff_height)))
    gx1, gy1, gx2, gy2 = (int(v) for v in group["bbox"])
    x1 = _clip(gx1 - pad, 0, width)
    y1 = _clip(gy1 - pad, 0, height)
    x2 = _clip(gx2 + pad, 0, width)
    y2 = _clip(gy2 + pad, 0, height)
    crop = image[y1:y2, x1:x2]
    if crop is None or crop.size == 0:
        return crop, [x1, y1, x2, y2], {"foreground_fraction": 0.0}

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    horizontal_width = max(
        3,
        int(round(component_probe.DIGIT_REMOVE_HORIZONTAL_STAFF * staff_height)),
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_width, 1))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    cleaned = cv2.subtract(binary, horizontal)

    # Keep only foreground whose connected-component box intersects the original
    # selected group. This removes nearby notation that happens to fall inside the
    # padded OCR crop without consulting OCR output or expected values.
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(cleaned, 8)
    kept = np.zeros_like(cleaned)
    local_group = [gx1 - x1, gy1 - y1, gx2 - x1, gy2 - y1]
    kept_components = 0
    for label in range(1, count):
        cx, cy, cw, ch, _area = (int(v) for v in stats[label])
        cx2, cy2 = cx + cw, cy + ch
        intersects = not (
            cx2 <= local_group[0]
            or cx >= local_group[2]
            or cy2 <= local_group[1]
            or cy >= local_group[3]
        )
        if not intersects:
            continue
        kept[labels == label] = 255
        kept_components += 1

    canvas = np.full((kept.shape[0], kept.shape[1], 3), 255, dtype=np.uint8)
    canvas[kept > 0] = (0, 0, 0)
    foreground_fraction = float(np.count_nonzero(kept) / max(1, kept.size))
    return canvas, [x1, y1, x2, y2], {
        "kept_components": kept_components,
        "foreground_fraction": foreground_fraction,
    }


def _longest_vertical_run(mask: np.ndarray) -> int:
    if mask is None or mask.size == 0:
        return 0
    best = 0
    for column in range(mask.shape[1]):
        run = 0
        for value in mask[:, column]:
            if value:
                run += 1
                best = max(best, run)
            else:
                run = 0
    return int(best)


def _bar_shape_evidence(image: np.ndarray, bar: Mapping[str, Any]) -> dict[str, Any]:
    height, width = image.shape[:2]
    staff_height = float(bar["staff_height"])
    bx1, by1, bx2, by2 = (int(v) for v in bar["bbox"])
    center_y = (by1 + by2) / 2.0
    x_half = max(1, int(round(ENDCAP_X_HALF_STAFF * staff_height)))
    y_half = max(1, int(round(ENDCAP_Y_HALF_STAFF * staff_height)))

    def endpoint(cx: int) -> dict[str, Any]:
        x1 = _clip(cx - x_half, 0, width)
        x2 = _clip(cx + x_half, 0, width)
        y1 = _clip(round(center_y - y_half), 0, height)
        y2 = _clip(round(center_y + y_half), 0, height)
        crop = image[y1:y2, x1:x2]
        if crop is None or crop.size == 0:
            return {"bbox": [x1, y1, x2, y2], "ink_fraction": 0.0, "vertical_run_staff": 0.0}
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        return {
            "bbox": [x1, y1, x2, y2],
            "ink_fraction": float(np.count_nonzero(binary) / max(1, binary.size)),
            "vertical_run_staff": float(_longest_vertical_run(binary > 0) / staff_height),
        }

    return {
        "width_staff": float(bar["width_staff"]),
        "height_staff": float(bar["height_staff"]),
        "left_endpoint": endpoint(bx1),
        "right_endpoint": endpoint(bx2),
    }


def _group_trace(
    image: np.ndarray,
    bar: Mapping[str, Any],
    group: Mapping[str, Any],
    ocr: MMROCREngine,
) -> dict[str, Any]:
    original_img, original_bbox = _original_group_image(image, bar, group)
    isolated_img, isolated_bbox, isolated_debug = _isolated_group_image(
        image, bar, group
    )
    return {
        "group": dict(group),
        "original_bbox": original_bbox,
        "original": _run_ocr_image(
            original_img,
            staff_height=float(bar["staff_height"]),
            ocr=ocr,
        ),
        "isolated_bbox": isolated_bbox,
        "isolated_debug": isolated_debug,
        "isolated": _run_ocr_image(
            isolated_img,
            staff_height=float(bar["staff_height"]),
            ocr=ocr,
        ),
    }


def _trace_measure(
    image: np.ndarray,
    system: Mapping[str, Any],
    measure_bbox: list[int],
    ocr: MMROCREngine,
) -> dict[str, Any]:
    candidates_by_staff = []
    for staff_index, stave in enumerate(system.get("staves", [])):
        staff_bbox = [int(v) for v in stave["bbox"]]
        candidates_by_staff.append(
            component_probe._bar_candidates(image, measure_bbox, staff_bbox, staff_index)
        )
    clusters = component_probe._cluster_bars(candidates_by_staff, measure_bbox)

    cluster_traces = []
    original_skips: list[int] = []
    isolated_skips: list[int] = []
    for cluster_index, cluster in enumerate(clusters):
        bars = []
        for bar in cluster["bars"]:
            groups, component_debug = component_probe._component_groups(image, bar)
            group_traces = [
                _group_trace(image, bar, group, ocr)
                for group in groups[:MAX_GROUPS_PER_BAR]
            ]
            for trace in group_traces:
                original_skip = trace["original"]["skip"]
                isolated_skip = trace["isolated"]["skip"]
                if original_skip is not None:
                    original_skips.append(int(original_skip))
                if isolated_skip is not None:
                    isolated_skips.append(int(isolated_skip))
            bars.append(
                {
                    "staff": int(bar["staff"]),
                    "bar": dict(bar),
                    "shape": _bar_shape_evidence(image, bar),
                    "component_debug": component_debug,
                    "group_count": len(groups),
                    "groups": group_traces,
                }
            )
        cluster_traces.append(
            {
                "cluster_index": cluster_index,
                "cluster": dict(cluster),
                "bars": bars,
            }
        )

    selected = component_probe._anchored_measure(image, system, measure_bbox, ocr)
    return {
        "measure_bbox": measure_bbox,
        "bar_candidate_counts": [len(values) for values in candidates_by_staff],
        "cluster_count": len(clusters),
        "selected_policy": {
            "skip": selected["skip"],
            "selection_reason": selected["selection_reason"],
        },
        "original_candidate_skips": sorted(set(original_skips)),
        "isolated_candidate_skips": sorted(set(isolated_skips)),
        "clusters": cluster_traces,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    artifact_path = args.component_artifact.resolve()
    accepted_path = args.accepted_rebase_report.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / base.DEFAULT_MANIFEST_REL).resolve()
    )
    for path in (artifact_path, accepted_path, manifest_path, args.model.resolve()):
        if not path.is_file():
            raise FileNotFoundError(path)

    started = time.perf_counter()
    component_artifact = _load(artifact_path)
    selected_keys = _selected_keys(component_artifact)
    manifest = base._load_json(manifest_path)
    matrix_pages = base._load_matrix_pages(manifest, issue294_root)
    accepted_pages, accepted_provenance = full_probe._accepted_pages(accepted_path)
    specs = {str(spec.page_id): spec for spec in base.build_page_specs()}

    raw_ocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(raw_ocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDAExecutionProvider not confirmed: {providers}")
    counter = base.CountingOCR(raw_ocr)
    classifier = MMRClassifier(args.model, torch.device("cuda"))
    processor = MMRProcessor(
        args.model,
        torch.device("cuda"),
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=counter),
    )

    keys_by_page: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    source_by_key: dict[str, Mapping[str, Any]] = {}
    for item in selected_keys:
        key = str(item["key"])
        page_id, system_idx, measure_idx = _parse_key(key)
        keys_by_page[page_id].append((system_idx, measure_idx, key))
        source_by_key[key] = item

    events = []
    for page_id in sorted(keys_by_page):
        spec = specs[page_id]
        matrix_page = matrix_pages[(str(spec.score), str(spec.page_name))]
        page_data, image_path, support, mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        expected, _mappings = full_probe._rebase_expected(
            accepted_pages[page_id],
            page_data,
            global_page_index=int(spec.global_index),
        )
        systems = support["views"]["primary"]["pages"][0]["systems"]

        for system_idx, measure_idx, key in sorted(keys_by_page[page_id]):
            system = systems[system_idx]
            measure_bbox = [int(v) for v in system["measures"][measure_idx]["bbox"]]
            expected_skip = expected.get((system_idx, measure_idx))
            trace = _trace_measure(image, system, measure_bbox, processor.ocr)
            original_candidates = trace["original_candidate_skips"]
            isolated_candidates = trace["isolated_candidate_skips"]
            events.append(
                {
                    "key": key,
                    "page_id": page_id,
                    "system": system_idx,
                    "measure": measure_idx,
                    "expected_skip": expected_skip,
                    "was_all_variants_expected": bool(
                        source_by_key[key].get("all_variants_expected")
                    ),
                    "mapping_mode": mapping_mode,
                    "expected_seen_original": bool(
                        expected_skip is not None and expected_skip in original_candidates
                    ),
                    "expected_seen_isolated": bool(
                        expected_skip is not None and expected_skip in isolated_candidates
                    ),
                    **trace,
                }
            )

    return {
        "schema_version": "issue277.bar_digit_candidate_space.v1",
        "status": "completed",
        "diagnostic_only": True,
        "component_artifact": str(artifact_path),
        "accepted_rebase": accepted_provenance,
        "rapidocr_providers": providers,
        "contract": {
            "historical_a_geometry_used": False,
            "expected_values_used_for_selection": False,
            "production_source_modified": False,
            "native_candidate_geometry_only": True,
            "candidate_space_exhaustive_within_retained_bar_clusters": True,
        },
        "selected_key_count": len(events),
        "ocr_calls": counter.calls,
        "runtime_seconds": time.perf_counter() - started,
        "events": events,
    }


def summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    rows = []
    for event in payload["events"]:
        rows.append(
            {
                "key": event["key"],
                "expected_skip": event["expected_skip"],
                "control": event["was_all_variants_expected"],
                "policy_skip": event["selected_policy"]["skip"],
                "policy_reason": event["selected_policy"]["selection_reason"],
                "bar_candidate_counts": event["bar_candidate_counts"],
                "cluster_count": event["cluster_count"],
                "original_candidate_skips": event["original_candidate_skips"],
                "isolated_candidate_skips": event["isolated_candidate_skips"],
                "expected_seen_original": event["expected_seen_original"],
                "expected_seen_isolated": event["expected_seen_isolated"],
            }
        )
    return {
        "status": payload["status"],
        "output": str(output),
        "selected_key_count": payload["selected_key_count"],
        "ocr_calls": payload["ocr_calls"],
        "expected_seen_original_count": sum(
            1 for row in rows if row["expected_seen_original"]
        ),
        "expected_seen_isolated_count": sum(
            1 for row in rows if row["expected_seen_isolated"]
        ),
        "keys": rows,
        "runtime_seconds": payload["runtime_seconds"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--issue294-root",
        type=Path,
        default=base.DEFAULT_ISSUE294_ROOT,
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--component-artifact", type=Path, required=True)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=base.DEFAULT_MODEL)
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
