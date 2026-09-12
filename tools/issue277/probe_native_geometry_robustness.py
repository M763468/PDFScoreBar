#!/usr/bin/env python3
"""Probe Issue #277 MMR robustness on maintained-HOMR candidate-native geometry.

Experiment-only diagnostic. It reuses retained Issue #294 detector/HOMR/SR/OMR
artifacts, reconstructs the maintained-B candidate-native numbering/support view
with the retained mapping-guarded grouping experiment, and reruns only the current
MMR classifier/RapidOCR path on the five required #277 controls.

The probe never consumes historical-A/frozen-A geometry. Expected fixture values
are used only to label observations after OCR; they do not affect view generation
or result selection.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import cv2
import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.connector_aware_builder import ConnectorAwareSystemBuilder
from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Staff, System
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from tools.issue264.run_phase_c_mmr_regression import build_page_specs

DEFAULT_ISSUE294_ROOT = Path("/home/masaki_muramatsu/ws_PDFScoreBar_issue294")
DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
DEFAULT_MANIFEST_REL = Path("logs/issue294/issue294_full68_refresh_02/full68_host.json")
TARGETS = (
    ("page_002", 3, 1),
    ("page_002", 5, 2),
    ("page_022", 0, 0),
    ("page_034", 2, 0),
    ("page_042", 8, 0),
)
MICRO_FRACTION = 0.0025


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _capture(command: list[str]) -> str:
    return subprocess.check_output(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def _git_provenance() -> dict[str, str]:
    return {
        "head": _capture(["git", "rev-parse", "HEAD"]),
        "branch": _capture(["git", "branch", "--show-current"]) or "<detached>",
    }


def _resolve_retained_path(value: str | Path, issue294_root: Path) -> Path:
    raw = Path(value)
    if raw.is_file():
        return raw.resolve()

    candidates: list[Path] = []
    if not raw.is_absolute():
        candidates.append(issue294_root / raw)

    text = str(raw)
    if "/workspace/" in text:
        candidates.append(issue294_root / text.split("/workspace/", 1)[1])

    parts = raw.parts
    for marker in ("ws_PDFScoreBar_issue294", "ws_PDFScoreBar"):
        if marker in parts:
            index = parts.index(marker)
            candidates.append(issue294_root.joinpath(*parts[index + 1 :]))

    if "logs" in parts:
        index = parts.index("logs")
        candidates.append(issue294_root.joinpath(*parts[index:]))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(f"Unable to resolve retained #294 path: {raw}")


def _latest_focused(issue294_root: Path) -> Path:
    candidates = sorted(
        issue294_root.glob("logs/issue294/**/issue294_post277_focused_*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        candidates = sorted(
            issue294_root.glob("logs/issue294/issue294_post277_focused_*.json"),
            key=lambda path: path.stat().st_mtime,
        )
    if not candidates:
        raise FileNotFoundError(
            f"No retained issue294_post277_focused_*.json under {issue294_root / 'logs/issue294'}"
        )
    return candidates[-1].resolve()


def _load_matrix_pages(
    manifest: Mapping[str, Any], issue294_root: Path
) -> dict[tuple[str, str], Mapping[str, Any]]:
    pages: dict[tuple[str, str], Mapping[str, Any]] = {}
    chunks = manifest.get("completed_chunks")
    if not isinstance(chunks, list):
        raise ValueError("Full68 manifest lacks completed_chunks")
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            raise ValueError("Malformed completed chunk")
        report_path = _resolve_retained_path(str(chunk["matrix_report"]), issue294_root)
        report = _load_json(report_path)
        report_pages = report.get("pages") if isinstance(report, Mapping) else None
        if not isinstance(report_pages, list):
            raise ValueError(f"Matrix report lacks pages: {report_path}")
        for page in report_pages:
            if not isinstance(page, Mapping):
                raise ValueError(f"Malformed matrix page: {report_path}")
            image = Path(str(page["image"]))
            key = (image.parent.name, image.stem)
            if key in pages:
                raise RuntimeError(f"Duplicate full68 matrix page: {key}")
            pages[key] = page
    if len(pages) != 68:
        raise RuntimeError(f"Expected 68 matrix pages, got {len(pages)}")
    return pages


def _vertical_iou(left: Staff, right: Staff) -> float:
    intersection = max(
        0,
        min(left.bbox.y2, right.bbox.y2) - max(left.bbox.y1, right.bbox.y1),
    )
    union = max(left.bbox.y2, right.bbox.y2) - min(left.bbox.y1, right.bbox.y1)
    return float(intersection / union) if union > 0 else 0.0


def _best_index(source: Staff, candidates: list[Staff]) -> tuple[int | None, float]:
    if not candidates:
        return None, 0.0
    scored = [
        (_vertical_iou(source, candidate), index)
        for index, candidate in enumerate(candidates)
    ]
    best_iou, best_index = max(scored, key=lambda item: (item[0], -item[1]))
    return best_index, best_iou


def _identity_mapping_reliable(geometry_staves: list[Staff], evidence_staves: list[Staff]) -> bool:
    if len(geometry_staves) != len(evidence_staves) or not geometry_staves:
        return False
    for index, (geometry, evidence) in enumerate(zip(geometry_staves, evidence_staves)):
        if _vertical_iou(geometry, evidence) <= 0.0:
            return False
        geometry_best, _ = _best_index(geometry, evidence_staves)
        evidence_best, _ = _best_index(evidence, geometry_staves)
        if geometry_best != index or evidence_best != index:
            return False
    return True


class ConnectorPositiveWithinDistanceBuilder(ConnectorAwareSystemBuilder):
    """Retained #294 experiment rule needed to reconstruct B candidate topology."""

    def _group_by_geometry(
        self,
        staves: List[Staff],
        image: Optional[np.ndarray],
        connector_evidence: Optional[Dict[Any, Any]] = None,
    ) -> List[System]:
        if not staves:
            return []

        connector_by_pair = self._normalize_connector_evidence(connector_evidence)
        parent = list(range(len(staves)))

        def find(index: int) -> int:
            if parent[index] != index:
                parent[index] = find(parent[index])
            return parent[index]

        def union(left: int, right: int) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        heights = [staff.bbox.height for staff in staves]
        avg_height = sum(heights) / len(heights) if heights else 100.0

        for index in range(len(staves) - 1):
            s1, s2 = staves[index], staves[index + 1]
            gap = s2.bbox.y1 - s1.bbox.y2
            within_distance = gap <= avg_height * self.DIVISI_DIST_RATIO
            within_rescue = gap <= avg_height * self.CONNECTOR_RESCUE_DIST_RATIO
            aligned_pairs = self._find_aligned_pairs(s1, s2)
            pair_evidence = connector_by_pair.get((index, index + 1))
            explicit = pair_evidence is not None
            left_present = self._has_left_connector_evidence(pair_evidence)

            if not within_distance and not (left_present and within_rescue):
                continue
            if explicit and not left_present:
                continue
            if left_present and within_distance:
                union(index, index + 1)
                continue

            if image is not None:
                if self._check_aligned_connection(s1, s2, aligned_pairs, image) and within_distance:
                    union(index, index + 1)
                    continue
                if (
                    left_present
                    and within_rescue
                    and len(aligned_pairs) >= self.CONNECTOR_RESCUE_MIN_ALIGN_COUNT
                ):
                    union(index, index + 1)
                    continue

            if image is None:
                if within_distance and len(aligned_pairs) >= self.MIN_ALIGN_COUNT:
                    union(index, index + 1)
                elif (
                    left_present
                    and within_rescue
                    and len(aligned_pairs) >= self.CONNECTOR_RESCUE_MIN_ALIGN_COUNT
                ):
                    union(index, index + 1)

        groups: Dict[int, List[Staff]] = {}
        for index in range(len(staves)):
            groups.setdefault(find(index), []).append(staves[index])
        return [
            System(staves=groups[root])
            for root in sorted(groups, key=lambda key: groups[key][0].bbox.y1)
        ]


class MappingGuardedConnectorPositivePipeline(MeasureNumberingPipeline):
    """Retained #294 candidate reconstruction; not a proposed #277 production change."""

    def __init__(self) -> None:
        super().__init__()
        self.builder = ConnectorPositiveWithinDistanceBuilder()
        self.last_evidence_geometry_mode = "unresolved"

    def _connector_evidence_staves(
        self,
        geometry_staves: list[Staff],
        staff_mask_path: Path,
        image_size: tuple[int, int],
        connector_mask_paths: Optional[Mapping[str, Path | str]],
    ) -> list[Staff]:
        semantic_staves = super()._connector_evidence_staves(
            geometry_staves,
            staff_mask_path,
            image_size,
            connector_mask_paths,
        )
        if semantic_staves is geometry_staves:
            self.last_evidence_geometry_mode = "geometry_existing_fallback"
            return geometry_staves
        if not _identity_mapping_reliable(geometry_staves, semantic_staves):
            self.last_evidence_geometry_mode = "geometry_mapping_guard_fallback"
            return geometry_staves
        self.last_evidence_geometry_mode = "semantic_identity_mapped"
        return semantic_staves


class CountingOCR:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        return self.engine(*args, **kwargs)


def _result(value: tuple[Any, Any, Any, Any]) -> dict[str, Any]:
    number, score, debug, evidence = value
    return {
        "number": None if number is None else int(number),
        "skip": None if number is None else int(number) - 1,
        "score": float(score),
        "debug": str(debug),
        "one_bar_evidence": int(evidence),
    }


def _pair(value: tuple[Any, Any]) -> dict[str, Any]:
    number, score = value
    return {
        "number": None if number is None else int(number),
        "skip": None if number is None else int(number) - 1,
        "score": float(score),
    }


def _measured(counter: CountingOCR, func: Any) -> tuple[Any, dict[str, Any]]:
    before = counter.calls
    started = time.perf_counter()
    value = func()
    return value, {
        "ocr_calls": counter.calls - before,
        "seconds": time.perf_counter() - started,
    }


def _bbox(payload: Mapping[str, Any], system_idx: int, measure_idx: int) -> list[int]:
    measure = payload["pages"][0]["systems"][system_idx]["measures"][measure_idx]
    return [int(value) for value in measure["bbox"]]


def _clip_bbox(bbox: list[int], width: int, height: int) -> list[int] | None:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(width - 1, int(x1)))
    x2 = max(1, min(width, int(x2)))
    y1 = max(0, min(height - 1, int(y1)))
    y2 = max(1, min(height, int(y2)))
    if x2 - x1 <= 1 or y2 - y1 <= 1:
        return None
    return [x1, y1, x2, y2]


def _micro_variants(bbox: list[int], width: int, height: int) -> dict[str, list[int]]:
    x1, y1, x2, y2 = bbox
    dx = max(1, int(round(max(1, x2 - x1) * MICRO_FRACTION)))
    raw = {
        "native": [x1, y1, x2, y2],
        "left_in": [x1 + dx, y1, x2, y2],
        "right_in": [x1, y1, x2 - dx, y2],
        "symmetric_in": [x1 + dx, y1, x2 - dx, y2],
        "symmetric_out": [x1 - dx, y1, x2 + dx, y2],
        "translate_left": [x1 - dx, y1, x2 - dx, y2],
        "translate_right": [x1 + dx, y1, x2 + dx, y2],
    }
    return {
        name: clipped
        for name, candidate in raw.items()
        if (clipped := _clip_bbox(candidate, width, height)) is not None
    }


def _expected_map(focused: Mapping[str, Any]) -> dict[tuple[str, int, int], int]:
    variants = focused.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("Focused #294 artifact lacks variants")
    candidate = variants.get("B_b377_mapping_guarded")
    if not isinstance(candidate, Mapping):
        b_candidates = [
            value
            for key, value in variants.items()
            if str(key).startswith("B_") and isinstance(value, Mapping)
        ]
        if len(b_candidates) != 1:
            raise ValueError("Unable to identify maintained-B focused variant")
        candidate = b_candidates[0]
    result: dict[tuple[str, int, int], int] = {}
    for page in candidate.get("pages", []):
        page_id = str(page["page_id"])
        for item in page.get("expected", []):
            result[(page_id, int(item["system"]), int(item["measure"]))] = int(item["skip"])
    return result


def _build_candidate_page(
    spec: Any,
    matrix_page: Mapping[str, Any],
    issue294_root: Path,
) -> tuple[dict[str, Any], Path, dict[str, Any], str]:
    variant = matrix_page["modes"]["candidate_native_geometry"]["variants"]["B_b377"]
    fixed_support = _load_json(
        _resolve_retained_path(str(matrix_page["fixed_inputs"]["support_result"]), issue294_root)
    )
    image = _resolve_retained_path(str(matrix_page["image"]), issue294_root)
    image_data = cv2.imread(str(image))
    if image_data is None:
        raise FileNotFoundError(image)
    height, width = image_data.shape[:2]

    pipeline = MappingGuardedConnectorPositivePipeline()
    score = pipeline.run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(
                    _resolve_retained_path(str(variant["staff_mask"]), issue294_root)
                ),
                "image_size": (width, height),
                "page_number": int(spec.global_index) + 1,
                "connector_mask_paths": {
                    "symbols": str(
                        _resolve_retained_path(
                            str(fixed_support["connector_symbols"]), issue294_root
                        )
                    ),
                    "brace_dot": str(
                        _resolve_retained_path(
                            str(fixed_support["connector_brace_dot"]), issue294_root
                        )
                    ),
                },
            }
        ]
    )
    base = score_to_dict(score)
    support = build_mmr_support_data(
        base,
        _resolve_retained_path(
            str(fixed_support["current_homr_staff_mask"]),
            issue294_root,
        ),
    )
    return base, image, support, pipeline.last_evidence_geometry_mode


def _cnn_probability(
    processor: MMRProcessor,
    image: np.ndarray,
    bbox: list[int],
) -> float:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox
    margin = 20
    crop = image[
        max(0, y1 - margin) : min(height, y2 + margin),
        max(0, x1 - margin) : min(width, x2 + margin),
    ]
    return float(processor.classifier.predict(crop))


def _view_consistency(
    views: Mapping[str, Mapping[str, Any]], expected_skip: int | None
) -> dict[str, Any]:
    valid = [
        (name, value)
        for name, value in views.items()
        if value["result"].get("skip") is not None
    ]
    counts = Counter(int(value["result"]["skip"]) for _name, value in valid)
    majority_skip = None
    majority_support = 0
    if counts:
        majority_support = max(counts.values())
        leaders = [skip for skip, count in counts.items() if count == majority_support]
        if len(leaders) == 1:
            majority_skip = leaders[0]

    max_score = None
    if valid:
        name, value = max(
            valid,
            key=lambda item: (float(item[1]["result"]["score"]), item[0]),
        )
        max_score = {
            "view": name,
            "skip": int(value["result"]["skip"]),
            "score": float(value["result"]["score"]),
        }

    return {
        "valid_view_count": len(valid),
        "skip_counts": {str(skip): count for skip, count in sorted(counts.items())},
        "majority_skip": majority_skip,
        "majority_support": majority_support,
        "majority_fraction": (
            float(majority_support / len(valid)) if valid else 0.0
        ),
        "expected_skip": expected_skip,
        "expected_support": (
            counts.get(int(expected_skip), 0) if expected_skip is not None else None
        ),
        "max_score": max_score,
        "max_score_disagrees_with_majority": bool(
            max_score is not None
            and majority_skip is not None
            and int(max_score["skip"]) != int(majority_skip)
        ),
    }


def _targeted_staff_trace(
    processor: MMRProcessor,
    counter: CountingOCR,
    image: np.ndarray,
    system: Mapping[str, Any],
    bbox: list[int],
) -> dict[str, Any]:
    height, width = image.shape[:2]
    full: list[dict[str, Any]] = []
    shifted: list[dict[str, Any]] = []

    for stave in system.get("staves", []):
        value, metrics = _measured(
            counter,
            lambda stave=stave: processor._run_targeted_full_span_staff(
                image, bbox, stave["bbox"], width, height
            ),
        )
        full.append({"result": _pair(value), **metrics})

    shifted_bbox = processor._targeted_shift_x1(bbox)
    if shifted_bbox[0] != bbox[0]:
        for stave in system.get("staves", []):
            value, metrics = _measured(
                counter,
                lambda stave=stave: processor._run_targeted_shifted_staff(
                    image, shifted_bbox, stave["bbox"], width, height
                ),
            )
            shifted.append({"result": _pair(value), **metrics})

    full_values = [
        (item["result"]["number"], item["result"]["score"])
        for item in full
    ]
    shifted_values = [
        (item["result"]["number"], item["result"]["score"])
        for item in shifted
    ]
    return {
        "full_span": {
            "staff_results": full,
            "aggregate": _pair(processor._aggregate_targeted_staff_results(full_values)),
        },
        "shifted_bbox": shifted_bbox,
        "shifted": {
            "staff_results": shifted,
            "aggregate": _pair(processor._aggregate_targeted_staff_results(shifted_values)),
        },
    }


def _run_shifted_ablation_staff(
    processor: MMRProcessor,
    counter: CountingOCR,
    image: np.ndarray,
    measure_bbox: list[int],
    staff_bbox: list[int],
    *,
    crop_geometry: str,
    mask_geometry: str,
    preprocess_geometry: str,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    x1, _y1, x2, _y2 = (int(value) for value in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (int(value) for value in staff_bbox)
    staff_height = max(1.0, float(sy2 - sy1))

    if crop_geometry == "legacy_fixed":
        margin_x = 30
        margin_y = 80
    elif crop_geometry == "staff_relative":
        margin_x = int(round(staff_height * processor.TARGETED_SHIFTED_X_MARGIN_STAFF_RATIO))
        margin_y = int(round(staff_height * processor.TARGETED_SHIFTED_Y_MARGIN_STAFF_RATIO))
    else:
        raise ValueError(crop_geometry)

    ox1 = max(0, min(width, x1 - margin_x))
    ox2 = max(0, min(width, x2 + margin_x))
    oy1 = max(0, min(height, sy1 - margin_y))
    oy2 = max(0, min(height, sy2 + margin_y))
    crop = image[oy1:oy2, ox1:ox2]
    staff_top_rel = float(sy1 - oy1)
    if crop is None or crop.size == 0:
        return {"result": _pair((None, 0.0)), "ocr_calls": 0, "seconds": 0.0}

    if mask_geometry == "legacy":
        crop = processor.ocr.mask_hbar_candidates(crop, staff_top_rel, staff_height)
    elif mask_geometry == "staff_relative":
        if getattr(processor.ocr, "supports_staff_relative_hbar_geometry", False):
            crop = processor.ocr.mask_hbar_candidates(crop, staff_top_rel, staff_height, True)
        else:
            crop = processor.ocr.mask_hbar_candidates(crop, staff_top_rel, staff_height)
    else:
        raise ValueError(mask_geometry)

    if crop is None or crop.size == 0:
        return {"result": _pair((None, 0.0)), "ocr_calls": 0, "seconds": 0.0}

    if preprocess_geometry == "legacy":
        processed = processor.ocr.preprocess_variant(crop, mode="no_dilate", angle=0)
    elif preprocess_geometry == "staff_relative":
        if getattr(processor.ocr, "supports_staff_relative_preprocess_geometry", False):
            processed = processor.ocr.preprocess_variant(
                crop,
                mode="no_dilate",
                angle=0,
                staff_height=staff_height,
                use_staff_relative_geometry=True,
            )
        else:
            processed = processor.ocr.preprocess_variant(crop, mode="no_dilate", angle=0)
    else:
        raise ValueError(preprocess_geometry)

    if processed is None or processed.size == 0:
        return {"result": _pair((None, 0.0)), "ocr_calls": 0, "seconds": 0.0}

    def run_ocr() -> tuple[Optional[int], float]:
        ocr_result, _ = processor.ocr.ocr_engine(processed)
        number, score, _debug = processor.ocr.select_best_candidate(
            ocr_result or [],
            processed.shape[1],
            processed.shape[0],
        )
        if number is None or number < 2:
            return None, 0.0
        return int(number), float(score)

    value, metrics = _measured(counter, run_ocr)
    return {
        "crop_geometry": crop_geometry,
        "mask_geometry": mask_geometry,
        "preprocess_geometry": preprocess_geometry,
        "crop_bbox": [ox1, oy1, ox2, oy2],
        "staff_height": staff_height,
        "staff_top_rel": staff_top_rel,
        "result": _pair(value),
        **metrics,
    }


def _page034_ablation(
    processor: MMRProcessor,
    counter: CountingOCR,
    image: np.ndarray,
    system: Mapping[str, Any],
    bbox: list[int],
) -> dict[str, Any]:
    shifted_bbox = processor._targeted_shift_x1(bbox)
    configs = [
        (crop, mask, preprocess)
        for crop in ("legacy_fixed", "staff_relative")
        for mask in ("legacy", "staff_relative")
        for preprocess in ("legacy", "staff_relative")
    ]
    results: dict[str, Any] = {}
    for crop, mask, preprocess in configs:
        key = f"crop={crop}|mask={mask}|preprocess={preprocess}"
        staff_results = [
            _run_shifted_ablation_staff(
                processor,
                counter,
                image,
                shifted_bbox,
                [int(value) for value in stave["bbox"]],
                crop_geometry=crop,
                mask_geometry=mask,
                preprocess_geometry=preprocess,
            )
            for stave in system.get("staves", [])
        ]
        values = [
            (item["result"]["number"], item["result"]["score"])
            for item in staff_results
        ]
        results[key] = {
            "staff_results": staff_results,
            "aggregate": _pair(processor._aggregate_targeted_staff_results(values)),
        }
    return {
        "shifted_bbox": shifted_bbox,
        "factorial": results,
        "note": (
            "legacy_fixed+legacy+legacy isolates the pre-review retry family; "
            "other cells separate crop, mask, and preprocess geometry."
        ),
    }


def _trace_event(
    processor: MMRProcessor,
    counter: CountingOCR,
    image: np.ndarray,
    support: Mapping[str, Any],
    system_idx: int,
    measure_idx: int,
    expected_skip: int | None,
    include_page034_ablation: bool,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    primary = support["views"]["primary"]
    system = primary["pages"][0]["systems"][system_idx]
    bbox = _bbox(primary, system_idx, measure_idx)
    probability = _cnn_probability(processor, image, bbox)

    baseline_raw, baseline_metrics = _measured(
        counter,
        lambda: processor._detect_number_with_evidence_once(
            image, system, *bbox, probability, width, height
        ),
    )
    policy_raw, policy_metrics = _measured(
        counter,
        lambda: processor._detect_number_with_evidence(
            image, system, *bbox, probability, width, height
        ),
    )
    baseline = _result(baseline_raw)
    policy = _result(policy_raw)

    views: dict[str, Any] = {}
    for name, view_bbox in _micro_variants(bbox, width, height).items():
        view_probability = _cnn_probability(processor, image, view_bbox)
        raw, metrics = _measured(
            counter,
            lambda view_bbox=view_bbox, view_probability=view_probability: (
                processor._detect_number_with_evidence(
                    image,
                    system,
                    *view_bbox,
                    view_probability,
                    width,
                    height,
                )
            ),
        )
        views[name] = {
            "bbox": view_bbox,
            "probability": view_probability,
            "result": _result(raw),
            "matches_expected": (
                expected_skip is not None and _result(raw)["skip"] == expected_skip
            ),
            **metrics,
        }

    payload: dict[str, Any] = {
        "bbox": bbox,
        "staff_bboxes": [
            [int(value) for value in stave["bbox"]]
            for stave in system.get("staves", [])
        ],
        "probability": probability,
        "reaches_ocr_in_production": probability > processor.rescue_threshold,
        "expected_skip": expected_skip,
        "baseline": {
            "result": baseline,
            "matches_expected": expected_skip is not None and baseline["skip"] == expected_skip,
            **baseline_metrics,
        },
        "score_short_circuit": bool(
            baseline["number"] is not None
            and baseline["score"] > processor.JITTER_SCORE_TRIGGER
        ),
        "current_policy": {
            "result": policy,
            "matches_expected": expected_skip is not None and policy["skip"] == expected_skip,
            **policy_metrics,
        },
        "targeted_staff_trace": _targeted_staff_trace(
            processor,
            counter,
            image,
            system,
            bbox,
        ),
        "micro_fraction": MICRO_FRACTION,
        "micro_views": views,
        "micro_consistency": _view_consistency(views, expected_skip),
    }
    if include_page034_ablation:
        payload["page034_shifted_geometry_ablation"] = _page034_ablation(
            processor,
            counter,
            image,
            system,
            bbox,
        )
    return payload


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / DEFAULT_MANIFEST_REL).resolve()
    )
    focused_path = (
        args.focused_artifact.resolve()
        if args.focused_artifact is not None
        else _latest_focused(issue294_root)
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not focused_path.is_file():
        raise FileNotFoundError(focused_path)
    if not args.model.is_file():
        raise FileNotFoundError(args.model)

    started = time.perf_counter()
    manifest = _load_json(manifest_path)
    matrix_pages = _load_matrix_pages(manifest, issue294_root)
    expected = _expected_map(_load_json(focused_path))
    specs = {str(spec.page_id): spec for spec in build_page_specs()}

    raw_ocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(raw_ocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDAExecutionProvider not confirmed: {providers}")
    counting_ocr = CountingOCR(raw_ocr)
    processor = MMRProcessor(
        args.model,
        torch.device("cuda"),
        classifier=MMRClassifier(args.model, torch.device("cuda")),
        ocr_engine=MMROCREngine(ocr_engine=counting_ocr),
    )

    targets_by_page: dict[str, list[tuple[int, int]]] = {}
    for page_id, system_idx, measure_idx in TARGETS:
        targets_by_page.setdefault(page_id, []).append((system_idx, measure_idx))

    pages: dict[str, Any] = {}
    for page_id, keys in targets_by_page.items():
        spec = specs.get(page_id)
        if spec is None:
            raise KeyError(f"build_page_specs lacks {page_id}")
        matrix_page = matrix_pages.get((str(spec.score), str(spec.page_name)))
        if matrix_page is None:
            raise KeyError(f"Matrix lacks {page_id}: {(spec.score, spec.page_name)}")

        base, image_path, support, mapping_mode = _build_candidate_page(
            spec,
            matrix_page,
            issue294_root,
        )
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)

        events: list[dict[str, Any]] = []
        for system_idx, measure_idx in keys:
            event_expected = expected.get((page_id, system_idx, measure_idx))
            trace = _trace_event(
                processor,
                counting_ocr,
                image,
                support,
                system_idx,
                measure_idx,
                event_expected,
                include_page034_ablation=(
                    page_id == "page_034" and system_idx == 2 and measure_idx == 0
                ),
            )
            events.append(
                {
                    "system": system_idx,
                    "measure": measure_idx,
                    **trace,
                }
            )

        pages[page_id] = {
            "score": str(spec.score),
            "page_name": str(spec.page_name),
            "image": str(image_path),
            "mapping_mode": mapping_mode,
            "numbering_system_count": len(base["pages"][0].get("systems", [])),
            "events": events,
        }

    return {
        "schema_version": "issue277.native_geometry_robustness_probe.v1",
        "status": "completed",
        "diagnostic_only": True,
        "git": _git_provenance(),
        "retained_issue294": {
            "root": str(issue294_root),
            "manifest": str(manifest_path),
            "focused_artifact": str(focused_path),
        },
        "model": str(args.model.resolve()),
        "rapidocr_providers": providers,
        "targets": [
            {"page_id": page_id, "system": system_idx, "measure": measure_idx}
            for page_id, system_idx, measure_idx in TARGETS
        ],
        "contract": {
            "historical_a_geometry_used": False,
            "frozen_a_geometry_used": False,
            "expected_values_used_for_selection": False,
            "threshold_changes": False,
            "production_source_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "numbering_reconstructed_from_candidate_native_b": True,
            "cnn_ocr_mmr_reexecuted": True,
            "rapidocr_cuda_required": True,
        },
        "ocr_calls_total": counting_ocr.calls,
        "runtime_seconds": time.perf_counter() - started,
        "pages": pages,
    }


def _summary(payload: Mapping[str, Any], output: Path) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for page_id, page in payload["pages"].items():
        for event in page["events"]:
            consistency = event["micro_consistency"]
            events.append(
                {
                    "key": f"{page_id} s{event['system']} m{event['measure']}",
                    "expected_skip": event["expected_skip"],
                    "baseline_skip": event["baseline"]["result"]["skip"],
                    "baseline_score": event["baseline"]["result"]["score"],
                    "current_policy_skip": event["current_policy"]["result"]["skip"],
                    "score_short_circuit": event["score_short_circuit"],
                    "micro_majority_skip": consistency["majority_skip"],
                    "micro_majority_support": consistency["majority_support"],
                    "micro_valid_views": consistency["valid_view_count"],
                    "micro_max_score": consistency["max_score"],
                    "max_score_disagrees_with_majority": consistency[
                        "max_score_disagrees_with_majority"
                    ],
                }
            )
    return {
        "status": payload["status"],
        "output": str(output),
        "rapidocr_providers": payload["rapidocr_providers"],
        "ocr_calls_total": payload["ocr_calls_total"],
        "runtime_seconds": payload["runtime_seconds"],
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue294-root",
        type=Path,
        default=DEFAULT_ISSUE294_ROOT,
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--focused-artifact", type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        args.output = PROJECT_ROOT / "logs/issue277" / f"native_geometry_probe_{stamp}.json"
    else:
        args.output = args.output.resolve()

    try:
        payload = run(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as error:  # noqa: BLE001
        failure = {
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
        }
        print(json.dumps(failure, ensure_ascii=False))
        return 1

    print(json.dumps(_summary(payload, args.output), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
