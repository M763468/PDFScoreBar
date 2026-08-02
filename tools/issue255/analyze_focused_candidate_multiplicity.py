#!/usr/bin/env python3
"""Analyze focused detector multiplicity and candidate deduplication offline.

This tool never runs HOMR, SR, OMR-DLN, probe detection, or CNN inference.  It
reuses retained focused artifacts to distinguish three different outcomes:

* newly recovered accepted barlines;
* duplicate representations of one accepted physical barline;
* additions with no accepted match.

It also sweeps a rescue-aware geometric deduplication policy.  Current boxes
that reproduce the pre-repair baseline are protected.  Only current additions
are considered suppressible, which models the intended production rule:
preserve the established detector route and normalize low-paper rescue output.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common import barline_iou
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = ROOT / "tools/issue255/gate05_targets.json"
DEFAULT_BASELINE = (
    ROOT
    / "logs/issue255_focused_fresh/"
    "issue255_focused_fresh_batch_issue255_gate_05.json"
)

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Policy:
    x_tolerance: float
    min_vertical_overlap_ratio: float
    min_height_ratio: float

    def as_dict(self) -> dict[str, float]:
        return {
            "x_tolerance": self.x_tolerance,
            "min_vertical_overlap_ratio": self.min_vertical_overlap_ratio,
            "min_height_ratio": self.min_height_ratio,
        }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return ROOT / path.relative_to("/workspace")
    return path if path.is_absolute() else ROOT / path


def _artifact_path(contract: Mapping[str, Any], name: str) -> Path:
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Focused contract lacks artifacts")
    record = artifacts.get(name)
    if not isinstance(record, Mapping) or record.get("exists") is not True:
        raise ValueError(f"Focused contract lacks completed artifact: {name}")
    path = _resolve_path(str(record["path"]))
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _records(path: Path) -> list[Mapping[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected list: {path}")
    return [item for item in payload if isinstance(item, Mapping)]


def _run_by_label(batch: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    runs = batch.get("runs")
    if not isinstance(runs, list):
        raise ValueError("Focused batch lacks runs")
    result = {}
    for run in runs:
        if isinstance(run, Mapping) and run.get("label"):
            result[str(run["label"])] = run
    return result


def _box(value: Sequence[int | float]) -> Box:
    return normalize_box(value)


def _center_x(box: Box) -> float:
    return (box[0] + box[2]) / 2.0


def _height(box: Box) -> float:
    return float(abs(box[3] - box[1]))


def _vertical_overlap_ratio(first: Box, second: Box) -> float:
    first_y1, first_y2 = sorted((first[1], first[3]))
    second_y1, second_y2 = sorted((second[1], second[3]))
    intersection = max(0, min(first_y2, second_y2) - max(first_y1, second_y1))
    return float(intersection) / float(max(1.0, min(_height(first), _height(second))))


def _height_ratio(first: Box, second: Box) -> float:
    low = min(_height(first), _height(second))
    high = max(_height(first), _height(second))
    return low / max(1.0, high)


def _best_reference(
    prediction: Box,
    references: Sequence[Box],
    *,
    accepted_iou: float,
) -> tuple[int | None, float]:
    if not references:
        return None, 0.0
    ranked = sorted(
        (
            (float(barline_iou(prediction, reference)), index)
            for index, reference in enumerate(references)
        ),
        reverse=True,
    )
    iou, index = ranked[0]
    return (index, iou) if iou > accepted_iou else (None, iou)


def _stable_match_details(
    references: Sequence[Sequence[int | float]],
    predictions: Sequence[Sequence[int | float]],
    *,
    accepted_iou: float = 0.5,
) -> dict[str, Any]:
    """Return deterministic exact-first maximum-cardinality matching.

    The earlier focused evaluator greedily consumed references in prediction
    order.  An approximate new box could therefore consume a reference before
    an exact retained baseline box was visited.  Exact matches are locked
    first; the remaining bipartite graph is matched with augmenting paths.
    """

    refs = [_box(box) for box in references]
    preds = [_box(box) for box in predictions]
    unmatched_refs = set(range(len(refs)))
    unmatched_preds = set(range(len(preds)))
    matches: list[dict[str, Any]] = []

    refs_by_box: dict[Box, list[int]] = defaultdict(list)
    for ref_index, reference in enumerate(refs):
        refs_by_box[reference].append(ref_index)

    for pred_index, prediction in enumerate(preds):
        candidates = refs_by_box.get(prediction)
        if not candidates:
            continue
        ref_index = next(
            (index for index in candidates if index in unmatched_refs),
            None,
        )
        if ref_index is None:
            continue
        unmatched_refs.remove(ref_index)
        unmatched_preds.remove(pred_index)
        matches.append(
            {
                "prediction_index": pred_index,
                "reference_index": ref_index,
                "prediction": list(prediction),
                "reference": list(refs[ref_index]),
                "iou": 1.0,
                "exact": True,
            }
        )

    adjacency: dict[int, list[tuple[int, float]]] = {}
    for pred_index in sorted(unmatched_preds):
        prediction = preds[pred_index]
        edges = []
        for ref_index in sorted(unmatched_refs):
            iou = float(barline_iou(prediction, refs[ref_index]))
            if iou > accepted_iou:
                edges.append((ref_index, iou))
        edges.sort(key=lambda item: (-item[1], item[0]))
        adjacency[pred_index] = edges

    ref_to_pred: dict[int, int] = {}

    def augment(pred_index: int, seen_refs: set[int]) -> bool:
        for ref_index, _ in adjacency.get(pred_index, []):
            if ref_index in seen_refs:
                continue
            seen_refs.add(ref_index)
            previous = ref_to_pred.get(ref_index)
            if previous is None or augment(previous, seen_refs):
                ref_to_pred[ref_index] = pred_index
                return True
        return False

    prediction_order = sorted(
        unmatched_preds,
        key=lambda index: (
            -max((iou for _, iou in adjacency.get(index, [])), default=0.0),
            index,
        ),
    )
    for pred_index in prediction_order:
        augment(pred_index, set())

    matched_pred_indices = {match["prediction_index"] for match in matches}
    matched_ref_indices = {match["reference_index"] for match in matches}
    for ref_index, pred_index in sorted(ref_to_pred.items()):
        matches.append(
            {
                "prediction_index": pred_index,
                "reference_index": ref_index,
                "prediction": list(preds[pred_index]),
                "reference": list(refs[ref_index]),
                "iou": float(barline_iou(preds[pred_index], refs[ref_index])),
                "exact": False,
            }
        )
        matched_pred_indices.add(pred_index)
        matched_ref_indices.add(ref_index)

    return {
        "tp": len(matches),
        "fp": len(preds) - len(matches),
        "fn": len(refs) - len(matches),
        "matches": sorted(matches, key=lambda item: item["prediction_index"]),
        "unmatched_prediction_indices": sorted(
            set(range(len(preds))) - matched_pred_indices
        ),
        "unmatched_reference_indices": sorted(
            set(range(len(refs))) - matched_ref_indices
        ),
        "false_positive_boxes": [
            list(preds[index])
            for index in sorted(set(range(len(preds))) - matched_pred_indices)
        ],
        "false_negative_boxes": [
            list(refs[index])
            for index in sorted(set(range(len(refs))) - matched_ref_indices)
        ],
    }


def _score_map(records: Sequence[Mapping[str, Any]]) -> dict[Box, float]:
    result: dict[Box, float] = {}
    for item in records:
        bbox = item.get("bbox")
        score = item.get("score")
        if not isinstance(bbox, Sequence) or not isinstance(score, (int, float)):
            continue
        box = _box(bbox)
        result[box] = max(float(score), result.get(box, float("-inf")))
    return result


def _duplicate_relation(first: Box, second: Box, policy: Policy) -> bool:
    return (
        abs(_center_x(first) - _center_x(second)) <= policy.x_tolerance
        and _vertical_overlap_ratio(first, second)
        >= policy.min_vertical_overlap_ratio
        and _height_ratio(first, second) >= policy.min_height_ratio
    )


def _metrics(
    accepted: Sequence[Box],
    predictions: Sequence[Box],
) -> dict[str, int]:
    details = _stable_match_details(accepted, predictions)
    return {key: int(details[key]) for key in ("tp", "fp", "fn")}


def _target_recovery(
    targets: Sequence[Box],
    predictions: Sequence[Box],
) -> list[bool]:
    return [
        _best_reference(target, predictions, accepted_iou=0.5)[0] is not None
        for target in targets
    ]


def _multiplicity(
    accepted: Sequence[Box],
    predictions: Sequence[Box],
) -> dict[str, Any]:
    groups: dict[int, list[int]] = defaultdict(list)
    unrelated = []
    best_rows = []
    for pred_index, prediction in enumerate(predictions):
        ref_index, iou = _best_reference(
            prediction,
            accepted,
            accepted_iou=0.5,
        )
        best_rows.append(
            {
                "prediction_index": pred_index,
                "bbox": list(prediction),
                "accepted_reference_index": ref_index,
                "best_iou": iou,
            }
        )
        if ref_index is None:
            unrelated.append(pred_index)
        else:
            groups[ref_index].append(pred_index)

    duplicate_groups = [
        {
            "accepted_reference_index": ref_index,
            "accepted_bbox": list(accepted[ref_index]),
            "prediction_indices": indices,
            "prediction_boxes": [list(predictions[index]) for index in indices],
            "excess_count": len(indices) - 1,
        }
        for ref_index, indices in sorted(groups.items())
        if len(indices) > 1
    ]
    return {
        "assigned_reference_count": len(groups),
        "unrelated_prediction_indices": unrelated,
        "unrelated_boxes": [list(predictions[index]) for index in unrelated],
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_excess_count": sum(
            group["excess_count"] for group in duplicate_groups
        ),
        "duplicate_groups": duplicate_groups,
        "best_reference_by_prediction": best_rows,
    }


def _simulate_policy(
    *,
    accepted: Sequence[Box],
    baseline: Sequence[Box],
    current: Sequence[Box],
    scores: Mapping[Box, float],
    targets: Sequence[Box],
    policy: Policy,
    include_details: bool = False,
) -> dict[str, Any]:
    baseline_to_current = _stable_match_details(baseline, current)
    protected = {
        int(match["prediction_index"])
        for match in baseline_to_current["matches"]
    }
    additions = [
        index for index in range(len(current)) if index not in protected
    ]
    additions.sort(
        key=lambda index: (
            -scores.get(current[index], float("-inf")),
            -_height(current[index]),
            current[index],
        )
    )

    kept = sorted(protected)
    suppressed = []
    accepted_collisions = []
    for candidate_index in additions:
        candidate = current[candidate_index]
        duplicate_of = next(
            (
                kept_index
                for kept_index in kept
                if _duplicate_relation(candidate, current[kept_index], policy)
            ),
            None,
        )
        if duplicate_of is None:
            kept.append(candidate_index)
            continue

        candidate_ref, _ = _best_reference(
            candidate,
            accepted,
            accepted_iou=0.5,
        )
        kept_ref, _ = _best_reference(
            current[duplicate_of],
            accepted,
            accepted_iou=0.5,
        )
        collision = (
            candidate_ref is not None
            and kept_ref is not None
            and candidate_ref != kept_ref
        )
        if collision:
            accepted_collisions.append(
                {
                    "candidate_index": candidate_index,
                    "candidate_bbox": list(candidate),
                    "kept_index": duplicate_of,
                    "kept_bbox": list(current[duplicate_of]),
                    "candidate_reference_index": candidate_ref,
                    "kept_reference_index": kept_ref,
                }
            )
        suppressed.append(
            {
                "candidate_index": candidate_index,
                "candidate_bbox": list(candidate),
                "duplicate_of_index": duplicate_of,
                "duplicate_of_bbox": list(current[duplicate_of]),
                "accepted_collision": collision,
            }
        )

    retained = [current[index] for index in sorted(kept)]
    target_recovered = _target_recovery(targets, retained)
    result = {
        "policy": policy.as_dict(),
        "retained_count": len(retained),
        "suppressed_count": len(suppressed),
        "metrics": _metrics(accepted, retained),
        "all_targets_recovered": all(target_recovered),
        "target_recovered": target_recovered,
        "accepted_collision_count": len(accepted_collisions),
    }
    if include_details:
        result["accepted_collisions"] = accepted_collisions
        result["suppressed"] = suppressed
    return result


def _load_accepted_pair_features(
    accepted_root: Path | None,
) -> dict[str, Any]:
    if accepted_root is None:
        return {"available": False, "page_count": 0, "pairs": []}
    paths = sorted(accepted_root.rglob("pipeline2_no_peak_filtered_cnn.json"))
    pairs = []
    for path in paths:
        boxes = [_box(box) for box in load_json_boxes(path)]
        for first_index, first in enumerate(boxes):
            for second_index in range(first_index + 1, len(boxes)):
                second = boxes[second_index]
                x_distance = abs(_center_x(first) - _center_x(second))
                vertical_overlap = _vertical_overlap_ratio(first, second)
                height_ratio = _height_ratio(first, second)
                if x_distance > 12 or vertical_overlap < 0.8 or height_ratio < 0.7:
                    continue
                pairs.append(
                    {
                        "path": str(path),
                        "first_index": first_index,
                        "first_bbox": list(first),
                        "second_index": second_index,
                        "second_bbox": list(second),
                        "x_distance": x_distance,
                        "vertical_overlap_ratio": vertical_overlap,
                        "height_ratio": height_ratio,
                    }
                )
    return {
        "available": True,
        "page_count": len(paths),
        "pairs": pairs,
    }


def _accepted_root_collisions(
    accepted_pair_features: Mapping[str, Any],
    policy: Policy,
) -> dict[str, Any]:
    if accepted_pair_features.get("available") is not True:
        return {
            "available": False,
            "page_count": 0,
            "collision_count": None,
            "examples": [],
        }
    pairs = accepted_pair_features.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("Accepted pair feature inventory is invalid")
    collisions = [
        pair
        for pair in pairs
        if float(pair["x_distance"]) <= policy.x_tolerance
        and float(pair["vertical_overlap_ratio"])
        >= policy.min_vertical_overlap_ratio
        and float(pair["height_ratio"]) >= policy.min_height_ratio
    ]
    return {
        "available": True,
        "page_count": int(accepted_pair_features.get("page_count", 0)),
        "collision_count": len(collisions),
        "examples": collisions[:50],
        "examples_truncated": len(collisions) > 50,
    }


def build_report(
    *,
    current_batch: Path,
    baseline_batch: Path,
    targets_path: Path,
    accepted_root: Path | None,
) -> dict[str, Any]:
    current_payload = _load_json(current_batch.resolve())
    baseline_payload = _load_json(baseline_batch.resolve())
    target_payload = _load_json(targets_path.resolve())
    if not isinstance(current_payload, Mapping) or current_payload.get("status") != "completed":
        raise ValueError("Current focused batch must be completed")
    if not isinstance(baseline_payload, Mapping) or baseline_payload.get("status") != "completed":
        raise ValueError("Baseline focused batch must be completed")
    if not isinstance(target_payload, Mapping) or not isinstance(
        target_payload.get("pages"), Mapping
    ):
        raise ValueError("Focused target manifest is invalid")

    current_runs = _run_by_label(current_payload)
    baseline_runs = _run_by_label(baseline_payload)
    pages: dict[str, dict[str, Any]] = {}
    page_inputs: dict[str, dict[str, Any]] = {}
    baseline_metrics_by_page: dict[str, dict[str, int]] = {}

    for label, page_spec in target_payload["pages"].items():
        if not isinstance(page_spec, Mapping):
            raise ValueError(f"Invalid page specification: {label}")
        current_contract = current_runs[str(label)].get("contract")
        baseline_contract = baseline_runs[str(label)].get("contract")
        if not isinstance(current_contract, Mapping) or not isinstance(
            baseline_contract, Mapping
        ):
            raise ValueError(f"Incomplete focused contracts for {label}")

        accepted_path = _resolve_path(str(page_spec["accepted_barlines"]))
        accepted = [_box(box) for box in load_json_boxes(accepted_path)]
        baseline = [
            _box(box)
            for box in load_json_boxes(
                _artifact_path(baseline_contract, "final_barlines")
            )
        ]
        current = [
            _box(box)
            for box in load_json_boxes(
                _artifact_path(current_contract, "final_barlines")
            )
        ]
        scores = _score_map(
            _records(_artifact_path(current_contract, "cnn_scored"))
        )
        target_rows = page_spec.get("targets")
        if not isinstance(target_rows, list):
            raise ValueError(f"Target list missing for {label}")
        targets = [
            _box(item["accepted_bbox"])
            for item in target_rows
            if isinstance(item, Mapping)
            and isinstance(item.get("accepted_bbox"), Sequence)
        ]

        baseline_metrics = _metrics(accepted, baseline)
        current_metrics = _metrics(accepted, current)
        baseline_to_current = _stable_match_details(baseline, current)
        multiplicity = _multiplicity(accepted, current)
        pages[str(label)] = {
            "score": page_spec.get("score"),
            "page": page_spec.get("page"),
            "accepted_reference": str(accepted_path),
            "accepted_reference_runtime_input": False,
            "baseline_count": len(baseline),
            "current_count": len(current),
            "count_delta": len(current) - len(baseline),
            "baseline_metrics": baseline_metrics,
            "current_metrics": current_metrics,
            "metric_delta": {
                key: current_metrics[key] - baseline_metrics[key]
                for key in ("tp", "fp", "fn")
            },
            "baseline_preservation": {
                "matched_count": baseline_to_current["tp"],
                "missing_baseline_count": baseline_to_current["fn"],
                "new_current_count": baseline_to_current["fp"],
                "missing_baseline_boxes": baseline_to_current[
                    "false_negative_boxes"
                ],
                "new_current_boxes": baseline_to_current[
                    "false_positive_boxes"
                ],
            },
            "multiplicity": multiplicity,
            "target_recovered": _target_recovery(targets, current),
        }
        page_inputs[str(label)] = {
            "accepted": accepted,
            "baseline": baseline,
            "current": current,
            "scores": scores,
            "targets": targets,
        }
        baseline_metrics_by_page[str(label)] = baseline_metrics

    policies = [
        Policy(
            x_tolerance=float(x_tolerance),
            min_vertical_overlap_ratio=vertical_overlap,
            min_height_ratio=height_ratio,
        )
        for x_tolerance in (1, 2, 3, 4, 5, 6, 8, 10, 12)
        for vertical_overlap in (0.95, 0.9, 0.8)
        for height_ratio in (0.9, 0.8, 0.7)
    ]
    accepted_pair_features = _load_accepted_pair_features(accepted_root)
    policy_rows = []
    for policy in policies:
        page_results = {
            label: _simulate_policy(policy=policy, **inputs)
            for label, inputs in page_inputs.items()
        }
        accepted_safety = _accepted_root_collisions(
            accepted_pair_features,
            policy,
        )
        focused_pass = all(
            result["all_targets_recovered"]
            and result["accepted_collision_count"] == 0
            and result["metrics"]["fp"]
            <= baseline_metrics_by_page[label]["fp"]
            and result["metrics"]["fn"]
            <= baseline_metrics_by_page[label]["fn"]
            and result["metrics"]["tp"]
            >= baseline_metrics_by_page[label]["tp"]
            for label, result in page_results.items()
        )
        full_reference_safe = (
            accepted_safety["available"]
            and accepted_safety["collision_count"] == 0
        )
        fp_excess = sum(
            max(
                0,
                result["metrics"]["fp"]
                - baseline_metrics_by_page[label]["fp"],
            )
            for label, result in page_results.items()
        )
        fn_excess = sum(
            max(
                0,
                result["metrics"]["fn"]
                - baseline_metrics_by_page[label]["fn"],
            )
            for label, result in page_results.items()
        )
        missing_targets = sum(
            result["target_recovered"].count(False)
            for result in page_results.values()
        )
        accepted_collisions = sum(
            result["accepted_collision_count"]
            for result in page_results.values()
        )
        full_collisions = (
            int(accepted_safety["collision_count"])
            if accepted_safety["collision_count"] is not None
            else 1
        )
        policy_rows.append(
            {
                "policy": policy.as_dict(),
                "focused_pass": focused_pass,
                "full_reference_safe": full_reference_safe,
                "passes_all_checks": focused_pass and full_reference_safe,
                "failure_score": (
                    missing_targets * 1000
                    + fp_excess * 100
                    + fn_excess * 100
                    + accepted_collisions * 10
                    + full_collisions
                ),
                "pages": page_results,
                "accepted_root_safety": accepted_safety,
            }
        )

    passing = [row for row in policy_rows if row["passes_all_checks"]]
    passing.sort(
        key=lambda row: (
            row["policy"]["x_tolerance"],
            -row["policy"]["min_vertical_overlap_ratio"],
            -row["policy"]["min_height_ratio"],
        )
    )

    nearest = sorted(
        policy_rows,
        key=lambda row: (
            row["failure_score"],
            row["policy"]["x_tolerance"],
            -row["policy"]["min_vertical_overlap_ratio"],
            -row["policy"]["min_height_ratio"],
        ),
    )[:10]
    detailed_policies = passing[:3] if passing else nearest[:3]
    detailed = []
    for row in detailed_policies:
        policy = Policy(**row["policy"])
        detailed.append(
            {
                **row,
                "pages": {
                    label: _simulate_policy(
                        policy=policy,
                        include_details=True,
                        **inputs,
                    )
                    for label, inputs in page_inputs.items()
                },
            }
        )

    return {
        "schema_version": "issue255.focused_candidate_multiplicity.v1",
        "status": "completed",
        "current_commit": current_payload.get("expected_commit"),
        "baseline_commit": baseline_payload.get("expected_commit"),
        "accepted_reference_runtime_input": False,
        "analysis_only": True,
        "pages": pages,
        "accepted_root_safety_inventory": {
            "available": accepted_pair_features["available"],
            "page_count": accepted_pair_features["page_count"],
            "near_pair_count": len(accepted_pair_features["pairs"]),
        },
        "policy_sweep": {
            "policy_count": len(policy_rows),
            "passing_policy_count": len(passing),
            "recommended_policy": passing[0]["policy"] if passing else None,
            "passing_policies": passing,
            "nearest_policies": nearest,
            "detailed_policies": detailed,
            "all_policies": policy_rows,
        },
        "next_gpu_run_authorized": bool(passing)
        and accepted_pair_features["available"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-batch", type=Path, required=True)
    parser.add_argument("--baseline-batch", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument(
        "--accepted-root",
        type=Path,
        help=(
            "Optional full accepted probe root. When supplied, every policy is "
            "checked for collisions between distinct accepted boxes."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        report = build_report(
            current_batch=args.current_batch,
            baseline_batch=args.baseline_batch,
            targets_path=args.targets,
            accepted_root=args.accepted_root.resolve()
            if args.accepted_root
            else None,
        )
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": report["status"],
                "passing_policy_count": report["policy_sweep"][
                    "passing_policy_count"
                ],
                "recommended_policy": report["policy_sweep"][
                    "recommended_policy"
                ],
                "next_gpu_run_authorized": report[
                    "next_gpu_run_authorized"
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
