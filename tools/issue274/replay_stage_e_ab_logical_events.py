#!/usr/bin/env python3
"""Replay Issue #274 Stage-E A/B evaluation under an audited physical-event GT view.

This is retained-artifact only. It does not rerun HOMR, SR, OMR-DLN, dense
candidate generation/filtering, CNN, MMR, or numbering.

The authoritative GT files are left untouched. P1 pairs from the Issue #274 GT
near-duplicate audit are treated as a *review hypothesis*: both member boxes
represent one physical vertical-line event. P3 double/end/repeat pairs remain
separate physical events.

For each retained Stage-E boundary the report records:
- legacy/raw-slot greedy metrics (for reproduction of the existing evaluator);
- raw-slot maximum-cardinality metrics (to expose greedy assignment artifacts);
- audited physical-event maximum-cardinality metrics;
- P1-event and non-P1-event independent coverage.

The purpose is not to declare GT corrections automatically. It is to determine
whether the apparent C->B regression survives after removing invalid duplicate
identity/capacity assumptions and evaluator assignment artifacts.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.common.barline_evaluation import greedy_barline_match, is_barline_match

Box = tuple[int, int, int, int]

DEFAULT_AUDIT = Path(
    "logs/issue274_homr_unification_analysis/"
    "evaluation2_gt_near_duplicate_audit_01/"
    "issue274_evaluation2_gt_near_duplicate_audit.json"
)
DEFAULT_AB = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/issue274_homr_x4_stage_e_ab.json"
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
    "logs/issue274_homr_unification_analysis/stage_e_logical_event_replay_01/"
    "issue274_stage_e_logical_event_replay.json"
)

STAGES = (
    "hybrid",
    "raw_first_pass",
    "filtered_first_pass",
    "final_pre_cnn",
    "scored",
    "accepted",
)


@dataclass(frozen=True)
class Event:
    event_id: str
    member_indices: tuple[int, ...]
    members: tuple[Box, ...]
    classification: str


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


def norm_box(values: Iterable[Any]) -> Box:
    vals = list(values)
    if len(vals) < 4:
        raise ValueError(f"Expected four bbox values, got {vals!r}")
    return tuple(int(round(float(v))) for v in vals[:4])  # type: ignore[return-value]


def extract_box(item: Any) -> Box | None:
    if isinstance(item, (list, tuple)) and len(item) >= 4:
        return norm_box(item)
    if not isinstance(item, Mapping):
        return None
    for key in ("orig_bbox", "bbox", "pred_bbox", "barline_location"):
        value = item.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            return norm_box(value)
    return None


def records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in ("predictions", "boxes", "detections"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def load_boxes(path: Path) -> list[Box]:
    return [
        box
        for box in (extract_box(item) for item in records_from_payload(load_json(path)))
        if box is not None
    ]


def load_scored_boxes(path: Path, threshold: float) -> tuple[list[Box], int]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected scored list: {path}")
    boxes: list[Box] = []
    record_count = 0
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        box = extract_box(item)
        if box is None:
            continue
        record_count += 1
        if float(item.get("score", 0.0)) >= threshold:
            boxes.append(box)
    return boxes, record_count


def load_gt(path: Path) -> list[Box]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected GT list: {path}")
    boxes = []
    for item in payload:
        box = extract_box(item)
        if box is None:
            raise ValueError(f"GT row lacks bbox in {path}: {item!r}")
        boxes.append(box)
    return boxes


def control_dense_root(base: Path, score: str) -> Path:
    return (
        base
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
    )


def candidate_dense_root(base: Path, score: str) -> Path:
    return base / score / "dense_route" / "dense_candidate_reconstruction"


def stage_paths(
    *,
    score: str,
    page: str,
    variant: str,
    dense_root: Path,
    ab_page: Mapping[str, Any],
) -> dict[str, Path]:
    if variant == "control":
        hybrid = Path(str(ab_page["retained_hybrid"]))
    else:
        hybrid = Path(str(ab_page["candidate_hybrid"]))

    final_dir = dense_root / "probe_rescue_candidates" / f"eval2_{score}_{page}"
    return {
        "hybrid": hybrid,
        "raw_first_pass": (
            dense_root
            / "probe_candidates_from_inventory"
            / score
            / page
            / "pipeline2_no_peak_candidates.json"
        ),
        "filtered_first_pass": (
            dense_root
            / "probe_candidates_filtered"
            / score
            / page
            / "pipeline2_no_peak_candidates.json"
        ),
        "final_pre_cnn": final_dir / "pipeline2_no_peak_candidates.json",
        "scored": final_dir / "pipeline2_no_peak_scored.json",
        "accepted": final_dir / "pipeline2_no_peak_filtered_cnn.json",
    }


def match(pred: Box, gt: Box) -> bool:
    return is_barline_match(
        pred,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def maximum_matching(
    adjacency: Sequence[Sequence[int]], target_count: int
) -> tuple[int, list[int]]:
    target_owner = [-1] * target_count

    def augment(pred_index: int, seen: set[int]) -> bool:
        for target_index in adjacency[pred_index]:
            if target_index in seen:
                continue
            seen.add(target_index)
            owner = target_owner[target_index]
            if owner == -1 or augment(owner, seen):
                target_owner[target_index] = pred_index
                return True
        return False

    matched = 0
    for pred_index in range(len(adjacency)):
        if augment(pred_index, set()):
            matched += 1
    return matched, target_owner


def raw_slot_maximum(predictions: Sequence[Box], gt: Sequence[Box]) -> dict[str, Any]:
    adjacency = [
        [gt_index for gt_index, target in enumerate(gt) if match(pred, target)]
        for pred in predictions
    ]
    matched, owner = maximum_matching(adjacency, len(gt))
    unmatched = [index for index, pred_owner in enumerate(owner) if pred_owner == -1]
    return {
        "tp": matched,
        "fn": len(gt) - matched,
        "unmatched_gt_indices": unmatched,
        "ambiguous_prediction_count": sum(len(edges) > 1 for edges in adjacency),
    }


def raw_slot_greedy(predictions: Sequence[Box], gt: Sequence[Box]) -> dict[str, Any]:
    result = greedy_barline_match(
        predictions,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    return {
        "pred": len(predictions),
        "gt": len(gt),
        "tp": len(result.matches),
        "fp": len(result.false_positive_indices),
        "fn": len(result.false_negative_indices),
        "soft_duplicate_or_repeat_like": len(result.soft_matches),
        "false_negative_indices": result.false_negative_indices,
    }


def event_adjacency(predictions: Sequence[Box], events: Sequence[Event]) -> list[list[int]]:
    return [
        [
            event_index
            for event_index, event in enumerate(events)
            if any(match(pred, member) for member in event.members)
        ]
        for pred in predictions
    ]


def event_maximum(predictions: Sequence[Box], events: Sequence[Event]) -> dict[str, Any]:
    adjacency = event_adjacency(predictions, events)
    matched, owner = maximum_matching(adjacency, len(events))
    unmatched = [index for index, pred_owner in enumerate(owner) if pred_owner == -1]
    return {
        "event_count": len(events),
        "tp": matched,
        "fn": len(events) - matched,
        "unmatched_event_indices": unmatched,
        "unmatched_events": [
            {
                "event_id": events[index].event_id,
                "classification": events[index].classification,
                "member_indices": list(events[index].member_indices),
                "members": [list(box) for box in events[index].members],
            }
            for index in unmatched
        ],
        "ambiguous_prediction_count": sum(len(edges) > 1 for edges in adjacency),
    }


def subgroup_coverage(
    predictions: Sequence[Box],
    events: Sequence[Event],
    *,
    classification: str,
) -> dict[str, Any]:
    subset = [event for event in events if event.classification == classification]
    result = event_maximum(predictions, subset)
    result["classification"] = classification
    return result


def build_events(
    gt: Sequence[Box],
    p1_pairs: Sequence[Mapping[str, Any]],
    *,
    score: str,
    page: str,
) -> tuple[list[Event], list[dict[str, Any]]]:
    consumed: set[int] = set()
    pair_rows: list[dict[str, Any]] = []
    grouped: dict[int, tuple[int, int]] = {}

    for pair in p1_pairs:
        a = pair.get("a")
        b = pair.get("b")
        if not isinstance(a, Mapping) or not isinstance(b, Mapping):
            raise ValueError(f"Malformed P1 pair for {score}/{page}: {pair!r}")
        ia = int(a["index"])
        ib = int(b["index"])
        if ia == ib or ia in consumed or ib in consumed:
            raise ValueError(f"Overlapping P1 GT grouping for {score}/{page}: {ia}, {ib}")
        if ia >= len(gt) or ib >= len(gt):
            raise IndexError(f"P1 GT index out of range for {score}/{page}: {ia}, {ib}")
        ba = norm_box(a["bbox"])
        bb = norm_box(b["bbox"])
        if gt[ia] != ba or gt[ib] != bb:
            raise RuntimeError(
                f"Audit/GT mismatch for {score}/{page} pair {pair.get('pair_id')}: "
                f"a={gt[ia]} vs {ba}, b={gt[ib]} vs {bb}"
            )
        consumed.update((ia, ib))
        anchor = min(ia, ib)
        grouped[anchor] = (ia, ib)
        pair_rows.append(
            {
                "pair_id": pair.get("pair_id"),
                "indices": [ia, ib],
                "bboxes": [list(ba), list(bb)],
                "matches_existing_gui_auto_dedup": bool(
                    pair.get("matches_existing_gui_auto_dedup")
                ),
            }
        )

    events: list[Event] = []
    for index, box in enumerate(gt):
        if index in consumed:
            if index not in grouped:
                continue
            ia, ib = grouped[index]
            events.append(
                Event(
                    event_id=f"p1:{score}/{page}:{ia}+{ib}",
                    member_indices=(ia, ib),
                    members=(gt[ia], gt[ib]),
                    classification="p1_collapsed_review_hypothesis",
                )
            )
        else:
            events.append(
                Event(
                    event_id=f"singleton:{score}/{page}:{index}",
                    member_indices=(index,),
                    members=(box,),
                    classification="singleton",
                )
            )
    return events, pair_rows


def metrics_delta(candidate: Mapping[str, Any], control: Mapping[str, Any]) -> dict[str, int]:
    return {key: int(candidate.get(key, 0)) - int(control.get(key, 0)) for key in ("tp", "fn")}


def page_stage_payload(
    *,
    predictions: Sequence[Box],
    gt: Sequence[Box],
    events: Sequence[Event],
    path: Path,
    scored_record_count: int | None = None,
) -> dict[str, Any]:
    payload = {
        "path": str(path),
        "prediction_count": len(predictions),
        "raw_slot_greedy": raw_slot_greedy(predictions, gt),
        "raw_slot_maximum": raw_slot_maximum(predictions, gt),
        "physical_event_maximum": event_maximum(predictions, events),
        "p1_event_independent": subgroup_coverage(
            predictions,
            events,
            classification="p1_collapsed_review_hypothesis",
        ),
        "singleton_event_independent": subgroup_coverage(
            predictions,
            events,
            classification="singleton",
        ),
    }
    if scored_record_count is not None:
        payload["scored_record_count"] = scored_record_count
    return payload


def aggregate_stage(
    page_rows: Sequence[Mapping[str, Any]],
    *,
    stage: str,
    variant: str,
    key: str,
) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for page in page_rows:
        metrics = page["variants"][variant][stage][key]
        for field in (
            "event_count",
            "gt",
            "pred",
            "tp",
            "fp",
            "fn",
            "soft_duplicate_or_repeat_like",
        ):
            if field in metrics:
                totals[field] += int(metrics[field])
    return dict(totals)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--ab-report", type=Path, default=DEFAULT_AB)
    parser.add_argument("--control-root", type=Path, default=DEFAULT_CONTROL_ROOT)
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--gt-root", type=Path, default=DEFAULT_GT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    audit_path = to_workspace(args.audit, workspace)
    ab_path = to_workspace(args.ab_report, workspace)
    control_root = to_workspace(args.control_root, workspace)
    candidate_root = to_workspace(args.candidate_root, workspace)
    gt_root = to_workspace(args.gt_root, workspace)
    output = to_workspace(args.output, workspace)

    audit = load_json(audit_path)
    ab = load_json(ab_path)
    ab_pages = ab["hybrid_ab"]["pages"]
    if len(ab_pages) != 68:
        raise RuntimeError(f"Expected 68 A/B pages, got {len(ab_pages)}")

    audit_pages = {(str(row["score"]), str(row["page"])): row for row in audit.get("pages", [])}
    if len(audit_pages) != 68:
        raise RuntimeError(f"Expected 68 audit pages, got {len(audit_pages)}")

    p1_total = int(
        audit.get("summary", {})
        .get("classification_counts", {})
        .get("ordinary_same_ink_high_overlap", 0)
    )

    page_rows: list[dict[str, Any]] = []
    seen_pages: set[tuple[str, str]] = set()
    grouped_pair_total = 0

    for ab_page in ab_pages:
        score = str(ab_page["score"])
        page = str(ab_page["page"])
        key = (score, page)
        if key in seen_pages:
            raise RuntimeError(f"Duplicate A/B page: {key}")
        seen_pages.add(key)
        audit_page = audit_pages.get(key)
        if audit_page is None:
            raise RuntimeError(f"Audit page missing for A/B page: {key}")

        p1_pairs = [
            pair
            for pair in audit_page.get("pairs", [])
            if pair.get("priority") == "P1"
            and pair.get("classification") == "ordinary_same_ink_high_overlap"
        ]
        grouped_pair_total += len(p1_pairs)

        gt_path = gt_root / score / page / "boxes_sorted.json"
        gt = load_gt(gt_path)
        if len(gt) != int(audit_page["sorted_count"]):
            raise RuntimeError(
                f"GT count mismatch for {score}/{page}: {len(gt)} vs {audit_page['sorted_count']}"
            )
        events, p1_rows = build_events(gt, p1_pairs, score=score, page=page)

        dense_roots = {
            "control": control_dense_root(control_root, score),
            "candidate": candidate_dense_root(candidate_root, score),
        }
        variants: dict[str, Any] = {}
        for variant in ("control", "candidate"):
            paths = stage_paths(
                score=score,
                page=page,
                variant=variant,
                dense_root=dense_roots[variant],
                ab_page=ab_page,
            )
            stage_rows: dict[str, Any] = {}
            for stage in STAGES:
                path = to_workspace(paths[stage], workspace)
                if not path.is_file():
                    raise FileNotFoundError(f"Missing retained {variant}/{stage}: {path}")
                scored_count = None
                if stage == "scored":
                    predictions, scored_count = load_scored_boxes(path, args.score_threshold)
                else:
                    predictions = load_boxes(path)
                stage_rows[stage] = page_stage_payload(
                    predictions=predictions,
                    gt=gt,
                    events=events,
                    path=path,
                    scored_record_count=scored_count,
                )
            variants[variant] = stage_rows

        page_rows.append(
            {
                "score": score,
                "page": page,
                "gt_path": str(gt_path),
                "raw_gt_count": len(gt),
                "physical_event_count_under_p1_hypothesis": len(events),
                "p1_pair_count": len(p1_pairs),
                "p1_pairs": p1_rows,
                "variants": variants,
                "accepted_deltas": {
                    "raw_slot_greedy": metrics_delta(
                        variants["candidate"]["accepted"]["raw_slot_greedy"],
                        variants["control"]["accepted"]["raw_slot_greedy"],
                    ),
                    "raw_slot_maximum": metrics_delta(
                        variants["candidate"]["accepted"]["raw_slot_maximum"],
                        variants["control"]["accepted"]["raw_slot_maximum"],
                    ),
                    "physical_event_maximum": metrics_delta(
                        variants["candidate"]["accepted"]["physical_event_maximum"],
                        variants["control"]["accepted"]["physical_event_maximum"],
                    ),
                    "p1_event_independent": metrics_delta(
                        variants["candidate"]["accepted"]["p1_event_independent"],
                        variants["control"]["accepted"]["p1_event_independent"],
                    ),
                    "singleton_event_independent": metrics_delta(
                        variants["candidate"]["accepted"]["singleton_event_independent"],
                        variants["control"]["accepted"]["singleton_event_independent"],
                    ),
                },
            }
        )

    if grouped_pair_total != p1_total:
        raise RuntimeError(
            f"P1 grouped pair count mismatch: grouped={grouped_pair_total}, audit={p1_total}"
        )

    aggregate: dict[str, Any] = {}
    for stage in STAGES:
        aggregate[stage] = {}
        for variant in ("control", "candidate"):
            aggregate[stage][variant] = {
                metric_key: aggregate_stage(
                    page_rows,
                    stage=stage,
                    variant=variant,
                    key=metric_key,
                )
                for metric_key in (
                    "raw_slot_greedy",
                    "raw_slot_maximum",
                    "physical_event_maximum",
                    "p1_event_independent",
                    "singleton_event_independent",
                )
            }

    expected_control = ab.get("metrics", {}).get("control", {})
    expected_candidate = ab.get("metrics", {}).get("candidate", {})
    accepted_control = aggregate["accepted"]["control"]["raw_slot_greedy"]
    accepted_candidate = aggregate["accepted"]["candidate"]["raw_slot_greedy"]

    def legacy_reproduction(
        actual: Mapping[str, Any], expected: Mapping[str, Any]
    ) -> dict[str, Any]:
        keys = ("gt", "pred", "tp", "fp", "fn")
        comparison = {
            key: {
                "actual": actual.get(key),
                "expected": expected.get(key),
                "exact": actual.get(key) == expected.get(key),
            }
            for key in keys
        }
        return {
            "exact": all(row["exact"] for row in comparison.values()),
            "fields": comparison,
        }

    control_repro = legacy_reproduction(accepted_control, expected_control)
    candidate_repro = legacy_reproduction(accepted_candidate, expected_candidate)

    accepted_summary = {
        variant: {
            metric_key: aggregate["accepted"][variant][metric_key]
            for metric_key in (
                "raw_slot_greedy",
                "raw_slot_maximum",
                "physical_event_maximum",
                "p1_event_independent",
                "singleton_event_independent",
            )
        }
        for variant in ("control", "candidate")
    }

    physical_control = accepted_summary["control"]["physical_event_maximum"]
    physical_candidate = accepted_summary["candidate"]["physical_event_maximum"]
    singleton_control = accepted_summary["control"]["singleton_event_independent"]
    singleton_candidate = accepted_summary["candidate"]["singleton_event_independent"]

    changed_physical_pages = [
        {
            "score": page["score"],
            "page": page["page"],
            "physical_event_maximum": page["accepted_deltas"]["physical_event_maximum"],
            "singleton_event_independent": page["accepted_deltas"]["singleton_event_independent"],
            "p1_pair_count": page["p1_pair_count"],
        }
        for page in page_rows
        if page["accepted_deltas"]["physical_event_maximum"]["tp"] != 0
        or page["accepted_deltas"]["physical_event_maximum"]["fn"] != 0
    ]

    result = {
        "schema_version": "issue274.stage_e_logical_event_replay.v1",
        "status": "completed",
        "scope": {
            "page_count": len(page_rows),
            "raw_gt_count": sum(int(page["raw_gt_count"]) for page in page_rows),
            "p1_pair_count": grouped_pair_total,
            "physical_event_count_under_p1_hypothesis": sum(
                int(page["physical_event_count_under_p1_hypothesis"]) for page in page_rows
            ),
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_reexecuted": False,
            "filter_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
            "authoritative_gt_modified": False,
        },
        "premise": {
            "formal_gt_policy": "one bbox per physical vertical line",
            "p1_treatment": (
                "P1 ordinary same-ink high-overlap pairs are collapsed only for "
                "this review replay; this is not an automatic authoritative GT edit."
            ),
            "p3_treatment": (
                "double_barline/end_barline/repeat physical lines remain independent events."
            ),
            "matching_rule": {
                "rule": "center_anchor",
                "vov_threshold": 0.5,
                "xdist_threshold_px": 12.0,
            },
            "why_maximum_cardinality": (
                "The legacy evaluator is greedy. Maximum matching is reported "
                "separately to distinguish missing physical detection capacity "
                "from assignment order."
            ),
        },
        "input_validation": {
            "legacy_control_accepted_reproduction": control_repro,
            "legacy_candidate_accepted_reproduction": candidate_repro,
            "p1_pair_count_matches_audit": grouped_pair_total == p1_total,
        },
        "accepted_summary": accepted_summary,
        "accepted_interpretation": {
            "physical_event_delta_candidate_minus_control": metrics_delta(
                physical_candidate,
                physical_control,
            ),
            "singleton_independent_delta_candidate_minus_control": metrics_delta(
                singleton_candidate,
                singleton_control,
            ),
            "changed_physical_page_count": len(changed_physical_pages),
            "changed_physical_pages": changed_physical_pages,
            "decision_guardrail": (
                "Do not remove C solely from legacy greedy TP/FN. If B has equal "
                "physical-event maximum capacity and equal singleton-event coverage, "
                "the apparent regression is an evaluation/GT identity artifact. If a "
                "real physical-event deficit remains, trace that event before selecting "
                "the canonical one-inference x4 producer."
            ),
        },
        "aggregate_by_stage": aggregate,
        "pages": page_rows,
    }
    write_json(output, result)

    if not control_repro["exact"] or not candidate_repro["exact"]:
        print(f"Wrote {output}")
        print("Legacy metric reproduction failed; inspect input_validation.")
        return 3

    print(f"Wrote {output}")
    print(
        json.dumps(
            {
                "raw_gt_count": result["scope"]["raw_gt_count"],
                "p1_pair_count": grouped_pair_total,
                "physical_event_count": result["scope"]["physical_event_count_under_p1_hypothesis"],
                "control_physical": physical_control,
                "candidate_physical": physical_candidate,
                "control_singleton": singleton_control,
                "candidate_singleton": singleton_candidate,
                "changed_physical_page_count": len(changed_physical_pages),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
