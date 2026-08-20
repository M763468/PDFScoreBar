#!/usr/bin/env python3
"""Issue #274: replay legacy/current thin-barline policies from one HOMR inference.

For each selected x4 page this experiment executes the expensive HOMR stage once.
It intercepts the mapped pre-thin-barline predictions, evaluates both the
historical scaled-default ThinBarlineConfig and the current broad config from the
same base predictions, then compares both post-processing results with retained
B/C artifacts.

It does not rerun SR, OMR-DLN, dense probe, CNN, or MMR.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import torch

import homr.main as homr_main
from homr.music_xml_generator import XmlGeneratorArguments
from src.common.thin_barline_finder import ThinBarlineConfig
from src.homr_eval_scripts.core import heuristics as homr_heuristics
from src.homr_eval_scripts.core import predictor as homr_predictor
from src.homr_eval_scripts.core.metrics import BarlinePrediction
from src.homr_eval_scripts.core.utils import DEFAULT_TUNING, STEM_CONTEXT_HEURISTICS
from src.pipeline.detection.homr_profile_compat import (
    build_processing_config_compat,
    install_current_homr_consumer_compat,
)
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue274.analyze_x4_support_contract import (
    directional_support,
    has_iou_support,
    phase_a_slots,
    residual_critical_boxes,
    to_workspace,
)

Box = tuple[int, int, int, int]

DEFAULT_CASES = (
    "Shostakovich-Sym5-Va/page_013",
    "Shostakovich-Sym5-Va/page_015",
    "Sibelius-Violin_Concerto-Viola/page_004",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_box(values: Iterable[Any]) -> Box:
    vals = list(values)
    return tuple(int(round(float(value))) for value in vals[:4])  # type: ignore[return-value]


def legacy_thin_config(sr_scale: int) -> ThinBarlineConfig:
    """Reproduce the monolithic evaluator's scaled-default policy."""
    base = ThinBarlineConfig()
    if sr_scale <= 1:
        return base
    return ThinBarlineConfig(
        min_height=base.min_height * sr_scale,
        max_height=base.max_height * sr_scale,
        max_width=base.max_width * sr_scale,
        y_merge_tolerance=base.y_merge_tolerance * sr_scale,
        y_center_tolerance=base.y_center_tolerance * sr_scale,
        x_center_tolerance=base.x_center_tolerance * sr_scale,
        adjacent_relaxed_span=base.adjacent_relaxed_span * sr_scale,
        vertical_gap_fill=base.vertical_gap_fill * sr_scale,
        left_margin_limit=base.left_margin_limit * sr_scale,
        cluster_x_tolerance=base.cluster_x_tolerance * sr_scale,
        cluster_reject_span=base.cluster_reject_span * sr_scale,
        pixel_threshold=base.pixel_threshold,
        dark_pixel_threshold=base.dark_pixel_threshold,
    )


def merge_thin_candidates(
    base_boxes: list[Box],
    extra_boxes: list[Box],
    *,
    sr_scale: int,
) -> list[BarlinePrediction]:
    """Replay the merge/replace loop shared by legacy and current predictors."""
    predictions = [
        BarlinePrediction(
            pred_bbox=box,
            orig_bbox=box,
            system_index=-1,
            staff_index=-1,
        )
        for box in base_boxes
    ]

    def centre(box: Box) -> tuple[float, float]:
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    def vertical_overlap_fraction(a: Box, b: Box) -> float:
        top = max(a[1], b[1])
        bottom = min(a[3], b[3])
        if bottom <= top:
            return 0.0
        overlap = bottom - top
        height_a = max(a[3] - a[1], 1)
        height_b = max(b[3] - b[1], 1)
        return overlap / float(max(height_a, height_b))

    for box in extra_boxes:
        cx_extra, cy_extra = centre(box)
        box_height = max(box[3] - box[1], 1)
        replaced = False

        for index, prediction in enumerate(predictions):
            existing = norm_box(prediction.orig_bbox)
            cx_existing, cy_existing = centre(existing)
            if abs(cx_existing - cx_extra) > 2 * sr_scale:
                continue

            existing_height = max(existing[3] - existing[1], 1)
            centre_gap = abs(cy_existing - cy_extra)
            vertical_overlap = vertical_overlap_fraction(existing, box)

            if vertical_overlap >= 0.6:
                if box_height > existing_height:
                    predictions[index] = BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                replaced = True
                break

            max_height = max(box_height, existing_height)
            if centre_gap <= max_height:
                if box_height >= existing_height:
                    predictions[index] = BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                replaced = True
                break

        if not replaced:
            predictions.append(
                BarlinePrediction(
                    pred_bbox=box,
                    orig_bbox=box,
                    system_index=-2,
                    staff_index=-1,
                )
            )

    return predictions


def apply_stem_filter(
    predictions: list[BarlinePrediction],
    notehead_mask,
    staff_mask,
    *,
    sr_scale: int,
    tuning: dict[str, Any],
) -> tuple[list[BarlinePrediction], list[BarlinePrediction]]:
    if not tuning.get("stem_context_heuristics_enabled", True):
        return predictions, []

    cfg = STEM_CONTEXT_HEURISTICS.copy()
    if sr_scale > 1:
        cfg["notehead_proximity_threshold_px"] *= sr_scale
        cfg["min_overlap_px"] *= sr_scale * sr_scale
        cfg["max_height_px"] *= sr_scale
        cfg["max_width_px"] *= sr_scale
        cfg["cluster_gap_threshold_px"] *= sr_scale

    return homr_heuristics.filter_detections_by_notehead_proximity(
        predictions,
        notehead_mask,
        cfg["notehead_proximity_threshold_px"],
        cfg["min_overlap_px"],
        cfg["max_height_px"],
        cfg["max_width_px"],
        staff_mask,
        cfg["min_staff_crossings"],
        cfg["staff_crossing_enabled"],
    )


def multiset_compare(left: list[Box], right: list[Box]) -> dict[str, Any]:
    lhs = Counter(left)
    rhs = Counter(right)
    common = lhs & rhs
    left_only = lhs - rhs
    right_only = rhs - lhs
    return {
        "left_count": sum(lhs.values()),
        "right_count": sum(rhs.values()),
        "exact_common": sum(common.values()),
        "left_only_count": sum(left_only.values()),
        "right_only_count": sum(right_only.values()),
        "left_only": [list(box) for box in left_only.elements()],
        "right_only": [list(box) for box in right_only.elements()],
        "exact_equal": lhs == rhs,
    }


def source_boxes(predictions: Iterable[BarlinePrediction], sr_scale: int) -> list[Box]:
    return [
        tuple(int(round(value / sr_scale)) for value in pred.orig_bbox)  # type: ignore[misc]
        for pred in predictions
    ]


def select_records(report: dict[str, Any], cases: list[str]) -> list[dict[str, Any]]:
    wanted = set(cases)
    selected = []
    for row in report["hybrid_ab"]["pages"]:
        key = f"{row['score']}/{row['page']}"
        if key in wanted:
            selected.append(row)
    found = {f"{row['score']}/{row['page']}" for row in selected}
    missing = wanted - found
    if missing:
        raise KeyError(f"Cases not found in A/B report: {sorted(missing)}")
    return selected


def build_predictor(det_cfg: dict[str, Any]):
    use_gpu = torch.cuda.is_available()
    compat = install_current_homr_consumer_compat(
        homr_main,
        homr_predictor,
        homr_heuristics,
        use_gpu_inference=use_gpu,
    )
    config = build_processing_config_compat(
        homr_main.ProcessingConfig,
        enable_debug=bool(det_cfg.get("enable_debug", False)),
        enable_cache=bool(det_cfg.get("enable_cache", True)),
        write_staff_positions=bool(det_cfg.get("write_staff_positions", False)),
        use_gpu_inference=use_gpu,
    )
    tuning = DEFAULT_TUNING.copy()
    tuning.update(
        {
            "barline_min_height_factor": det_cfg.get("barline_min_height_factor", 1.0),
            "barline_max_width_factor": det_cfg.get("barline_max_width_factor", 1.0),
        }
    )
    if tuning.get("enable_end_barline_recovery", False):
        raise RuntimeError("Experiment assumes end-barline recovery is disabled")
    predictor = homr_predictor.HomrPredictor(
        config,
        tuning,
        use_gpu_inference=use_gpu,
    )
    return predictor, tuning, compat, use_gpu


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ab-report",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/stage_e_ab_01/issue274_homr_x4_stage_e_ab.json"
        ),
    )
    parser.add_argument(
        "--residual-report",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
            "residual_trace_01/issue274_homr_x4_stage_e_residual_trace.json"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/issue274_homr_unification_analysis/thin_policy_replay_01"),
    )
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--case", action="append", default=None)
    parser.add_argument("--sr-scale", type=int, default=4)
    parser.add_argument("--directional-alpha", type=float, default=0.30)
    parser.add_argument("--slot-coverage", type=float, default=0.60)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    ab_path = to_workspace(args.ab_report, workspace)
    residual_path = to_workspace(args.residual_report, workspace)
    output_root = to_workspace(args.output_root, workspace)
    output_root.mkdir(parents=True, exist_ok=True)

    cases = list(args.case or DEFAULT_CASES)
    ab = load_json(ab_path)
    selected = select_records(ab, cases)
    critical = residual_critical_boxes(residual_path if residual_path.is_file() else None)

    requests = []
    for row in selected:
        b_path = to_workspace(row["b_current_x4_path"], workspace)
        support_root = b_path.parents[3]
        request_path = support_root / "current_homr_request.json"
        if not request_path.is_file():
            raise FileNotFoundError(request_path)
        request = load_json(request_path)
        requests.append((row, request_path, request))

    first_det_cfg = dict(requests[0][2]["detection"])
    for _, request_path, request in requests[1:]:
        if dict(request["detection"]) != first_det_cfg:
            raise RuntimeError(f"Detection config differs across selected pages: {request_path}")

    if int(first_det_cfg.get("sr_scale", args.sr_scale)) != args.sr_scale:
        raise RuntimeError("Unexpected SR scale in retained request")

    predictor, tuning, compat, use_gpu = build_predictor(first_det_cfg)
    xml_args = XmlGeneratorArguments(False, None, None)

    original_finder = homr_predictor.detect_thin_vertical_runs
    active_capture: dict[str, Any] = {}

    def capture_finder(image_path, existing_boxes, *, config):
        base_boxes = [norm_box(box) for box in existing_boxes]
        legacy_cfg = legacy_thin_config(args.sr_scale)
        legacy_extra = [
            norm_box(box) for box in original_finder(image_path, base_boxes, config=legacy_cfg)
        ]
        current_extra = [
            norm_box(box) for box in original_finder(image_path, base_boxes, config=config)
        ]
        active_capture.clear()
        active_capture.update(
            {
                "base_boxes": base_boxes,
                "legacy_extra": legacy_extra,
                "current_extra": current_extra,
                "legacy_config": {
                    "min_height": legacy_cfg.min_height,
                    "max_height": legacy_cfg.max_height,
                    "max_width": legacy_cfg.max_width,
                    "pixel_threshold": legacy_cfg.pixel_threshold,
                    "max_intensity_std": legacy_cfg.max_intensity_std,
                    "max_intensity_std_relaxed": legacy_cfg.max_intensity_std_relaxed,
                },
                "current_config": {
                    "min_height": config.min_height,
                    "max_height": config.max_height,
                    "max_width": config.max_width,
                    "pixel_threshold": config.pixel_threshold,
                    "max_intensity_std": config.max_intensity_std,
                    "max_intensity_std_relaxed": config.max_intensity_std_relaxed,
                },
            }
        )
        return current_extra

    homr_predictor.detect_thin_vertical_runs = capture_finder
    page_results = []

    try:
        for row, request_path, request in requests:
            score = str(row["score"])
            page = str(row["page"])
            sr_image = to_workspace(request["sr_image"], workspace)
            if not sr_image.is_file():
                raise FileNotFoundError(sr_image)

            page_out = output_root / "pages" / score / page
            page_out.mkdir(parents=True, exist_ok=True)
            active_capture.clear()

            started = time.perf_counter()
            (
                current_predictions,
                _,
                _,
                predictor_runtime_s,
                notehead_mask,
                staff_mask,
                _,
                _,
            ) = predictor.predict(
                sr_image,
                xml_args,
                sr_scale=args.sr_scale,
                image_run_dir=page_out,
            )
            elapsed_s = time.perf_counter() - started

            if not active_capture:
                raise RuntimeError(f"Thin-barline capture did not run for {score}/{page}")

            base_boxes = list(active_capture["base_boxes"])
            legacy_extra = list(active_capture["legacy_extra"])
            current_extra = list(active_capture["current_extra"])

            legacy_merged = merge_thin_candidates(
                base_boxes,
                legacy_extra,
                sr_scale=args.sr_scale,
            )
            current_merged = merge_thin_candidates(
                base_boxes,
                current_extra,
                sr_scale=args.sr_scale,
            )
            legacy_final, legacy_rejected = apply_stem_filter(
                legacy_merged,
                notehead_mask,
                staff_mask,
                sr_scale=args.sr_scale,
                tuning=tuning,
            )
            current_replay, current_rejected = apply_stem_filter(
                current_merged,
                notehead_mask,
                staff_mask,
                sr_scale=args.sr_scale,
                tuning=tuning,
            )

            actual_current_x4 = [norm_box(pred.orig_bbox) for pred in current_predictions]
            replay_current_x4 = [norm_box(pred.orig_bbox) for pred in current_replay]
            legacy_x4 = [norm_box(pred.orig_bbox) for pred in legacy_final]

            current_replay_check = multiset_compare(replay_current_x4, actual_current_x4)
            if not current_replay_check["exact_equal"]:
                raise RuntimeError(
                    f"Current policy replay does not reproduce predictor output for {score}/{page}"
                )

            actual_current_source = source_boxes(current_predictions, args.sr_scale)
            replay_current_source = source_boxes(current_replay, args.sr_scale)
            legacy_source = source_boxes(legacy_final, args.sr_scale)

            retained_b = [
                norm_box(box)
                for box in load_json_boxes(to_workspace(row["b_current_x4_path"], workspace))
            ]
            retained_c = [
                norm_box(box)
                for box in load_json_boxes(to_workspace(row["c_pinned_x4_path"], workspace))
            ]
            a_boxes = [
                norm_box(box) for box in load_json_boxes(to_workspace(row["a_path"], workspace))
            ]
            bands, unit_size, slot_source = phase_a_slots(a_boxes)

            critical_rows = []
            for crit_score, crit_page, query in sorted(critical):
                if crit_score != score or crit_page != page:
                    continue
                policy_rows = {}
                for name, boxes in (
                    ("legacy", legacy_source),
                    ("current", replay_current_source),
                    ("retained_b", retained_b),
                    ("retained_c", retained_c),
                ):
                    directional, best = directional_support(
                        query,
                        boxes,
                        bands=bands,
                        unit_size=unit_size,
                        xdist_unit_ratio=args.directional_alpha,
                        slot_coverage_threshold=args.slot_coverage,
                        fallback_vertical_coverage=0.60,
                    )
                    policy_rows[name] = {
                        "iou_support": has_iou_support(query, boxes, 0.5),
                        "directional_support": directional,
                        "directional_best": best,
                    }
                critical_rows.append(
                    {
                        "baseline_box": list(query),
                        "policies": policy_rows,
                    }
                )

            page_result = {
                "score": score,
                "page": page,
                "request": str(request_path),
                "sr_image": str(sr_image),
                "heavy_homr_executions": 1,
                "predictor_runtime_s": predictor_runtime_s,
                "elapsed_s": elapsed_s,
                "pre_thin_count": len(base_boxes),
                "legacy_extra_count": len(legacy_extra),
                "current_extra_count": len(current_extra),
                "legacy_final_count_x4": len(legacy_x4),
                "current_final_count_x4": len(replay_current_x4),
                "legacy_rejected_count": len(legacy_rejected),
                "current_rejected_count": len(current_rejected),
                "thin_configs": {
                    "legacy": active_capture["legacy_config"],
                    "current": active_capture["current_config"],
                },
                "checks": {
                    "current_replay_vs_predictor": current_replay_check,
                    "predictor_current_vs_retained_b": multiset_compare(
                        actual_current_source, retained_b
                    ),
                    "legacy_policy_vs_retained_c": multiset_compare(legacy_source, retained_c),
                    "legacy_policy_vs_retained_b": multiset_compare(legacy_source, retained_b),
                    "current_policy_vs_retained_c": multiset_compare(
                        replay_current_source, retained_c
                    ),
                },
                "critical_cases": critical_rows,
                "slot_context": {
                    "source": slot_source,
                    "unit_size_px": unit_size,
                    "slot_count": len(bands),
                },
            }
            page_results.append(page_result)
            (page_out / "thin_policy_page_report.json").write_text(
                json.dumps(page_result, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    finally:
        homr_predictor.detect_thin_vertical_runs = original_finder
        predictor.cleanup()

    report = {
        "schema_version": "issue274.thin_policy_single_inference_replay.v1",
        "status": "completed",
        "scope": {
            "pages": len(page_results),
            "heavy_homr_executions": len(page_results),
            "homr_executions_per_page": 1,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
            "thin_policy_replays_per_page": 2,
        },
        "runtime": {
            "use_gpu": use_gpu,
            "homr_api_compat": compat,
        },
        "theory_test": {
            "same_pre_thin_homr_output_for_both_policies": True,
            "legacy_policy": "monolithic scaled-default ThinBarlineConfig",
            "current_policy": "current-core broad ThinBarlineConfig",
            "merge_rule_shared": True,
            "stem_filter_shared": True,
            "directional_support_alpha": args.directional_alpha,
            "slot_coverage": args.slot_coverage,
        },
        "pages": page_results,
    }

    report_path = output_root / "issue274_thin_policy_single_inference_replay.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "scope": report["scope"],
                "output": str(report_path),
                "pages": [
                    {
                        "score": row["score"],
                        "page": row["page"],
                        "pre_thin": row["pre_thin_count"],
                        "legacy_extra": row["legacy_extra_count"],
                        "current_extra": row["current_extra_count"],
                        "current_replay_exact": row["checks"]["current_replay_vs_predictor"][
                            "exact_equal"
                        ],
                        "current_vs_b_exact": row["checks"]["predictor_current_vs_retained_b"][
                            "exact_equal"
                        ],
                        "legacy_vs_c_exact": row["checks"]["legacy_policy_vs_retained_c"][
                            "exact_equal"
                        ],
                    }
                    for row in page_results
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
