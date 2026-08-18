#!/usr/bin/env python3
"""Retained-only Stage-E multiplicity and mask-provenance analysis for Issue #274.

This tool does not rerun HOMR, SR, OMR-DLN, dense probe generation, filtering,
CNN, MMR, or numbering. It compares the already-retained accepted control route
with the retained current-x4 (B) Stage-E replay at the exact production dense-route
boundaries.

Two questions are answered together:

1. At which Stage-E boundary does a control barline multiplicity/capacity become a
   candidate matching competition (one prediction eligible for multiple GT slots)?
2. Which retained staff/clef masks did the first-pass Stage-E filter actually use,
   and which producer tree (A/B/C/unknown) do those paths belong to?

Ownership note:
- dense generation/filter/probe-rescue/CNN are PDFScoreBar extensions;
- staff/clef mask pixels originate in upstream HOMR;
- selecting, persisting and handing those masks to Stage-E is PDFScoreBar
  orchestration.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.common import Box
from src.common.barline_evaluation import is_barline_match
from tools.issue120.eval_full68_from_intermediates import boxes_from_gt

DEFAULT_RESIDUAL = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
    "residual_trace_01/issue274_homr_x4_stage_e_residual_trace.json"
)
DEFAULT_CONTROL_ROOT = Path(
    "logs/verification/detector_full68/"
    "issue255_production_restore_full68_top_level_worker_01/production_runs"
)
DEFAULT_CANDIDATE_ROOT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/candidate_stage_e"
)
DEFAULT_GT_ROOT = Path("data/evaluation2/annotations")
DEFAULT_OUTPUT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_multiplicity_provenance_01/"
    "issue274_stage_e_multiplicity_and_mask_provenance.json"
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


def load_candidate_boxes(path: Path) -> list[Box]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected candidate list: {path}")
    boxes: list[Box] = []
    for item in payload:
        if isinstance(item, (list, tuple)) and len(item) >= 4:
            boxes.append(norm_box(item))
        elif isinstance(item, Mapping):
            value = item.get("bbox")
            if isinstance(value, (list, tuple)) and len(value) >= 4:
                boxes.append(norm_box(value))
    return boxes


def load_scored_boxes(path: Path, threshold: float) -> tuple[list[Box], list[dict[str, Any]]]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected scored list: {path}")
    boxes: list[Box] = []
    records: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        value = item.get("bbox")
        if not isinstance(value, (list, tuple)) or len(value) < 4:
            continue
        score = float(item.get("score", 0.0))
        record = {"bbox": list(norm_box(value)), "score": score}
        records.append(record)
        if score >= threshold:
            boxes.append(norm_box(value))
    return boxes, records


def route_root(base: Path, score: str, variant: str) -> Path:
    if variant == "control":
        return (
            base
            / score
            / "intermediate"
            / "dense_full_pipeline_route"
            / "dense_candidate_reconstruction"
        )
    if variant == "candidate":
        return base / score / "dense_route" / "dense_candidate_reconstruction"
    raise ValueError(variant)


def route_summary_path(base: Path, score: str, variant: str) -> Path:
    return route_root(base, score, variant).parent / "dense_route_execution_summary.json"


def stage_paths(root: Path, score: str, page: str) -> dict[str, Path]:
    final_dir = root / "probe_rescue_candidates" / f"eval2_{score}_{page}"
    return {
        "raw_first_pass": (
            root
            / "probe_candidates_from_inventory"
            / score
            / page
            / "pipeline2_no_peak_candidates.json"
        ),
        "filtered_first_pass": (
            root
            / "probe_candidates_filtered"
            / score
            / page
            / "pipeline2_no_peak_candidates.json"
        ),
        "final_pre_cnn": final_dir / "pipeline2_no_peak_candidates.json",
        "scored": final_dir / "pipeline2_no_peak_scored.json",
        "accepted": final_dir / "pipeline2_no_peak_filtered_cnn.json",
    }


def producer_from_path(path_value: str | None) -> str:
    if not path_value:
        return "missing"
    text = path_value.replace("\\", "/")
    if "/current_support/" in text:
        return "B_current_x4_tree"
    if "/sr/batch/" in text:
        return "C_pinned_x4_tree"
    if "/baseline/batch/" in text:
        return "A_pinned_original_tree"
    return "unknown_tree"


def inventory_path(summary_path: Path, workspace: Path) -> Path | None:
    if not summary_path.is_file():
        return None
    payload = load_json(summary_path)
    for phase in payload.get("phases", []):
        if phase.get("name") == "load_route_image_paths" and phase.get("inventory"):
            return to_workspace(phase["inventory"], workspace)
    return None


def inventory_record(path: Path | None, score: str, page: str) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = load_json(path)
    for record in payload.get("records", []):
        if str(record.get("score")) == score and str(record.get("page")) == page:
            return dict(record)
    return None


def filter_page_record(root: Path, score: str, page: str) -> dict[str, Any] | None:
    path = root / "filter_apply_summary.json"
    if not path.is_file():
        return None
    payload = load_json(path)
    for record in payload.get("per_page", []):
        if str(record.get("score")) == score and str(record.get("page")) == page:
            return dict(record)
    return None


def mask_provenance(
    *,
    summary_path: Path,
    dense_root: Path,
    score: str,
    page: str,
    workspace: Path,
) -> dict[str, Any]:
    inv_path = inventory_path(summary_path, workspace)
    record = inventory_record(inv_path, score, page)
    filter_record = filter_page_record(dense_root, score, page)
    staff = None if record is None else record.get("staff_mask")
    explicit_clef = None if record is None else record.get("clef_mask")
    resolved_clef = None if filter_record is None else filter_record.get("clef_mask_path")
    hybrid = None if record is None else record.get("hybrid_predictions")
    return {
        "inventory": None if inv_path is None else str(inv_path),
        "inventory_exists": bool(inv_path and inv_path.is_file()),
        "inventory_record_found": record is not None,
        "image": None if record is None else record.get("image"),
        "hybrid_predictions": hybrid,
        "hybrid_path_tree": producer_from_path(str(hybrid) if hybrid else None),
        "staff_mask": staff,
        "staff_mask_path_tree": producer_from_path(str(staff) if staff else None),
        "explicit_clef_mask": explicit_clef,
        "explicit_clef_path_tree": producer_from_path(
            str(explicit_clef) if explicit_clef else None
        ),
        "resolved_filter_clef_mask": resolved_clef,
        "resolved_filter_clef_path_tree": producer_from_path(
            str(resolved_clef) if resolved_clef else None
        ),
        "filter_record": filter_record,
        "ownership": {
            "mask_pixel_generation": "upstream_homr",
            "inventory_selection_and_filter_handoff": "pdfscore_upstream_orchestration",
            "candidate_filter_algorithm": "pdfscore_extension",
        },
    }


def adjacency(predictions: Sequence[Box], gt: Sequence[Box]) -> list[list[int]]:
    return [
        [
            gt_index
            for gt_index, target in enumerate(gt)
            if is_barline_match(
                pred,
                target,
                rule_name="center_anchor",
                vov_threshold=0.5,
                xdist_threshold=12.0,
            )
        ]
        for pred in predictions
    ]


def maximum_matching(
    pred_to_gt: Sequence[Sequence[int]], gt_count: int
) -> tuple[int, list[int]]:
    gt_owner = [-1] * gt_count

    def augment(pred_index: int, seen: set[int]) -> bool:
        for gt_index in pred_to_gt[pred_index]:
            if gt_index in seen:
                continue
            seen.add(gt_index)
            owner = gt_owner[gt_index]
            if owner == -1 or augment(owner, seen):
                gt_owner[gt_index] = pred_index
                return True
        return False

    matched = 0
    for pred_index in range(len(pred_to_gt)):
        if augment(pred_index, set()):
            matched += 1
    return matched, gt_owner


def component_for_target(
    predictions: Sequence[Box],
    gt: Sequence[Box],
    target_gt_index: int,
) -> dict[str, Any]:
    pred_to_gt = adjacency(predictions, gt)
    gt_to_pred: list[list[int]] = [[] for _ in gt]
    for pred_index, gt_indices in enumerate(pred_to_gt):
        for gt_index in gt_indices:
            gt_to_pred[gt_index].append(pred_index)

    seen_gt = {target_gt_index}
    seen_pred: set[int] = set()
    queue: deque[tuple[str, int]] = deque([("gt", target_gt_index)])
    while queue:
        kind, index = queue.popleft()
        if kind == "gt":
            for pred_index in gt_to_pred[index]:
                if pred_index not in seen_pred:
                    seen_pred.add(pred_index)
                    queue.append(("pred", pred_index))
        else:
            for gt_index in pred_to_gt[index]:
                if gt_index not in seen_gt:
                    seen_gt.add(gt_index)
                    queue.append(("gt", gt_index))

    component_preds = sorted(seen_pred)
    component_gts = sorted(seen_gt)
    local_gt_map = {
        global_index: local_index
        for local_index, global_index in enumerate(component_gts)
    }
    local_adj = [
        [
            local_gt_map[gt_index]
            for gt_index in pred_to_gt[pred_index]
            if gt_index in local_gt_map
        ]
        for pred_index in component_preds
    ]
    matched, gt_owner = maximum_matching(local_adj, len(component_gts))
    unmatched_global = [
        component_gts[local_index]
        for local_index, owner in enumerate(gt_owner)
        if owner == -1
    ]
    prediction_rows = []
    for pred_index in component_preds:
        matches = sorted(pred_to_gt[pred_index])
        prediction_rows.append(
            {
                "pred_index": pred_index,
                "bbox": list(predictions[pred_index]),
                "matched_gt_indices": matches,
                "degree": len(matches),
            }
        )

    return {
        "target_gt_index": target_gt_index,
        "target_gt_bbox": list(gt[target_gt_index]),
        "component_gt_indices": component_gts,
        "component_gt_bboxes": [list(gt[index]) for index in component_gts],
        "component_prediction_count": len(component_preds),
        "component_gt_count": len(component_gts),
        "maximum_cardinality": matched,
        "capacity_deficit": len(component_gts) - matched,
        "unmatched_gt_indices_in_one_maximum_matching": unmatched_global,
        "ambiguous_prediction_count": sum(
            1 for row in prediction_rows if row["degree"] > 1
        ),
        "predictions": prediction_rows,
    }


def stage_payload(
    path: Path, gt: list[Box], target_index: int, threshold: float
) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    if path.name == "pipeline2_no_peak_scored.json":
        boxes, scored = load_scored_boxes(path, threshold)
        extra = {
            "score_threshold": threshold,
            "scored_record_count": len(scored),
            "passing_score_count": len(boxes),
        }
    else:
        boxes = load_candidate_boxes(path)
        extra = {}
    return {
        "path": str(path),
        "exists": True,
        "box_count": len(boxes),
        **extra,
        "target_component": component_for_target(boxes, gt, target_index),
    }


def first_capacity_divergence(
    control: Mapping[str, Any], candidate: Mapping[str, Any]
) -> str | None:
    for stage in (
        "raw_first_pass",
        "filtered_first_pass",
        "final_pre_cnn",
        "scored",
        "accepted",
    ):
        c = control.get(stage, {})
        b = candidate.get(stage, {})
        ccomp = c.get("target_component") if isinstance(c, Mapping) else None
        bcomp = b.get("target_component") if isinstance(b, Mapping) else None
        if not isinstance(ccomp, Mapping) or not isinstance(bcomp, Mapping):
            continue
        if int(bcomp.get("capacity_deficit", 0)) > int(
            ccomp.get("capacity_deficit", 0)
        ):
            return stage
        if int(bcomp.get("maximum_cardinality", 0)) < int(
            ccomp.get("maximum_cardinality", 0)
        ):
            return stage
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--residual-report", type=Path, default=DEFAULT_RESIDUAL)
    parser.add_argument("--control-root", type=Path, default=DEFAULT_CONTROL_ROOT)
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--gt-root", type=Path, default=DEFAULT_GT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    residual_path = to_workspace(args.residual_report, workspace)
    control_root = to_workspace(args.control_root, workspace)
    candidate_root = to_workspace(args.candidate_root, workspace)
    gt_root = to_workspace(args.gt_root, workspace)
    output = to_workspace(args.output, workspace)

    residual = load_json(residual_path)
    pages_out: list[dict[str, Any]] = []
    first_divergences: dict[str, int] = {}

    for page_record in residual.get("pages", []):
        score = str(page_record["score"])
        page = str(page_record["page"])
        gt_path = gt_root / score / page / "boxes_sorted.json"
        gt = list(boxes_from_gt(load_json(gt_path)))

        roots = {
            "control": route_root(control_root, score, "control"),
            "candidate": route_root(candidate_root, score, "candidate"),
        }
        summaries = {
            "control": route_summary_path(control_root, score, "control"),
            "candidate": route_summary_path(candidate_root, score, "candidate"),
        }
        masks = {
            name: mask_provenance(
                summary_path=summaries[name],
                dense_root=roots[name],
                score=score,
                page=page,
                workspace=workspace,
            )
            for name in ("control", "candidate")
        }

        targets: list[dict[str, Any]] = []
        for residual_row in page_record.get("residuals", []):
            target_index = int(residual_row["gt_index"])
            variants: dict[str, Any] = {}
            for name in ("control", "candidate"):
                paths = stage_paths(roots[name], score, page)
                variants[name] = {
                    stage: stage_payload(
                        path, gt, target_index, args.score_threshold
                    )
                    for stage, path in paths.items()
                }
            first = first_capacity_divergence(
                variants["control"], variants["candidate"]
            )
            key = first or "none"
            first_divergences[key] = first_divergences.get(key, 0) + 1
            targets.append(
                {
                    "gt_index": target_index,
                    "gt_bbox": list(gt[target_index]),
                    "historical_classification": residual_row.get("classification"),
                    "first_candidate_capacity_divergence": first,
                    "variants": variants,
                }
            )

        pages_out.append(
            {
                "score": score,
                "page": page,
                "control_dense_root": str(roots["control"]),
                "candidate_dense_root": str(roots["candidate"]),
                "mask_provenance": masks,
                "targets": targets,
            }
        )

    result = {
        "schema_version": "issue274.stage_e_multiplicity_and_mask_provenance.v1",
        "status": "completed",
        "scope": {
            "page_count": len(pages_out),
            "target_count": sum(len(page["targets"]) for page in pages_out),
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_reexecuted": False,
            "filter_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
        },
        "ownership": {
            "stage_e_dense_generation": "pdfscore_extension",
            "stage_e_candidate_filter": "pdfscore_extension",
            "stage_e_probe_rescue": "pdfscore_extension",
            "stage_e_barline_cnn": "pdfscore_extension",
            "staff_clef_mask_pixels": "upstream_homr_data",
            "mask_inventory_selection_and_handoff": "pdfscore_upstream_orchestration",
        },
        "matching_contract": {
            "rule": "center_anchor",
            "vov_threshold": 0.5,
            "xdist_threshold_px": 12.0,
            "analysis": (
                "For each target GT, construct the connected bipartite component of GT slots "
                "and predictions. A capacity deficit means the component has fewer mutually "
                "assignable predictions than GT identities, even if one prediction individually "
                "matches multiple GT boxes."
            ),
        },
        "first_candidate_capacity_divergence_counts": first_divergences,
        "pages": pages_out,
        "design_guardrails": [
            "Do not treat x proximity alone as barline identity.",
            "Separate evidence support from topology/identity multiplicity.",
            "Any suppression identity change must cover both Stage-E dense passes.",
            "Do not infer that C is removable until staff/clef inventory dependencies are assigned to a chosen producer bundle.",
        ],
    }
    write_json(output, result)
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "summary": first_divergences,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
