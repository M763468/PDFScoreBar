#!/usr/bin/env python3
"""Evaluate a retained-only composed MMR OCR retry candidate for Issue #277.

This experiment deliberately separates evidence that is already available from the
normal high-CNN primary OCR path from genuinely additional OCR work:

1. zero-extra-call primary candidate anchoring/consensus over the existing
   standard/no_dilate/heavy_dilate masked views;
2. if unresolved, one candidate-native normalized *unmasked heavy_dilate* OCR call
   per staff;
3. if still unresolved, one candidate-native measure-x +1% *masked no_dilate* OCR
   call per staff.

The current report is a projection from retained OCR provenance and the normalized
ROI probe.  It does not rerun OCR and is not production decision logic.  Frozen-A
geometry, page ids, score ids, and absolute coordinates are not used as decision
signals.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

PRIMARY_VARIANTS = ("standard", "no_dilate", "heavy_dilate")
PREPROCESS_BORDER = 20.0
NORMALIZED_POLICY = "full_unmasked"
NORMALIZED_MODE = "heavy_dilate"
SHIFT_FRACTION = 0.01
SHIFT_VARIANT = "no_dilate"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def candidate_absolute_center(
    candidate: Mapping[str, Any], staff_run: Mapping[str, Any]
) -> tuple[float, float]:
    crop = staff_run["crop_bounds"]
    bbox = candidate["bbox"]
    return (
        float(crop[0]) + (float(bbox[0]) + float(bbox[2])) / 2.0 - PREPROCESS_BORDER,
        float(crop[1]) + (float(bbox[1]) + float(bbox[3])) / 2.0 - PREPROCESS_BORDER,
    )


def candidate_is_measure_staff_anchored(
    candidate: Mapping[str, Any],
    staff_run: Mapping[str, Any],
    measure_bbox: Sequence[float],
    staff_bbox: Sequence[float],
) -> bool:
    center_x, center_y = candidate_absolute_center(candidate, staff_run)
    mx1, _my1, mx2, _my2 = (float(value) for value in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (float(value) for value in staff_bbox)
    staff_height = max(1.0, sy2 - sy1)
    return bool(mx1 <= center_x <= mx2 and sy1 - staff_height <= center_y <= sy2)


def primary_anchored_consensus(
    sweep_point: Mapping[str, Any], staff_bboxes: Sequence[Sequence[float]]
) -> dict[str, Any]:
    """Use only masked primary OCR views that production already executes."""

    votes: Counter[int] = Counter()
    best_scores: dict[int, float] = {}
    evidence_units: list[dict[str, Any]] = []
    measure_bbox = sweep_point["measure_bbox"]

    for variant in PRIMARY_VARIANTS:
        variant_run = sweep_point.get("variant_runs", {}).get(variant)
        if not isinstance(variant_run, Mapping):
            continue
        for staff_index, staff_run in enumerate(variant_run.get("staff_runs", [])):
            if staff_index >= len(staff_bboxes):
                continue
            anchored = [
                candidate
                for candidate in staff_run.get("ranked_numeric_candidates", [])
                if candidate_is_measure_staff_anchored(
                    candidate,
                    staff_run,
                    measure_bbox,
                    staff_bboxes[staff_index],
                )
            ]
            if not anchored:
                continue
            candidate = max(anchored, key=lambda item: float(item["score"]))
            value = int(candidate["value"])
            score = float(candidate["score"])
            votes[value] += 1
            best_scores[value] = max(best_scores.get(value, float("-inf")), score)
            evidence_units.append(
                {
                    "variant": variant,
                    "staff_index": staff_index,
                    "value": value,
                    "score": score,
                    "text": str(candidate.get("text", "")),
                }
            )

    if not votes:
        return {
            "selected_num": None,
            "support": 0,
            "vote_counts": {},
            "reason": "no_anchored_primary_numeric",
            "evidence_units": evidence_units,
        }

    max_support = max(votes.values())
    leaders = [value for value, count in votes.items() if count == max_support]
    if max_support < 2:
        selected = None
        reason = "primary_support_below_2"
    elif len(leaders) != 1:
        selected = None
        reason = "primary_consensus_tie"
    else:
        selected = leaders[0]
        reason = "primary_anchored_consensus"

    return {
        "selected_num": selected,
        "support": int(max_support),
        "vote_counts": {str(value): int(count) for value, count in sorted(votes.items())},
        "reason": reason,
        "evidence_units": evidence_units,
    }


def _unique_aggregate_num(aggregate: Mapping[str, Any]) -> int | None:
    """Reject multi-staff vote ties instead of score-breaking them."""

    found = aggregate.get("found_num")
    if found is None or int(found) < 2:
        return None
    raw_counts = aggregate.get("vote_counts")
    if not isinstance(raw_counts, Mapping) or not raw_counts:
        # Single-staff provenance may omit vote_counts in older retained reports.
        return int(found)
    counts = {int(key): int(value) for key, value in raw_counts.items()}
    max_support = max(counts.values())
    leaders = [value for value, count in counts.items() if count == max_support]
    if len(leaders) != 1:
        return None
    if leaders[0] != int(found):
        raise RuntimeError("Aggregate found_num disagrees with unique vote leader")
    return int(found)


def _zero_point(record: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        point
        for point in record.get("sweep", [])
        if abs(float(point.get("fraction", 999.0))) < 1e-12
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one native zero point for {record.get('page_id')}")
    return matches[0]


def _shift_point(record: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        point
        for point in record.get("sweep", [])
        if abs(float(point.get("fraction", 999.0)) - SHIFT_FRACTION) < 1e-12
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one +{SHIFT_FRACTION:.3f} sweep point for {record.get('page_id')}"
        )
    return matches[0]


def evaluate_record(
    provenance_record: Mapping[str, Any], normalized_record: Mapping[str, Any]
) -> dict[str, Any]:
    expected_num = int(provenance_record["expected_skip"]) + 1
    zero = _zero_point(provenance_record)
    staff_bboxes = provenance_record["native_reference"]["primary_staff_bboxes"]
    staff_count = len(staff_bboxes)

    primary = primary_anchored_consensus(zero, staff_bboxes)
    selected = primary["selected_num"]
    stage = "primary_anchored_consensus" if selected is not None else None
    additional_calls = 0

    normalized_detail: dict[str, Any] | None = None
    if selected is None:
        policy = normalized_record["policy_results"][NORMALIZED_POLICY]
        mode = policy["modes"][NORMALIZED_MODE]
        normalized_num = _unique_aggregate_num(mode)
        additional_calls += staff_count
        normalized_detail = {
            "policy": NORMALIZED_POLICY,
            "mode": NORMALIZED_MODE,
            "selected_num": normalized_num,
            "aggregate_found_num": mode.get("found_num"),
            "aggregate_support": mode.get("support"),
            "aggregate_vote_counts": mode.get("vote_counts", {}),
            "rapidocr_calls_per_staff": 1,
        }
        if normalized_num is not None:
            selected = normalized_num
            stage = "normalized_unmasked_heavy_dilate"

    shift_detail: dict[str, Any] | None = None
    if selected is None:
        shifted = _shift_point(provenance_record)
        aggregate = shifted["variant_runs"][SHIFT_VARIANT]["aggregate"]
        shifted_num = _unique_aggregate_num(aggregate)
        additional_calls += staff_count
        shift_detail = {
            "fraction": SHIFT_FRACTION,
            "variant": SHIFT_VARIANT,
            "measure_bbox": list(shifted["measure_bbox"]),
            "selected_num": shifted_num,
            "aggregate_found_num": aggregate.get("found_num"),
            "aggregate_score": float(aggregate.get("score", 0.0)),
            "rapidocr_calls_per_staff": 1,
        }
        if shifted_num is not None:
            selected = shifted_num
            stage = "scale_relative_x1_retry"

    if selected is None:
        outcome = "abstain"
        stage = "abstain"
    elif int(selected) == expected_num:
        outcome = "correct"
    else:
        outcome = "incorrect"

    return {
        "page_id": provenance_record["page_id"],
        "score": provenance_record["score"],
        "page_name": provenance_record["page_name"],
        "key": provenance_record["key"],
        "expected_num": expected_num,
        "source_native_num": zero.get("source_found_num"),
        "selected_num": selected,
        "stage": stage,
        "outcome": outcome,
        "staff_count": staff_count,
        "additional_rapidocr_calls": additional_calls,
        "primary": primary,
        "normalized_retry": normalized_detail,
        "scale_relative_x1_retry": shift_detail,
    }


def run(provenance_path: Path, normalized_path: Path, output_path: Path) -> dict[str, Any]:
    provenance = _load_json(provenance_path)
    normalized = _load_json(normalized_path)
    if not isinstance(provenance, Mapping) or provenance.get("status") != "completed":
        raise ValueError("OCR provenance report is not completed")
    if not isinstance(normalized, Mapping) or normalized.get("status") != "completed":
        raise ValueError("Normalized ROI report is not completed")
    if provenance.get("source_variant_match_failures"):
        raise RuntimeError("OCR provenance report has source replay mismatches")

    normalized_by_page = {
        str(record["page_id"]): record
        for record in normalized.get("records", [])
        if isinstance(record, Mapping)
    }
    records: list[dict[str, Any]] = []
    for provenance_record in provenance.get("records", []):
        if not isinstance(provenance_record, Mapping):
            continue
        page_id = str(provenance_record["page_id"])
        normalized_record = normalized_by_page.get(page_id)
        if normalized_record is None:
            raise RuntimeError(f"Normalized ROI report lacks {page_id}")
        records.append(evaluate_record(provenance_record, normalized_record))

    stage_counts = Counter(record["stage"] for record in records)
    correct = sum(record["outcome"] == "correct" for record in records)
    incorrect = [record for record in records if record["outcome"] == "incorrect"]
    abstain = [record for record in records if record["outcome"] == "abstain"]
    source_correct = sum(
        record["source_native_num"] == record["expected_num"] for record in records
    )

    payload = {
        "schema_version": "issue277.composed_mmr_retry_candidate.v1",
        "status": "completed",
        "execution_contract": {
            "production_code_modified": False,
            "ocr_reexecuted": False,
            "cnn_reexecuted": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "numbering_reexecuted": False,
            "full68_mmr_reexecuted": False,
            "frozen_A_geometry_used": False,
            "projection": "retained OCR provenance plus normalized ROI probe",
        },
        "candidate_contract": {
            "stage_1": "existing masked primary standard/no_dilate/heavy_dilate; accept only unique anchored support>=2",
            "stage_2": "if unresolved, one candidate-native full-span unmasked heavy_dilate RapidOCR call per staff",
            "stage_3": "if still unresolved, one candidate-native +1% measure-x1 masked no_dilate RapidOCR call per staff",
            "one_bar": "values below 2 are never emitted as overrides; dedicated one-bar/fallback semantics still require broader risk-slice validation",
            "rapidocr_confidence": "diagnostic only; not used in decisions",
        },
        "summary": {
            "record_count": len(records),
            "source_native_correct": source_correct,
            "candidate_correct": correct,
            "candidate_incorrect_numeric": len(incorrect),
            "candidate_abstain": len(abstain),
            "additional_rapidocr_calls_total": sum(
                int(record["additional_rapidocr_calls"]) for record in records
            ),
            "additional_rapidocr_calls_max_per_record": max(
                (int(record["additional_rapidocr_calls"]) for record in records), default=0
            ),
            "stage_counts": dict(sorted(stage_counts.items())),
        },
        "incorrect_numeric_predictions": incorrect,
        "unresolved": abstain,
        "records": records,
        "gates": {
            "all_controls_correct": bool(records) and correct == len(records),
            "no_incorrect_numeric": not incorrect,
            "no_abstain": not abstain,
        },
    }
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--normalized-roi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.provenance, args.normalized_roi, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                **payload["summary"],
                "gates": payload["gates"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
