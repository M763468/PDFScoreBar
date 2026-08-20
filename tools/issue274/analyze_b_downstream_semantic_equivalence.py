#!/usr/bin/env python3
"""Audit whether the retained B-only Stage-E detector delta is downstream-semantic.

This is a retained-artifact, CPU-only Issue #274 gate.  It does NOT rerun HOMR,
SR, OMR-DLN, dense probe generation, candidate filtering, the barline CNN, MMR,
or OCR.

Why this gate exists
--------------------
The B-only x4 experiment loses detector one-to-one matching cardinality on three
pages whose evaluation GT contains overlapping, near-same-x logical boxes on one
continuous printed barline.  Production measure numbering, however, intentionally
deduplicates system barlines that are closer than ``MeasureNumberer``'s x-distance
threshold.  Before inventing a new detector filter merely to reproduce evaluation
multiplicity, compare the actual downstream base-numbering semantics of the retained
control and retained B-only accepted barline sets across all 68 canonical pages.

The report separates:
- detector/evaluation multiplicity (raw accepted boxes),
- system/staff grouping semantics,
- base measure-count / numbering semantics,
- measure-boundary geometry (exact and tolerant), and
- the focused affected GT components' downstream x-cluster identity.

Connector semantics are resolved through the normal production numbering contract
from the authoritative A/original staff mask, so both control and B are compared
under the same current-support connector evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2

from src.common.barline_evaluation import is_barline_match
from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score
from tools.issue120.eval_full68_from_intermediates import SCORES

AB_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/issue274_homr_x4_stage_e_ab.json"
)
MULTIPLICITY_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_multiplicity_provenance_01/"
    "issue274_stage_e_multiplicity_and_mask_provenance.json"
)
CONTROL_ROOT_DEFAULT = Path(
    "logs/verification/detector_full68/"
    "issue255_production_restore_full68_top_level_worker_01/production_runs"
)
CANDIDATE_ROOT_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/candidate_stage_e"
)
OUTPUT_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/"
    "b_downstream_semantic_equivalence_01/"
    "issue274_b_downstream_semantic_equivalence.json"
)

Box = tuple[int, int, int, int]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    return tuple(int(round(float(v))) for v in values[:4])  # type: ignore[return-value]


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
    boxes: list[Box] = []
    for item in records:
        if isinstance(item, (list, tuple)) and len(item) >= 4:
            boxes.append(norm_box(item))
            continue
        if not isinstance(item, Mapping):
            continue
        for key in ("bbox", "orig_bbox", "pred_bbox", "barline_location"):
            value = item.get(key)
            if isinstance(value, (list, tuple)) and len(value) >= 4:
                boxes.append(norm_box(value))
                break
    return boxes


def discover_a_staff_mask(a_path: Path, page: str) -> Path:
    parent = a_path.parent
    for name in (
        f"{page}_staff_mask.png",
        f"{page}_proxy_debug_3_staff.png",
        f"{page}_debug_3_staff.png",
    ):
        candidate = parent / name
        if candidate.is_file():
            return candidate
    found: list[Path] = []
    for pattern in ("*_staff_mask.png", "*_proxy_debug_3_staff.png", "*_debug_3_staff.png"):
        found.extend(parent.glob(pattern))
    if not found:
        raise FileNotFoundError(f"A staff mask not found beside {a_path}")
    return sorted(set(found))[0]


def accepted_path(root: Path, score: str, page: str) -> Path:
    return (
        root
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_filtered_cnn.json"
    )


def candidate_accepted_path(root: Path, score: str, page: str) -> Path:
    return (
        root
        / score
        / "dense_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_filtered_cnn.json"
    )


def page_signature(
    *,
    boxes: list[Box],
    staff_mask: Path,
    image: Any,
) -> dict[str, Any]:
    h, w = image.shape[:2]
    pipeline = MeasureNumberingPipeline()
    page = pipeline.process_page(
        [list(box) for box in boxes],
        staff_mask,
        (w, h),
        page_number=1,
        image=image,
    )
    score = Score(pages=[page])
    pipeline.numberer.number_score(score, start_number=1)

    systems: list[dict[str, Any]] = []
    for system in page.systems:
        systems.append(
            {
                "staff_bboxes": [
                    [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]
                    for staff in system.staves
                ],
                "staff_barline_counts": [len(staff.barlines) for staff in system.staves],
                "measure_count": len(system.measures),
                "measure_numbers": [measure.number for measure in system.measures],
                "measure_bboxes": [
                    [
                        measure.bbox.x1,
                        measure.bbox.y1,
                        measure.bbox.x2,
                        measure.bbox.y2,
                    ]
                    for measure in system.measures
                ],
            }
        )

    return {
        "input_barline_count": len(boxes),
        "system_count": len(page.systems),
        "staves_per_system": [len(system.staves) for system in page.systems],
        "measures_per_system": [len(system.measures) for system in page.systems],
        "total_measures": sum(len(system.measures) for system in page.systems),
        "systems": systems,
    }


def topology_signature(sig: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        sig["system_count"],
        tuple(sig["staves_per_system"]),
        tuple(sig["measures_per_system"]),
        sig["total_measures"],
        tuple(tuple(system["measure_numbers"]) for system in sig["systems"]),
    )


def geometry_delta(control: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    if topology_signature(control) != topology_signature(candidate):
        return {
            "comparable": False,
            "exact": False,
            "max_abs_x_delta": None,
            "max_abs_y_delta": None,
            "within_2px": False,
            "within_5px": False,
            "within_10px": False,
        }

    max_dx = 0
    max_dy = 0
    exact = True
    for c_sys, b_sys in zip(control["systems"], candidate["systems"]):
        for c_box, b_box in zip(c_sys["measure_bboxes"], b_sys["measure_bboxes"]):
            deltas = [abs(int(a) - int(b)) for a, b in zip(c_box, b_box)]
            max_dx = max(max_dx, deltas[0], deltas[2])
            max_dy = max(max_dy, deltas[1], deltas[3])
            exact = exact and all(delta == 0 for delta in deltas)
    return {
        "comparable": True,
        "exact": exact,
        "max_abs_x_delta": max_dx,
        "max_abs_y_delta": max_dy,
        "within_2px": max_dx <= 2 and max_dy <= 2,
        "within_5px": max_dx <= 5 and max_dy <= 5,
        "within_10px": max_dx <= 10 and max_dy <= 10,
    }


def cluster_x(boxes: Iterable[Box], threshold: int) -> list[list[Box]]:
    ordered = sorted(boxes, key=lambda box: ((box[0] + box[2]) / 2.0, box[1], box[3]))
    clusters: list[list[Box]] = []
    for box in ordered:
        cx = (box[0] + box[2]) / 2.0
        if not clusters:
            clusters.append([box])
            continue
        prev_cx = sum((item[0] + item[2]) / 2.0 for item in clusters[-1]) / len(clusters[-1])
        if abs(cx - prev_cx) < threshold:
            clusters[-1].append(box)
        else:
            clusters.append([box])
    return clusters


def matching_boxes(boxes: Iterable[Box], gt_boxes: Iterable[Box]) -> list[Box]:
    gts = list(gt_boxes)
    return [
        box
        for box in boxes
        if any(
            is_barline_match(
                box,
                gt,
                rule_name="center_anchor",
                vov_threshold=0.5,
                xdist_threshold=12.0,
            )
            for gt in gts
        )
    ]


def focused_targets(multiplicity: Mapping[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for page in multiplicity.get("pages", []):
        key = (str(page["score"]), str(page["page"]))
        rows: list[dict[str, Any]] = []
        for target in page.get("targets", []):
            control_component = (
                target.get("variants", {})
                .get("control", {})
                .get("accepted", {})
                .get("target_component")
            )
            if not isinstance(control_component, Mapping):
                control_component = (
                    target.get("variants", {})
                    .get("control", {})
                    .get("raw_first_pass", {})
                    .get("target_component")
                )
            if not isinstance(control_component, Mapping):
                continue
            component = control_component.get("component_gt_bboxes")
            if not isinstance(component, list):
                continue
            rows.append(
                {
                    "gt_index": target.get("gt_index"),
                    "gt_bbox": target.get("gt_bbox"),
                    "component_gt_bboxes": [norm_box(box) for box in component],
                    "first_candidate_capacity_divergence": target.get(
                        "first_candidate_capacity_divergence"
                    ),
                }
            )
        if rows:
            result[key] = rows
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--ab-report", type=Path, default=AB_DEFAULT)
    parser.add_argument("--multiplicity-report", type=Path, default=MULTIPLICITY_DEFAULT)
    parser.add_argument("--control-root", type=Path, default=CONTROL_ROOT_DEFAULT)
    parser.add_argument("--candidate-root", type=Path, default=CANDIDATE_ROOT_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    ab_path = to_workspace(args.ab_report, workspace)
    multiplicity_path = to_workspace(args.multiplicity_report, workspace)
    control_root = to_workspace(args.control_root, workspace)
    candidate_root = to_workspace(args.candidate_root, workspace)
    output = to_workspace(args.output, workspace)

    ab = load_json(ab_path)
    records = ab["hybrid_ab"]["pages"]
    if len(records) != 68:
        raise RuntimeError(f"Expected 68 AB page records, got {len(records)}")
    expected = {(score, page) for score, pages in SCORES.items() for page in pages}
    observed = {(str(row["score"]), str(row["page"])) for row in records}
    if observed != expected:
        raise RuntimeError(
            f"AB page set mismatch: missing={sorted(expected - observed)[:4]} extra={sorted(observed - expected)[:4]}"
        )

    multiplicity = load_json(multiplicity_path)
    target_map = focused_targets(multiplicity)
    dedup_threshold = int(MeasureNumberer.DEDUPLICATION_THRESHOLD)

    pages_out: list[dict[str, Any]] = []
    counts = {
        "pages": 0,
        "input_box_set_exact": 0,
        "topology_exact": 0,
        "measure_geometry_exact": 0,
        "measure_geometry_within_2px": 0,
        "measure_geometry_within_5px": 0,
        "measure_geometry_within_10px": 0,
    }

    for record in records:
        score_name = str(record["score"])
        page_name = str(record["page"])
        c_path = accepted_path(control_root, score_name, page_name)
        b_path = candidate_accepted_path(candidate_root, score_name, page_name)
        if not c_path.is_file():
            raise FileNotFoundError(c_path)
        if not b_path.is_file():
            raise FileNotFoundError(b_path)

        control_boxes = load_boxes(c_path)
        candidate_boxes = load_boxes(b_path)
        a_path = to_workspace(str(record["a_path"]), workspace)
        staff_mask = discover_a_staff_mask(a_path, page_name)
        image_path = workspace / "data" / "evaluation2" / "images" / score_name / f"{page_name}.png"
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)

        control_sig = page_signature(boxes=control_boxes, staff_mask=staff_mask, image=image)
        candidate_sig = page_signature(boxes=candidate_boxes, staff_mask=staff_mask, image=image)
        top_exact = topology_signature(control_sig) == topology_signature(candidate_sig)
        geom = geometry_delta(control_sig, candidate_sig)
        box_exact = set(control_boxes) == set(candidate_boxes)

        counts["pages"] += 1
        counts["input_box_set_exact"] += int(box_exact)
        counts["topology_exact"] += int(top_exact)
        counts["measure_geometry_exact"] += int(bool(geom["exact"]))
        counts["measure_geometry_within_2px"] += int(bool(geom["within_2px"]))
        counts["measure_geometry_within_5px"] += int(bool(geom["within_5px"]))
        counts["measure_geometry_within_10px"] += int(bool(geom["within_10px"]))

        focused: list[dict[str, Any]] = []
        for target in target_map.get((score_name, page_name), []):
            component_gts = target["component_gt_bboxes"]
            c_matches = matching_boxes(control_boxes, component_gts)
            b_matches = matching_boxes(candidate_boxes, component_gts)
            c_clusters = cluster_x(c_matches, dedup_threshold)
            b_clusters = cluster_x(b_matches, dedup_threshold)
            focused.append(
                {
                    "gt_index": target["gt_index"],
                    "gt_bbox": target["gt_bbox"],
                    "first_candidate_capacity_divergence": target[
                        "first_candidate_capacity_divergence"
                    ],
                    "component_gt_bboxes": [list(box) for box in component_gts],
                    "control_matching_boxes": [list(box) for box in c_matches],
                    "candidate_matching_boxes": [list(box) for box in b_matches],
                    "control_downstream_x_cluster_count": len(c_clusters),
                    "candidate_downstream_x_cluster_count": len(b_clusters),
                    "control_downstream_x_clusters": [
                        [list(box) for box in cluster] for cluster in c_clusters
                    ],
                    "candidate_downstream_x_clusters": [
                        [list(box) for box in cluster] for cluster in b_clusters
                    ],
                    "same_downstream_x_identity_count": len(c_clusters) == len(b_clusters),
                }
            )

        pages_out.append(
            {
                "score": score_name,
                "page": page_name,
                "control_accepted": str(c_path),
                "candidate_accepted": str(b_path),
                "a_staff_mask": str(staff_mask),
                "image": str(image_path),
                "input_barline_set_exact": box_exact,
                "input_barline_counts": {
                    "control": len(control_boxes),
                    "candidate": len(candidate_boxes),
                },
                "topology_exact": top_exact,
                "geometry": geom,
                "control_signature": control_sig,
                "candidate_signature": candidate_sig,
                "focused_targets": focused,
            }
        )

    changed_topology = [
        {"score": row["score"], "page": row["page"]}
        for row in pages_out
        if not row["topology_exact"]
    ]
    changed_geometry = [
        {
            "score": row["score"],
            "page": row["page"],
            "geometry": row["geometry"],
        }
        for row in pages_out
        if not row["geometry"]["exact"]
    ]
    focused_rows = [
        {
            "score": page["score"],
            "page": page["page"],
            **target,
        }
        for page in pages_out
        for target in page["focused_targets"]
    ]

    result = {
        "schema_version": "issue274.b_downstream_semantic_equivalence.v1",
        "status": "completed",
        "scope": {
            "page_count": len(pages_out),
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_reexecuted": False,
            "filter_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
            "base_numbering_reexecuted": True,
        },
        "production_semantics": {
            "measure_numberer_x_deduplication_threshold_px": dedup_threshold,
            "interpretation": (
                "Accepted barline boxes closer than this x threshold collapse to one logical "
                "system boundary before measure construction. The focused detector GT "
                "multiplicity is therefore not automatically downstream multiplicity."
            ),
        },
        "summary": {
            **counts,
            "topology_changed_page_count": len(changed_topology),
            "geometry_changed_page_count": len(changed_geometry),
            "focused_target_count": len(focused_rows),
            "focused_same_downstream_x_identity_count": sum(
                int(bool(row["same_downstream_x_identity_count"])) for row in focused_rows
            ),
        },
        "topology_changed_pages": changed_topology,
        "geometry_changed_pages": changed_geometry,
        "focused_targets": focused_rows,
        "decision_rule": {
            "do_not_add_detector_rule_if": [
                "focused control/B differences collapse to the same downstream x identity",
                "full68 base-numbering topology is unchanged",
                "remaining geometry differences are absent or small enough for the next explicit MMR geometry gate",
            ],
            "investigate_detector_coexistence_rule_only_if": (
                "B changes actual downstream system/measure topology, or a focused detector multiplicity "
                "maps to more than one downstream x identity."
            ),
            "next_if_topology_equivalent": (
                "Treat the p013/p015/Sibelius one-to-one detector losses as evaluation-cardinality "
                "artifacts for Issue #274, keep detector suppression conservative, and separately gate "
                "any changed measure geometry against retained MMR behavior before removing C."
            ),
        },
        "pages": pages_out,
    }
    write_json(output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "summary": result["summary"],
                "output": str(output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
