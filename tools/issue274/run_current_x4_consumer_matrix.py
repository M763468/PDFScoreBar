#!/usr/bin/env python3
"""Issue #274 focused current-x4 consumer matrix.

This experiment asks whether the retained current-x4 HOMR result (B) can replace
pinned-x4 HOMR (C) once PDFScoreBar's downstream evidence/topology contracts are
made explicit.

Heavy producer work is NOT rerun.  The matrix reuses retained A/B/C/OMR artifacts
and reruns only PDFScoreBar-owned dense probe/filter/CNN consumers on four focused
pages.

Axes:
- x4 support: legacy symmetric IoU vs directional staff-slot evidence;
- dense existing-box suppression: legacy vs one-existing-box/one-band vs disabled;
- clef artifact: retained C clef vs no clef.

The disabled-suppression cells are causal upper bounds, not production proposals.
The one-box/one-band implementation is experiment-local: production source is not
patched by this tool.
"""
from __future__ import annotations

import argparse
import csv
import inspect
import json
import shutil
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np
import torch
import yaml

from src.common import Box, barline_iou
from src.common.barline_evaluation import greedy_barline_match, is_barline_match
from src.pipeline.detection.config import get_cnn_apply_nms, get_probe_kwargs
from src.pipeline.probe_detector import detect_probe_scan as production_detect_probe_scan
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.candidate_filters import (
    filter_probe_candidates,
    split_box_vertically,
    trim_box_to_ink,
)
from src.pipeline.steps.cnn_scoring import (
    GPUNormalize,
    MEAN,
    STD,
    _load_model,
    _resolve_model_path,
    _score_directory,
)
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from src.pipeline.steps.probe_scan import (
    _augment_unit_normalized_boxes,
    _build_clef_mask_map,
    _estimate_unit_size_from_existing_boxes,
    _extract_candidate_postprocess_cfg,
    _resolve_scale_aware_probe_kwargs,
)
from src.pipeline.utils.wide_split_utils import split_wide_candidates
from tools.issue120.eval_full68_from_intermediates import boxes_from_gt
from tools.issue274.analyze_x4_support_contract import (
    directional_support,
    has_iou_support,
    phase_a_slots,
    to_workspace,
)

ROOT = Path(__file__).resolve().parents[2]
AB_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
    "issue274_homr_x4_stage_e_ab.json"
)
RESIDUAL_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
    "residual_trace_01/issue274_homr_x4_stage_e_residual_trace.json"
)
CONFIG_DEFAULT = Path("configs/dense_full_pipeline.yaml")
OUT_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/current_x4_consumer_matrix_01"
)

FOCUSED_CASES = (
    ("Shostakovich-Sym5-Va", "page_013"),
    ("Shostakovich-Sym5-Va", "page_015"),
    ("Sibelius-Violin_Concerto-Viola", "page_004"),
    ("Va_Prokofiev_Symphony1", "page_004"),
)

MATRIX = (
    {
        "name": "control_c_iou_legacy_retained_c_clef",
        "support": "c_iou",
        "suppression": "legacy",
        "clef": "retained_c",
    },
    {
        "name": "control_c_iou_legacy_no_clef",
        "support": "c_iou",
        "suppression": "legacy",
        "clef": "none",
    },
    {
        "name": "b_iou_legacy_retained_c_clef",
        "support": "b_iou",
        "suppression": "legacy",
        "clef": "retained_c",
    },
    {
        "name": "b_directional_legacy_retained_c_clef",
        "support": "b_directional",
        "suppression": "legacy",
        "clef": "retained_c",
    },
    {
        "name": "b_iou_best_band_retained_c_clef",
        "support": "b_iou",
        "suppression": "best_band",
        "clef": "retained_c",
    },
    {
        "name": "b_directional_best_band_retained_c_clef",
        "support": "b_directional",
        "suppression": "best_band",
        "clef": "retained_c",
    },
    {
        "name": "b_iou_suppression_disabled_retained_c_clef",
        "support": "b_iou",
        "suppression": "disabled",
        "clef": "retained_c",
    },
    {
        "name": "b_directional_suppression_disabled_retained_c_clef",
        "support": "b_directional",
        "suppression": "disabled",
        "clef": "retained_c",
    },
    {
        "name": "b_iou_best_band_no_clef",
        "support": "b_iou",
        "suppression": "best_band",
        "clef": "none",
    },
    {
        "name": "b_directional_best_band_no_clef",
        "support": "b_directional",
        "suppression": "best_band",
        "clef": "none",
    },
)

OWNERSHIP = {
    "retained_A_B_C_homr_artifacts": "upstream_homr_data_via_pdfscore_orchestration",
    "retained_OMR": "external_omr_dln_not_homr",
    "iou_consensus": "pdfscore_extension",
    "directional_staff_slot_support": "pdfscore_extension_experimental",
    "dense_probe": "pdfscore_extension",
    "existing_box_suppression": "pdfscore_extension",
    "best_band_suppression": "pdfscore_extension_experimental",
    "candidate_filters": "pdfscore_extension",
    "barline_cnn": "pdfscore_extension",
    "retained_c_clef_pixels": "upstream_homr_data",
    "clef_artifact_discovery_and_handoff": "pdfscore_upstream_orchestration",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def norm_box(values: Sequence[Any]) -> Box:
    return tuple(int(round(float(value))) for value in values[:4])  # type: ignore[return-value]


def read_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Config is not a mapping: {path}")
    detection = payload.get("detection")
    if not isinstance(detection, Mapping):
        raise ValueError(f"Config lacks detection mapping: {path}")
    return dict(detection)


def find_ab_record(
    ab: Mapping[str, Any], score: str, page: str
) -> Mapping[str, Any]:
    for record in ab["hybrid_ab"]["pages"]:
        if record.get("score") == score and record.get("page") == page:
            return record
    raise KeyError(f"AB record not found: {score}/{page}")


def canonical_image(workspace: Path, score: str, page: str) -> Path:
    candidates = (
        workspace / "data/evaluation2/images" / score / f"{page}.png",
        workspace / "data/evaluation2/images" / score / page / f"{page}.png",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"Canonical image not found: {score}/{page}")


def canonical_gt(workspace: Path, score: str, page: str) -> Path:
    path = workspace / "data/evaluation2/annotations" / score / page / "boxes_sorted.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def discover_retained_c_clef(c_path: Path, page: str) -> Path | None:
    # Use the same filename resolution helper as production probe orchestration.
    mapping = _build_clef_mask_map(c_path.parent)
    path = mapping.get(page)
    if path is not None and path.is_file():
        return path
    # Some retained trees put debug files one level above/below the detection JSON.
    for root in (c_path.parent.parent, c_path.parent.parent.parent):
        mapping = _build_clef_mask_map(root)
        path = mapping.get(page)
        if path is not None and path.is_file():
            return path
    return None


def load_clef_mask(path: Path | None, shape: tuple[int, int]) -> np.ndarray:
    if path is None:
        return np.zeros(shape, dtype=np.uint8)
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise RuntimeError(f"Failed to read clef mask: {path}")
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return mask


def build_hybrid(
    *,
    a_boxes: list[Box],
    b_boxes: list[Box],
    c_boxes: list[Box],
    omr_boxes: list[Box],
    support_policy: str,
    iou_threshold: float,
    directional_alpha: float,
    directional_gamma: float,
    directional_fallback: float,
) -> tuple[list[Box], list[dict[str, Any]]]:
    bands, unit_size, slot_source = phase_a_slots(a_boxes)
    kept: list[Box] = []
    rows: list[dict[str, Any]] = []
    for box in a_boxes:
        if support_policy == "c_iou":
            x4_supported = has_iou_support(box, c_boxes, iou_threshold)
            detail = {"mode": "symmetric_iou", "source": "C"}
        elif support_policy == "b_iou":
            x4_supported = has_iou_support(box, b_boxes, iou_threshold)
            detail = {"mode": "symmetric_iou", "source": "B"}
        elif support_policy == "b_directional":
            x4_supported, best = directional_support(
                box,
                b_boxes,
                bands=bands,
                unit_size=unit_size,
                xdist_unit_ratio=directional_alpha,
                slot_coverage_threshold=directional_gamma,
                fallback_vertical_coverage=directional_fallback,
            )
            detail = {
                "mode": "directional_staff_slot",
                "source": "B",
                "best": best,
            }
        else:
            raise ValueError(f"Unknown support policy: {support_policy}")
        omr_supported = has_iou_support(box, omr_boxes, iou_threshold)
        keep = bool(x4_supported or omr_supported)
        if keep:
            kept.append(box)
        rows.append(
            {
                "baseline_box": list(box),
                "x4_supported": bool(x4_supported),
                "omr_supported": bool(omr_supported),
                "keep": keep,
                **detail,
            }
        )
    return kept, [
        {
            "slot_source": slot_source,
            "staff_band_count": len(bands),
            "unit_size_px": unit_size,
            "rows": rows,
        }
    ]


def make_best_band_probe() -> Any:
    """Compile an experiment-local exact copy with one-box/one-band suppression.

    All probe generation/rescue code remains the current PDFScoreBar implementation.
    Only the local `has_existing_for_suppression` closure is replaced.  The source
    replacement is asserted so repository drift fails loudly instead of silently
    changing the experiment.
    """
    source = textwrap.dedent(inspect.getsource(production_detect_probe_scan))
    signature_old = "    scan_existing_min_vertical_iou: float = 0.0,\n"
    signature_new = (
        signature_old
        + '    issue274_existing_suppression_mode: str = "legacy",\n'
    )
    if source.count(signature_old) != 1:
        raise RuntimeError("Could not locate probe suppression signature boundary")
    source = source.replace(signature_old, signature_new, 1)

    old = textwrap.dedent(
        """
            def has_existing_for_suppression(x_center: float, y1: int, y2: int) -> bool:
                if scan_disable_existing_suppression:
                    return False
                return has_existing(x_center, y1, y2)
        """
    ).strip("\n")
    # Re-indent the block to the function body's four-space level.
    old = textwrap.indent(old, "    ")
    new = textwrap.indent(
        textwrap.dedent(
            """
            suppression_owner_by_box: dict[int, int] = {}
            if issue274_existing_suppression_mode == "best_band":
                for box_index, (_bx1, by1, _bx2, by2) in enumerate(existing_boxes):
                    box_top = min(by1, by2)
                    box_bottom = max(by1, by2)
                    box_h = max(1.0, float(box_bottom - box_top))
                    cy = (by1 + by2) / 2.0
                    best_owner = None
                    best_rank = None
                    for candidate_band_index, (owner_y1, owner_y2) in enumerate(bands):
                        if cy < owner_y1 or cy > owner_y2:
                            continue
                        band_h_owner = max(1.0, float(owner_y2 - owner_y1))
                        inter = max(
                            0.0,
                            min(float(owner_y2), float(box_bottom))
                            - max(float(owner_y1), float(box_top)),
                        )
                        union = max(1.0, band_h_owner + box_h - inter)
                        v_iou = inter / union
                        box_coverage = inter / box_h
                        band_coverage = inter / band_h_owner
                        band_center = (owner_y1 + owner_y2) / 2.0
                        center_distance = abs(cy - band_center) / band_h_owner
                        rank = (v_iou, box_coverage, band_coverage, -center_distance)
                        if best_rank is None or rank > best_rank:
                            best_rank = rank
                            best_owner = candidate_band_index
                    if best_owner is not None:
                        suppression_owner_by_box[box_index] = best_owner
            elif issue274_existing_suppression_mode != "legacy":
                raise ValueError(
                    "Unknown issue274_existing_suppression_mode: "
                    + str(issue274_existing_suppression_mode)
                )

            def has_existing_for_suppression(x_center: float, y1: int, y2: int) -> bool:
                if scan_disable_existing_suppression:
                    return False
                if issue274_existing_suppression_mode == "legacy":
                    return has_existing(x_center, y1, y2)

                try:
                    current_band_index = bands.index((y1, y2))
                except ValueError:
                    return False
                band_h_local = max(1.0, float(y2 - y1))
                for box_index, (bx1, by1, bx2, by2) in enumerate(existing_boxes):
                    if suppression_owner_by_box.get(box_index) != current_band_index:
                        continue
                    cx = (bx1 + bx2) / 2.0
                    if abs(cx - x_center) > x_merge_tol:
                        continue
                    if scan_existing_min_vertical_iou > 0:
                        iy1 = max(y1, min(by1, by2))
                        iy2 = min(y2, max(by1, by2))
                        inter = max(0.0, iy2 - iy1)
                        box_h_local = max(1.0, abs(by2 - by1))
                        union = max(1.0, band_h_local + box_h_local - inter)
                        if inter / union < scan_existing_min_vertical_iou:
                            continue
                    return True
                return False
            """
        ).strip("\n"),
        "    ",
    )
    if source.count(old) != 1:
        raise RuntimeError("Could not locate existing-suppression closure")
    source = source.replace(old, new, 1)
    namespace = dict(inspect.getmodule(production_detect_probe_scan).__dict__)
    exec(compile(source, "<issue274_best_band_probe>", "exec"), namespace)
    return namespace["detect_probe_scan"]


def best_band_ownership(
    existing_boxes: Sequence[Box], bands: Sequence[tuple[int, int]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for box_index, box in enumerate(existing_boxes):
        bx1, by1, bx2, by2 = box
        top, bottom = min(by1, by2), max(by1, by2)
        box_h = max(1.0, float(bottom - top))
        cy = (by1 + by2) / 2.0
        eligible = []
        for band_index, (y1, y2) in enumerate(bands):
            if cy < y1 or cy > y2:
                continue
            band_h = max(1.0, float(y2 - y1))
            inter = max(0.0, min(float(y2), float(bottom)) - max(float(y1), float(top)))
            union = max(1.0, band_h + box_h - inter)
            rank = [
                inter / union,
                inter / box_h,
                inter / band_h,
                -abs(cy - (y1 + y2) / 2.0) / band_h,
            ]
            eligible.append({"band_index": band_index, "band": [y1, y2], "rank": rank})
        eligible.sort(key=lambda row: tuple(row["rank"]), reverse=True)
        result.append(
            {
                "box_index": box_index,
                "box": list(box),
                "eligible_band_count": len(eligible),
                "owner_band_index": eligible[0]["band_index"] if eligible else None,
                "eligible_bands": eligible,
            }
        )
    return result


def seed_split(
    image: np.ndarray,
    boxes: list[Box],
    *,
    ink_threshold: int,
) -> list[Box]:
    unit = _estimate_unit_size_from_existing_boxes(boxes) or 40.0
    split_threshold = 12.0 * unit
    min_gap_px = int(1.25 * unit)
    min_segment_h_px = int(0.75 * unit)
    split_seeds: list[Box] = []
    for box in boxes:
        if abs(box[3] - box[1]) > split_threshold:
            split_seeds.extend(
                norm_box(candidate)
                for candidate in split_box_vertically(
                    image,
                    box,
                    ink_threshold=ink_threshold,
                    min_gap=min_gap_px,
                    min_segment_h=min_segment_h_px,
                )
            )
        else:
            split_seeds.append(box)
    return split_seeds


def run_dense_page(
    *,
    image: np.ndarray,
    existing_boxes: list[Box],
    clef_mask: np.ndarray,
    det_cfg: Mapping[str, Any],
    suppression_mode: str,
    best_band_probe: Any,
) -> tuple[list[Box], dict[str, Any]]:
    ink_threshold = int(det_cfg.get("ink_threshold", 180))
    min_ratio = float(det_cfg.get("min_ratio", 0.50))
    min_height_ratio = float(det_cfg.get("min_height_ratio", 0.012))
    min_width_ratio = (
        float(det_cfg["min_width_ratio"])
        if det_cfg.get("min_width_ratio") is not None
        else 0.0001
    )
    band_cluster_max_dist = (
        float(det_cfg["band_cluster_max_dist"])
        if det_cfg.get("band_cluster_max_dist") is not None
        else None
    )
    band_min_row_count = int(det_cfg.get("band_min_row_count", 1))
    vertical_closing = int(det_cfg.get("vertical_closing", 4))

    seeds = seed_split(image, list(existing_boxes), ink_threshold=ink_threshold)
    kwargs: dict[str, Any] = {
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.8,
        "scan_gap_rescue_min_ratio": 0.0,
        "scan_gap_margin_ratio": 0.1,
        "divisi_rescue": True,
        "scan_x_peak_rescue_mode": "topbottom",
        "probe_width": 4,
        "scan_x_peak_ratio_min": 0.0,
        "scan_rightmost_min_ratio": 0.0,
        "max_per_band": 100,
        "scan_center_on_peak": True,
    }
    kwargs.update(get_probe_kwargs(det_cfg))
    page_kwargs = _resolve_scale_aware_probe_kwargs(kwargs, seeds)
    page_kwargs, post_cfg = _extract_candidate_postprocess_cfg(page_kwargs, seeds)
    effective_band_source = str(page_kwargs.pop("band_source", "row_stats"))
    if effective_band_source != "row_stats":
        raise RuntimeError(
            "Issue #274 focused matrix expects the canonical row_stats band source; "
            f"got {effective_band_source!r}"
        )

    staff_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    if suppression_mode == "legacy":
        raw = production_detect_probe_scan(
            base_img=image,
            staff_mask=staff_mask,
            existing_boxes=seeds,
            band_source=effective_band_source,
            band_cluster_max_dist=band_cluster_max_dist,
            band_min_row_count=band_min_row_count,
            ink_threshold=ink_threshold,
            min_ratio=min_ratio,
            vertical_closing=vertical_closing,
            **page_kwargs,
        )
    elif suppression_mode == "disabled":
        disabled_kwargs = dict(page_kwargs)
        disabled_kwargs["scan_disable_existing_suppression"] = True
        raw = production_detect_probe_scan(
            base_img=image,
            staff_mask=staff_mask,
            existing_boxes=seeds,
            band_source=effective_band_source,
            band_cluster_max_dist=band_cluster_max_dist,
            band_min_row_count=band_min_row_count,
            ink_threshold=ink_threshold,
            min_ratio=min_ratio,
            vertical_closing=vertical_closing,
            **disabled_kwargs,
        )
    elif suppression_mode == "best_band":
        best_kwargs = dict(page_kwargs)
        best_kwargs["issue274_existing_suppression_mode"] = "best_band"
        raw = best_band_probe(
            base_img=image,
            staff_mask=staff_mask,
            existing_boxes=seeds,
            band_source=effective_band_source,
            band_cluster_max_dist=band_cluster_max_dist,
            band_min_row_count=band_min_row_count,
            ink_threshold=ink_threshold,
            min_ratio=min_ratio,
            vertical_closing=vertical_closing,
            **best_kwargs,
        )
    else:
        raise ValueError(suppression_mode)

    image_h, image_w = image.shape[:2]
    min_height_px = int(image_h * min_height_ratio)
    min_width_px = int(image_w * min_width_ratio)
    filtered = [
        norm_box(box)
        for box in raw
        if abs(box[3] - box[1]) >= min_height_px
        and abs(box[2] - box[0]) >= min_width_px
    ]

    if bool(det_cfg.get("enable_heuristic_filters", True)):
        filter_kwargs = {
            "left_margin_ratio": 0.25,
            "clef_left_ratio": 0.30,
            "min_height_median_ratio": 0.85,
            "ink_threshold": 180,
            "min_ink_ratio": 0.70,
            "paper_threshold": 200,
            "min_paper_overlap_ratio": 0.6,
            "min_staff_overlap_ratio": 0.15,
            "max_width_ratio": 0.05,
        }
        filter_kwargs.update(det_cfg.get("candidate_filter_kwargs", {}))
        filtered, dropped = filter_probe_candidates(
            candidates=filtered,
            image=image,
            existing_boxes=seeds,
            staff_mask=None,
            clef_mask=clef_mask,
            **filter_kwargs,
        )
    else:
        dropped = []

    trimmed = [trim_box_to_ink(image, box, ink_threshold=ink_threshold) for box in filtered]
    filtered = [
        norm_box(box)
        for box in trimmed
        if abs(box[3] - box[1]) >= min_height_px
        and abs(box[2] - box[0]) >= min_width_px
    ]

    final_set = {
        norm_box(box)
        for box in seeds
        if abs(box[3] - box[1]) >= min_height_px
        and abs(box[2] - box[0]) >= min_width_px
    }
    final_set.update(filtered)

    if post_cfg:
        if post_cfg.get("post_emit_unit_normalized_box"):
            final_set.update(
                norm_box(box)
                for box in _augment_unit_normalized_boxes(
                    list(final_set),
                    img_w=image_w,
                    img_h=image_h,
                    cfg=post_cfg,
                )
            )
        if post_cfg.get("split_wide_candidates"):
            split_boxes, _stats = split_wide_candidates(
                boxes=list(final_set),
                img=image,
                min_split_width_unit_ratio=float(
                    post_cfg.get("split_min_width_unit_ratio", 1.5)
                ),
                split_box_width_unit_ratio=float(
                    post_cfg.get("split_box_width_unit_ratio", 0.8)
                ),
                split_peak_distance_unit_ratio=float(
                    post_cfg.get("split_peak_distance_unit_ratio", 0.5)
                ),
                peak_prominence_ratio=float(
                    post_cfg.get("split_peak_prominence_ratio", 0.15)
                ),
                require_exactly_two_peaks=False,
                recenter_single_peak=False,
                emit_merged_two_peak_box=False,
                keep_original_when_not_split=False,
            )
            final_set.update(norm_box(box) for box in split_boxes)

    row_stats = build_row_stats(
        seeds,
        cluster_max_dist=band_cluster_max_dist,
        min_row_count=band_min_row_count,
    )
    bands = [
        (int(row["top"]), int(row["bottom"]))
        for row in row_stats
        if row["bottom"] >= row["top"]
    ]
    ownership = best_band_ownership(seeds, bands)
    return sorted(final_set), {
        "seed_count": len(seeds),
        "raw_probe_count": len(raw),
        "heuristic_kept_count": len(filtered),
        "heuristic_drop_count": len(dropped),
        "final_candidate_count": len(final_set),
        "band_count": len(bands),
        "multi_eligible_existing_count": sum(
            1 for row in ownership if row["eligible_band_count"] > 1
        ),
        "best_band_ownership": ownership,
    }


def maximum_cardinality(
    predictions: Sequence[Box],
    ground_truth: Sequence[Box],
    *,
    rule_name: str = "center_anchor",
    vov_threshold: float = 0.5,
    xdist_threshold: float = 12.0,
) -> tuple[int, list[int]]:
    adjacency = [
        [
            gt_index
            for gt_index, gt in enumerate(ground_truth)
            if is_barline_match(
                pred,
                gt,
                rule_name=rule_name,
                vov_threshold=vov_threshold,
                xdist_threshold=xdist_threshold,
            )
        ]
        for pred in predictions
    ]
    gt_owner = [-1] * len(ground_truth)

    def augment(pred_index: int, seen: set[int]) -> bool:
        for gt_index in adjacency[pred_index]:
            if gt_index in seen:
                continue
            seen.add(gt_index)
            if gt_owner[gt_index] == -1 or augment(gt_owner[gt_index], seen):
                gt_owner[gt_index] = pred_index
                return True
        return False

    matched = 0
    for pred_index in range(len(predictions)):
        if augment(pred_index, set()):
            matched += 1
    unmatched = [index for index, owner in enumerate(gt_owner) if owner == -1]
    return matched, unmatched


def score_metrics(
    predictions: list[Box], candidates: list[Box], ground_truth: list[Box]
) -> dict[str, Any]:
    greedy = greedy_barline_match(
        predictions,
        ground_truth,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    pred_cardinality, pred_unmatched = maximum_cardinality(predictions, ground_truth)
    candidate_cardinality, candidate_unmatched = maximum_cardinality(candidates, ground_truth)
    fn_det = sum(
        1
        for gt_index in greedy.false_negative_indices
        if gt_index in candidate_unmatched
    )
    return {
        "gt": len(ground_truth),
        "pred": len(predictions),
        "candidate_count": len(candidates),
        "tp": len(greedy.matches),
        "fp": len(greedy.false_positive_indices),
        "fn": len(greedy.false_negative_indices),
        "fn_det": fn_det,
        "fn_cnn": len(greedy.false_negative_indices) - fn_det,
        "greedy_fn_indices": list(greedy.false_negative_indices),
        "maximum_cardinality": pred_cardinality,
        "maximum_cardinality_unmatched_gt_indices": pred_unmatched,
        "candidate_maximum_cardinality": candidate_cardinality,
        "candidate_unmatched_gt_indices": candidate_unmatched,
    }


def critical_metrics(
    *,
    ground_truth: list[Box],
    candidates: list[Box],
    predictions: list[Box],
    critical_indices: Sequence[int],
) -> list[dict[str, Any]]:
    rows = []
    for index in sorted(set(int(value) for value in critical_indices)):
        if index < 0 or index >= len(ground_truth):
            continue
        gt = ground_truth[index]
        candidate_matches = [
            list(box)
            for box in candidates
            if is_barline_match(
                box,
                gt,
                rule_name="center_anchor",
                vov_threshold=0.5,
                xdist_threshold=12.0,
            )
        ]
        pred_matches = [
            list(box)
            for box in predictions
            if is_barline_match(
                box,
                gt,
                rule_name="center_anchor",
                vov_threshold=0.5,
                xdist_threshold=12.0,
            )
        ]
        rows.append(
            {
                "gt_index": index,
                "gt_bbox": list(gt),
                "candidate_match_count": len(candidate_matches),
                "candidate_matches": candidate_matches,
                "prediction_match_count": len(pred_matches),
                "prediction_matches": pred_matches,
            }
        )
    return rows


def csv_metrics(path: Path) -> dict[tuple[str, str], dict[str, int]]:
    result: dict[tuple[str, str], dict[str, int]] = {}
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (str(row["score"]), str(row["page"]))
            result[key] = {
                name: int(row[name])
                for name in ("gt", "pred", "candidate_count", "tp", "fp", "fn")
                if row.get(name) not in (None, "")
            }
    return result


def comparable_metric_subset(metrics: Mapping[str, Any]) -> dict[str, int]:
    return {
        key: int(metrics[key])
        for key in ("gt", "pred", "candidate_count", "tp", "fp", "fn")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--ab-report", type=Path, default=AB_DEFAULT)
    parser.add_argument("--residual-report", type=Path, default=RESIDUAL_DEFAULT)
    parser.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    parser.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--directional-alpha", type=float, default=0.30)
    parser.add_argument("--directional-gamma", type=float, default=0.60)
    parser.add_argument("--directional-fallback", type=float, default=0.60)
    parser.add_argument("--iou-threshold", type=float, default=0.50)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    ab_path = to_workspace(args.ab_report, workspace)
    residual_path = to_workspace(args.residual_report, workspace)
    config_path = to_workspace(args.config, workspace)
    output_root = to_workspace(args.output_root, workspace)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output must be new/empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    ab = load_json(ab_path)
    residual = load_json(residual_path)
    det_cfg = read_config(config_path)
    if not bool(det_cfg.get("probe_use_original_images", False)):
        raise RuntimeError("Canonical config no longer probes original images")

    control_csv = to_workspace(residual["gate_input"]["control_page_metrics"], workspace)
    candidate_csv = to_workspace(residual["gate_input"]["candidate_page_metrics"], workspace)
    expected_control = csv_metrics(control_csv)
    expected_candidate = csv_metrics(candidate_csv)

    residual_by_page = {
        (str(page["score"]), str(page["page"])): page
        for page in residual.get("pages", [])
    }
    page_inputs: dict[tuple[str, str], dict[str, Any]] = {}
    for score, page in FOCUSED_CASES:
        record = find_ab_record(ab, score, page)
        a_path = to_workspace(record["a_path"], workspace)
        b_path = to_workspace(record["b_current_x4_path"], workspace)
        c_path = to_workspace(record["c_pinned_x4_path"], workspace)
        omr_path = to_workspace(record["omr_path"], workspace)
        for path in (a_path, b_path, c_path, omr_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        image_path = canonical_image(workspace, score, page)
        gt_path = canonical_gt(workspace, score, page)
        clef_path = discover_retained_c_clef(c_path, page)
        page_inputs[(score, page)] = {
            "score": score,
            "page": page,
            "image": image_path,
            "gt": gt_path,
            "a": list(load_json_boxes(a_path)),
            "b": list(load_json_boxes(b_path)),
            "c": list(load_json_boxes(c_path)),
            "omr": list(load_json_boxes(omr_path)),
            "paths": {
                "a": str(a_path),
                "b": str(b_path),
                "c": str(c_path),
                "omr": str(omr_path),
                "retained_c_clef": str(clef_path) if clef_path else None,
            },
            "critical_indices": [
                int(item["gt_index"])
                for item in residual_by_page.get((score, page), {}).get("residuals", [])
                if item.get("gt_index") is not None
            ],
        }

    best_band_probe = make_best_band_probe()
    model_path = _resolve_model_path(Path(str(det_cfg.get("cnn_model_path"))))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _load_model(model_path, device)
    gpu_norm = GPUNormalize(MEAN, STD).to(device)
    cnn_threshold = float(det_cfg.get("cnn_threshold", 0.1))
    cnn_apply_nms = get_cnn_apply_nms(det_cfg)

    report_cells = []
    replay_checks: dict[str, Any] = {}
    for cell in MATRIX:
        cell_root = output_root / cell["name"]
        page_reports = []
        totals = Counter()
        for score, page in FOCUSED_CASES:
            item = page_inputs[(score, page)]
            image = cv2.imread(str(item["image"]))
            if image is None:
                raise RuntimeError(f"Failed to read image: {item['image']}")
            ground_truth = [norm_box(box) for box in boxes_from_gt(load_json(item["gt"]))]
            hybrid, support_trace = build_hybrid(
                a_boxes=item["a"],
                b_boxes=item["b"],
                c_boxes=item["c"],
                omr_boxes=item["omr"],
                support_policy=cell["support"],
                iou_threshold=args.iou_threshold,
                directional_alpha=args.directional_alpha,
                directional_gamma=args.directional_gamma,
                directional_fallback=args.directional_fallback,
            )

            page_root = cell_root / score / page
            hybrid_root = page_root / "hybrid"
            hybrid_path = hybrid_root / "hybrid_results" / f"{page}_hybrid.json"
            write_json(hybrid_path, [list(box) for box in hybrid])

            clef_source = item["paths"]["retained_c_clef"] if cell["clef"] == "retained_c" else None
            clef_mask = load_clef_mask(
                Path(clef_source) if clef_source else None,
                image.shape[:2],
            )
            candidates, dense_trace = run_dense_page(
                image=image,
                existing_boxes=hybrid,
                clef_mask=clef_mask,
                det_cfg=det_cfg,
                suppression_mode=cell["suppression"],
                best_band_probe=best_band_probe,
            )

            run_dir = page_root / "probe"
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                run_dir / "pipeline2_no_peak_candidates.json",
                [list(box) for box in candidates],
            )
            if not _score_directory(
                run_dir=run_dir,
                image_path=item["image"],
                model=model,
                gpu_norm=gpu_norm,
                threshold=cnn_threshold,
                device=device,
                batch_size=64,
                staff_mask_path=None,
                bands_from=hybrid_root,
                current_score_name=score,
                staff_vov_threshold=float(det_cfg.get("staff_vov_threshold", 0.5)),
                crop_recenter_on_bbox_ink=bool(
                    det_cfg.get("crop_recenter_on_bbox_ink", False)
                ),
                crop_recenter_max_shift_unit_ratio=float(
                    det_cfg.get("crop_recenter_max_shift_unit_ratio", 0.35)
                ),
                input_image_scale=1.0,
                apply_nms_enabled=cnn_apply_nms,
            ):
                raise RuntimeError(f"CNN scoring failed: {cell['name']} {score}/{page}")
            scored = load_json(run_dir / "pipeline2_no_peak_scored.json")
            predictions = [
                norm_box(row["bbox"])
                for row in scored
                if isinstance(row, Mapping)
                and float(row.get("score", 0.0)) >= cnn_threshold
            ]
            metrics = score_metrics(predictions, candidates, ground_truth)
            for key in ("gt", "pred", "candidate_count", "tp", "fp", "fn", "fn_det", "fn_cnn"):
                totals[key] += int(metrics[key])
            totals["maximum_cardinality"] += int(metrics["maximum_cardinality"])
            totals["candidate_maximum_cardinality"] += int(
                metrics["candidate_maximum_cardinality"]
            )

            page_report = {
                "score": score,
                "page": page,
                "support_policy": cell["support"],
                "suppression_policy": cell["suppression"],
                "clef_policy": cell["clef"],
                "clef_path": clef_source,
                "hybrid_count": len(hybrid),
                "metrics": metrics,
                "critical": critical_metrics(
                    ground_truth=ground_truth,
                    candidates=candidates,
                    predictions=predictions,
                    critical_indices=item["critical_indices"],
                ),
                "support_trace": support_trace,
                "dense_trace": dense_trace,
                "paths": {
                    "hybrid": str(hybrid_path),
                    "candidates": str(run_dir / "pipeline2_no_peak_candidates.json"),
                    "scored": str(run_dir / "pipeline2_no_peak_scored.json"),
                },
            }
            write_json(page_root / "page_report.json", page_report)
            page_reports.append(page_report)

        report_cells.append(
            {
                **cell,
                "summary": dict(totals),
                "pages": page_reports,
            }
        )

    by_name = {cell["name"]: cell for cell in report_cells}
    control_cell = by_name["control_c_iou_legacy_retained_c_clef"]
    candidate_cell = by_name["b_iou_legacy_retained_c_clef"]
    for label, cell, expected in (
        ("control", control_cell, expected_control),
        ("candidate", candidate_cell, expected_candidate),
    ):
        rows = []
        exact = True
        for page_report in cell["pages"]:
            key = (page_report["score"], page_report["page"])
            actual = comparable_metric_subset(page_report["metrics"])
            reference = expected[key]
            same = actual == reference
            exact = exact and same
            rows.append(
                {
                    "score": key[0],
                    "page": key[1],
                    "actual": actual,
                    "expected": reference,
                    "exact": same,
                }
            )
        replay_checks[label] = {"exact_all_pages": exact, "pages": rows}

    if not replay_checks["control"]["exact_all_pages"] or not replay_checks["candidate"]["exact_all_pages"]:
        decision = "invalid_matrix_replay_does_not_reproduce_retained_ab"
    else:
        preferred = by_name["b_directional_best_band_no_clef"]
        preferred_with_clef = by_name["b_directional_best_band_retained_c_clef"]
        causal_upper = by_name[
            "b_directional_suppression_disabled_retained_c_clef"
        ]
        focused_gt = preferred["summary"]["gt"]
        if (
            preferred["summary"]["maximum_cardinality"] == focused_gt
            and preferred["summary"]["fn"] <= control_cell["summary"]["fn"]
            and preferred["summary"]["fp"] <= control_cell["summary"]["fp"]
        ):
            decision = "current_x4_consumer_contract_works_without_retained_c_clef"
        elif (
            preferred_with_clef["summary"]["maximum_cardinality"] == focused_gt
            and preferred_with_clef["summary"]["fn"] <= control_cell["summary"]["fn"]
            and preferred_with_clef["summary"]["fp"] <= control_cell["summary"]["fp"]
        ):
            decision = "consumer_contract_works_but_current_clef_handoff_must_be_added"
        elif causal_upper["summary"]["maximum_cardinality"] == focused_gt:
            decision = "suppression_is_causal_but_best_band_identity_needs_revision"
        else:
            decision = "current_x4_requires_additional_consumer_contract_work"

    report = {
        "schema_version": "issue274.current_x4_consumer_matrix.v1",
        "status": "completed",
        "decision": decision,
        "scope": {
            "pages": len(FOCUSED_CASES),
            "cells": len(MATRIX),
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "mmr_reexecuted": False,
            "dense_probe_reexecuted": True,
            "cnn_reexecuted": True,
            "cnn_model_loaded_once": True,
        },
        "ownership": OWNERSHIP,
        "ownership_reference": "tools/issue274/HOMR_FEATURE_OWNERSHIP.md",
        "producer_inputs": {
            "A": "retained pinned original-image HOMR baseline",
            "B": "retained current x4 HOMR support",
            "C": "retained pinned x4 HOMR support (control / clef dependency only)",
            "OMR": "retained OMR-DLN x4 support",
        },
        "contract_under_test": {
            "authoritative_topology": "A baseline geometry",
            "x4_role": "evidence, not topology owner",
            "directional_alpha": args.directional_alpha,
            "directional_gamma": args.directional_gamma,
            "directional_fallback": args.directional_fallback,
            "iou_threshold": args.iou_threshold,
            "best_band_invariant": (
                "one existing detection instance can suppress probe candidates in at most one "
                "structural row band"
            ),
            "best_band_rank": [
                "vertical_iou",
                "existing_box_vertical_coverage",
                "band_vertical_coverage",
                "negative_normalized_center_distance",
            ],
            "disabled_suppression_note": "causal upper bound only; not production proposal",
            "retained_c_clef_note": (
                "diagnostic control only. The clef pixels originate in upstream HOMR, but "
                "their persistence/handoff is a PDFScoreBar contract. If required, current B "
                "must publish its own clefs_keys mask from the same inference rather than keep C."
            ),
        },
        "replay_validation": replay_checks,
        "cells": report_cells,
        "decision_rule": {
            "first_gate": "control and legacy-B cells must exactly replay retained focused AB metrics",
            "do_not_select_by": "minimum focused error alone",
            "required_structure": [
                "recover true maximum-cardinality losses on p013/p015/Sibelius p004",
                "do not introduce focused FP beyond control",
                "Prokofiev p004 must not be mistaken for a true cardinality loss",
                "prefer one-box/one-band over suppression-disabled when both recover",
                "if retained C clef matters, capture current clefs_keys from the same B inference",
            ],
        },
        "next_gate": (
            "If a theory-justified current-B cell passes the focused matrix, replay that single "
            "consumer contract on all 68 retained pages before any fresh HOMR run."
        ),
    }
    write_json(output_root / "issue274_current_x4_consumer_matrix.json", report)
    print(
        json.dumps(
            {
                "status": "completed",
                "decision": decision,
                "output": str(output_root / "issue274_current_x4_consumer_matrix.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not decision.startswith("invalid_matrix") else 2


if __name__ == "__main__":
    raise SystemExit(main())
