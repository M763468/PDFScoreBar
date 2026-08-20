#!/usr/bin/env python3
"""Decompose Issue #274 Stage-E first-pass dense causality from retained artifacts.

This is a focused, low-cost experiment. It reruns only PDFScoreBar's first dense
probe scan on the already-retained page images and hybrid JSONs. It does NOT rerun
HOMR, SR, OMR-DLN, candidate filtering, the barline CNN, MMR, or numbering.

The previous multiplicity audit established that the four true structural losses
already exist at the merged first-pass raw-candidate boundary. That boundary still
conflates several roles of ``existing_boxes``:

- row-band construction;
- divisi / rescue context;
- existing-box suppression;
- final merge of hybrid seeds with generated candidates.

This tool first requires exact replay of the retained control and B raw candidate
roots. It then separates those roles enough to answer whether B's hybrid seed acts
mainly as detector context, as a suppression seed, or merely as a merged output
seed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from src.common import Box
from src.common.barline_evaluation import is_barline_match
from src.pipeline.probe_detector import detect_probe_scan
from src.pipeline.probe_detector.bands import build_row_stats

DEFAULT_INPUT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_multiplicity_provenance_01/"
    "issue274_stage_e_multiplicity_and_mask_provenance.json"
)
DEFAULT_OUTPUT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_first_pass_causality_01/"
    "issue274_stage_e_first_pass_context_causality.json"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def to_workspace(value: str | Path, workspace: Path) -> Path:
    text = str(value)
    if text.startswith("/workspace/"):
        return workspace / text[len("/workspace/") :]
    marker = "/ws_PDFScoreBar/"
    if marker in text:
        return workspace / text.split(marker, 1)[1]
    path = Path(text)
    return path if path.is_absolute() else workspace / path


def norm_box(values: Sequence[Any]) -> Box:
    return tuple(int(round(float(value))) for value in values[:4])  # type: ignore[return-value]


def load_boxes(path: Path) -> list[Box]:
    payload = load_json(path)
    records: Any = payload
    if isinstance(payload, Mapping):
        for key in ("predictions", "boxes", "detections"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break
    if not isinstance(records, list):
        return []
    result: list[Box] = []
    for item in records:
        if isinstance(item, (list, tuple)) and len(item) >= 4:
            result.append(norm_box(item))
            continue
        if not isinstance(item, Mapping):
            continue
        for key in ("orig_bbox", "bbox", "pred_bbox", "barline_location"):
            value = item.get(key)
            if isinstance(value, (list, tuple)) and len(value) >= 4:
                result.append(norm_box(value))
                break
    return result


def production_probe(
    image: np.ndarray,
    *,
    context_boxes: list[Box],
    supplied_row_stats: list[dict[str, float]] | None,
    disable_existing_suppression: bool,
) -> list[Box]:
    staff_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    return [
        norm_box(box)
        for box in detect_probe_scan(
            base_img=image,
            staff_mask=staff_mask,
            existing_boxes=context_boxes,
            band_source="row_stats",
            band_cluster_max_dist=25.0,
            band_min_row_count=1,
            row_stats=supplied_row_stats,
            band_scan_line_ratio=0.6,
            band_scan_min_lines=5,
            scan_x_peak_rescue=True,
            scan_rightmost_rescue=True,
            divisi_rescue=True,
            scan_x_peak_rescue_mode="topbottom",
            probe_width=4,
            ink_threshold=240,
            min_ratio=0.60,
            scan_x_peak_ratio_min=0.0,
            scan_rightmost_min_ratio=0.0,
            max_per_band=80,
            scan_center_on_peak=True,
            vertical_closing=0,
            scan_disable_existing_suppression=disable_existing_suppression,
        )
    ]


def merged_raw(
    image: np.ndarray,
    generated: list[Box],
    merge_boxes: list[Box],
) -> list[Box]:
    image_h, image_w = image.shape[:2]
    min_h_px = int(image_h * 0.006)
    min_w_px = int(image_w * 0.0)
    result: set[Box] = set()
    for box in [*merge_boxes, *generated]:
        if abs(box[3] - box[1]) < min_h_px:
            continue
        if abs(box[2] - box[0]) < min_w_px:
            continue
        result.add(norm_box(box))
    return sorted(result)


def exact_compare(observed: list[Box], expected: list[Box]) -> dict[str, Any]:
    obs = set(observed)
    exp = set(expected)
    return {
        "list_exact": observed == expected,
        "set_exact": obs == exp,
        "observed_count": len(observed),
        "expected_count": len(expected),
        "extra_count": len(obs - exp),
        "missing_count": len(exp - obs),
        "extra_sample": [list(box) for box in sorted(obs - exp)[:8]],
        "missing_sample": [list(box) for box in sorted(exp - obs)[:8]],
    }


def target_component(
    boxes: list[Box],
    component_gt_bboxes: list[Box],
    *,
    generated: set[Box],
    merge_boxes: set[Box],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    adjacency: list[list[int]] = []
    for box in boxes:
        matches = [
            index
            for index, gt in enumerate(component_gt_bboxes)
            if is_barline_match(
                box,
                gt,
                rule_name="center_anchor",
                vov_threshold=0.5,
                xdist_threshold=12.0,
            )
        ]
        if not matches:
            continue
        adjacency.append(matches)
        rows.append(
            {
                "bbox": list(box),
                "matched_local_gt_indices": matches,
                "source_generated": box in generated,
                "source_merged_existing": box in merge_boxes,
            }
        )

    owners = [-1] * len(component_gt_bboxes)

    def augment(pred_index: int, seen: set[int]) -> bool:
        for gt_index in adjacency[pred_index]:
            if gt_index in seen:
                continue
            seen.add(gt_index)
            owner = owners[gt_index]
            if owner == -1 or augment(owner, seen):
                owners[gt_index] = pred_index
                return True
        return False

    cardinality = 0
    for pred_index in range(len(adjacency)):
        if augment(pred_index, set()):
            cardinality += 1

    return {
        "gt_count": len(component_gt_bboxes),
        "gt_bboxes": [list(box) for box in component_gt_bboxes],
        "matching_prediction_count": len(rows),
        "maximum_cardinality": cardinality,
        "capacity_deficit": len(component_gt_bboxes) - cardinality,
        "predictions": rows,
    }


def local_rows(boxes: list[Box], target_bboxes: list[Box]) -> list[dict[str, float]]:
    stats = build_row_stats(boxes, cluster_max_dist=25.0, min_row_count=1)
    if not target_bboxes:
        return stats
    y1 = min(box[1] for box in target_bboxes)
    y2 = max(box[3] for box in target_bboxes)
    pad = max(50, int(round((y2 - y1) * 1.5)))
    return [
        stat
        for stat in stats
        if float(stat["bottom"]) >= y1 - pad and float(stat["top"]) <= y2 + pad
    ]


def run_variant(
    *,
    image: np.ndarray,
    context_boxes: list[Box],
    merge_boxes: list[Box],
    row_stats: list[dict[str, float]] | None,
    disable_suppression: bool,
    gt_bboxes: list[Box],
) -> dict[str, Any]:
    generated = production_probe(
        image,
        context_boxes=context_boxes,
        supplied_row_stats=row_stats,
        disable_existing_suppression=disable_suppression,
    )
    raw = merged_raw(image, generated, merge_boxes)
    return {
        "context_count": len(context_boxes),
        "merge_seed_count": len(merge_boxes),
        "supplied_row_stats": row_stats is not None,
        "disable_existing_suppression": disable_suppression,
        "generated_count": len(generated),
        "raw_count": len(raw),
        "local_context_rows": local_rows(context_boxes, gt_bboxes),
        "target_component": target_component(
            raw,
            gt_bboxes,
            generated=set(generated),
            merge_boxes=set(merge_boxes),
        ),
        "_raw": raw,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    input_path = to_workspace(args.input, workspace)
    output_path = to_workspace(args.output, workspace)
    audit = load_json(input_path)

    pages_out: list[dict[str, Any]] = []
    all_sanity = True
    for page in audit.get("pages", []):
        structural_targets = [
            target
            for target in page.get("targets", [])
            if target.get("first_candidate_capacity_divergence") == "raw_first_pass"
        ]
        if not structural_targets:
            continue

        score = str(page["score"])
        page_name = str(page["page"])
        control_meta = page["mask_provenance"]["control"]
        candidate_meta = page["mask_provenance"]["candidate"]
        image_path = to_workspace(control_meta["image"], workspace)
        control_hybrid_path = to_workspace(control_meta["hybrid_predictions"], workspace)
        candidate_hybrid_path = to_workspace(candidate_meta["hybrid_predictions"], workspace)
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        control_boxes = load_boxes(control_hybrid_path)
        candidate_boxes = load_boxes(candidate_hybrid_path)
        control_rows = build_row_stats(control_boxes, cluster_max_dist=25.0, min_row_count=1)
        candidate_rows = build_row_stats(candidate_boxes, cluster_max_dist=25.0, min_row_count=1)

        target_rows: list[dict[str, Any]] = []
        for target in structural_targets:
            gt_bboxes = [
                norm_box(box)
                for box in target["variants"]["control"]["raw_first_pass"]["target_component"][
                    "component_gt_bboxes"
                ]
            ]
            variants = {
                "control_production": run_variant(
                    image=image,
                    context_boxes=control_boxes,
                    merge_boxes=control_boxes,
                    row_stats=None,
                    disable_suppression=False,
                    gt_bboxes=gt_bboxes,
                ),
                "candidate_production": run_variant(
                    image=image,
                    context_boxes=candidate_boxes,
                    merge_boxes=candidate_boxes,
                    row_stats=None,
                    disable_suppression=False,
                    gt_bboxes=gt_bboxes,
                ),
                "candidate_no_suppression": run_variant(
                    image=image,
                    context_boxes=candidate_boxes,
                    merge_boxes=candidate_boxes,
                    row_stats=None,
                    disable_suppression=True,
                    gt_bboxes=gt_bboxes,
                ),
                "candidate_with_control_rows": run_variant(
                    image=image,
                    context_boxes=candidate_boxes,
                    merge_boxes=candidate_boxes,
                    row_stats=control_rows,
                    disable_suppression=False,
                    gt_bboxes=gt_bboxes,
                ),
                "candidate_with_control_rows_no_suppression": run_variant(
                    image=image,
                    context_boxes=candidate_boxes,
                    merge_boxes=candidate_boxes,
                    row_stats=control_rows,
                    disable_suppression=True,
                    gt_bboxes=gt_bboxes,
                ),
                "control_context_candidate_merge": run_variant(
                    image=image,
                    context_boxes=control_boxes,
                    merge_boxes=candidate_boxes,
                    row_stats=None,
                    disable_suppression=False,
                    gt_bboxes=gt_bboxes,
                ),
                "candidate_context_control_merge": run_variant(
                    image=image,
                    context_boxes=candidate_boxes,
                    merge_boxes=control_boxes,
                    row_stats=None,
                    disable_suppression=False,
                    gt_bboxes=gt_bboxes,
                ),
            }

            retained_control_path = to_workspace(
                target["variants"]["control"]["raw_first_pass"]["path"], workspace
            )
            retained_candidate_path = to_workspace(
                target["variants"]["candidate"]["raw_first_pass"]["path"], workspace
            )
            sanity = {
                "control": exact_compare(
                    variants["control_production"]["_raw"],
                    load_boxes(retained_control_path),
                ),
                "candidate": exact_compare(
                    variants["candidate_production"]["_raw"],
                    load_boxes(retained_candidate_path),
                ),
            }
            sanity_ok = sanity["control"]["set_exact"] and sanity["candidate"]["set_exact"]
            all_sanity = all_sanity and sanity_ok

            for variant in variants.values():
                variant.pop("_raw", None)

            target_rows.append(
                {
                    "gt_index": target["gt_index"],
                    "gt_bbox": target["gt_bbox"],
                    "component_gt_bboxes": [list(box) for box in gt_bboxes],
                    "sanity": sanity,
                    "sanity_ok": sanity_ok,
                    "control_row_stats_near_target": local_rows(control_boxes, gt_bboxes),
                    "candidate_row_stats_near_target": local_rows(candidate_boxes, gt_bboxes),
                    "variants": variants,
                }
            )

        pages_out.append(
            {
                "score": score,
                "page": page_name,
                "image": str(image_path),
                "control_hybrid": str(control_hybrid_path),
                "candidate_hybrid": str(candidate_hybrid_path),
                "control_hybrid_count": len(control_boxes),
                "candidate_hybrid_count": len(candidate_boxes),
                "control_row_count": len(control_rows),
                "candidate_row_count": len(candidate_rows),
                "targets": target_rows,
            }
        )

    result = {
        "schema_version": "issue274.stage_e_first_pass_context_causality.v1",
        "status": "completed" if all_sanity else "invalid_replay_sanity_failed",
        "scope": {
            "page_count": len(pages_out),
            "target_count": sum(len(page["targets"]) for page in pages_out),
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_first_pass_reexecuted": True,
            "candidate_filter_reexecuted": False,
            "probe_rescue_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
        },
        "production_contract": {
            "band_source": "row_stats",
            "band_cluster_max_dist": 25.0,
            "band_min_row_count": 1,
            "ink_threshold": 240,
            "min_ratio": 0.60,
            "min_height_ratio": 0.006,
            "min_width_ratio": 0.0,
            "probe_width": 4,
            "max_per_band": 80,
            "scan_x_peak_rescue": True,
            "scan_rightmost_rescue": True,
            "divisi_rescue": True,
            "scan_center_on_peak": True,
        },
        "all_production_replays_match_retained_raw_sets": all_sanity,
        "interpretation_guardrails": [
            "Do not interpret ablations unless production replay sanity passes.",
            "raw_first_pass contains both generated boxes and merged hybrid seeds.",
            "existing_boxes affect row bands, divisi/rescue context, suppression, and final merge.",
            "No single ablation alone proves a general production identity rule.",
            "Use visual/domain classification before turning local multiplicity into a generic topology contract.",
        ],
        "pages": pages_out,
    }
    write_json(output_path, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": str(output_path),
                "pages": len(pages_out),
                "targets": result["scope"]["target_count"],
            }
        )
    )
    return 0 if all_sanity else 2


if __name__ == "__main__":
    raise SystemExit(main())
