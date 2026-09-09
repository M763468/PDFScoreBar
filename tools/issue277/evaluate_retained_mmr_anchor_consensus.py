#!/usr/bin/env python3
"""Evaluate semantically anchored existing MMR OCR evidence for Issue #277.

This retained-only experiment consumes the raw OCR provenance report produced by
``diagnose_retained_mmr_ocr_provenance.py``.  It does not rerun OCR or any upstream
model.  The candidate rule intentionally uses only candidate-native measure/staff
geometry; frozen-A geometry is not an input.

The experiment asks two questions before trying another OCR geometry:

1. Can numeric candidates outside the physical measure/staff neighborhood be
   rejected as unrelated annotations?
2. Can agreement already present across existing preprocessing variants/staves
   recover a stable value without additional OCR calls?

This is investigation tooling, not production decision logic.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

PRIMARY_VARIANTS = ("standard", "no_dilate", "heavy_dilate")
FALLBACK_VARIANTS = (
    "unmasked_fallback_standard",
    "left_wide_unmasked_fallback_standard",
)
PREPROCESS_BORDER = 20.0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def candidate_absolute_center(
    candidate: Mapping[str, Any], staff_run: Mapping[str, Any]
) -> tuple[float, float]:
    """Map a provenance candidate center from preprocessed crop to page pixels."""

    crop = staff_run["crop_bounds"]
    bbox = candidate["bbox"]
    center_x = float(crop[0]) + (float(bbox[0]) + float(bbox[2])) / 2.0 - PREPROCESS_BORDER
    center_y = float(crop[1]) + (float(bbox[1]) + float(bbox[3])) / 2.0 - PREPROCESS_BORDER
    return center_x, center_y


def candidate_is_measure_staff_anchored(
    candidate: Mapping[str, Any],
    staff_run: Mapping[str, Any],
    measure_bbox: Sequence[float],
    staff_bbox: Sequence[float],
) -> bool:
    """Apply a deliberately broad, scale-relative physical anchor.

    Horizontally, the OCR center must lie inside the candidate-native measure span.
    Vertically, it may be up to one staff height above the staff, but not below the
    staff bottom.  The one-staff-height upper allowance is intentionally broad so
    printed MMR counts above the staff remain eligible; the experiment is testing
    physical anchoring plus consensus, not a tightly tuned OCR ROI.
    """

    center_x, center_y = candidate_absolute_center(candidate, staff_run)
    mx1, _my1, mx2, _my2 = (float(value) for value in measure_bbox)
    _sx1, sy1, _sx2, sy2 = (float(value) for value in staff_bbox)
    staff_height = max(1.0, sy2 - sy1)
    return bool(mx1 <= center_x <= mx2 and sy1 - staff_height <= center_y <= sy2)


def collect_variant_evidence(
    sweep_point: Mapping[str, Any],
    staff_bboxes: Sequence[Sequence[float]],
    variants: Sequence[str],
) -> dict[str, Any]:
    """Collect one anchored best candidate per (variant, staff) evidence unit."""

    measure_bbox = sweep_point["measure_bbox"]
    votes: Counter[int] = Counter()
    best_scores: dict[int, float] = {}
    units: list[dict[str, Any]] = []

    for variant in variants:
        variant_run = sweep_point.get("variant_runs", {}).get(variant)
        if not isinstance(variant_run, Mapping):
            continue
        for staff_index, staff_run in enumerate(variant_run.get("staff_runs", [])):
            if staff_index >= len(staff_bboxes):
                continue
            anchored: list[tuple[Mapping[str, Any], float, float]] = []
            for candidate in staff_run.get("ranked_numeric_candidates", []):
                if not candidate_is_measure_staff_anchored(
                    candidate, staff_run, measure_bbox, staff_bboxes[staff_index]
                ):
                    continue
                center_x, center_y = candidate_absolute_center(candidate, staff_run)
                anchored.append((candidate, center_x, center_y))
            if not anchored:
                continue
            candidate, center_x, center_y = max(
                anchored, key=lambda item: float(item[0]["score"])
            )
            value = int(candidate["value"])
            score = float(candidate["score"])
            votes[value] += 1
            best_scores[value] = max(best_scores.get(value, float("-inf")), score)
            units.append(
                {
                    "variant": variant,
                    "staff_index": staff_index,
                    "value": value,
                    "score": score,
                    "text": str(candidate.get("text", "")),
                    "confidence_diagnostic_only": float(candidate.get("confidence", 0.0)),
                    "absolute_center": [center_x, center_y],
                }
            )

    if not votes:
        return {
            "winner": None,
            "winner_support": 0,
            "vote_counts": {},
            "evidence_units": units,
        }

    max_support = max(votes.values())
    tied = [value for value, count in votes.items() if count == max_support]
    winner = max(tied, key=lambda value: best_scores[value])
    return {
        "winner": winner,
        "winner_support": int(max_support),
        "vote_counts": {str(value): int(count) for value, count in sorted(votes.items())},
        "evidence_units": units,
    }


def choose_anchored_existing_evidence(
    sweep_point: Mapping[str, Any], staff_bboxes: Sequence[Sequence[float]]
) -> dict[str, Any]:
    """Compose primary and already-recorded fallback evidence without new OCR calls."""

    primary = collect_variant_evidence(sweep_point, staff_bboxes, PRIMARY_VARIANTS)
    fallback = collect_variant_evidence(sweep_point, staff_bboxes, FALLBACK_VARIANTS)
    primary_winner = primary["winner"]
    fallback_winner = fallback["winner"]

    if primary_winner is None:
        selected = fallback_winner
        reason = "fallback_no_anchored_primary"
    elif int(primary["winner_support"]) >= 2:
        selected = primary_winner
        reason = "primary_consensus"
    elif (
        fallback_winner is not None
        and int(fallback["winner_support"]) >= 2
        and fallback_winner != primary_winner
    ):
        # A single primary observation is weak evidence.  If both existing
        # fallback views independently agree on another anchored value, expose
        # that disagreement instead of letting the singleton block fallback.
        selected = fallback_winner
        reason = "fallback_consensus_over_primary_singleton"
    else:
        selected = primary_winner
        reason = "primary_singleton_or_tie"

    return {
        "selected_num": selected,
        "reason": reason,
        "primary": primary,
        "fallback": fallback,
    }


def run(provenance_path: Path, output_path: Path) -> dict[str, Any]:
    provenance = _load_json(provenance_path)
    if not isinstance(provenance, Mapping) or provenance.get("status") != "completed":
        raise ValueError("OCR provenance report is not completed")
    if provenance.get("source_variant_match_failures"):
        raise RuntimeError("OCR provenance report has source replay mismatches")

    records_out: list[dict[str, Any]] = []
    source_correct = 0
    candidate_correct = 0
    candidate_incorrect_numeric: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    point_count = 0
    native_zero: list[dict[str, Any]] = []

    for record in provenance.get("records", []):
        if not isinstance(record, Mapping):
            continue
        expected_num = int(record["expected_skip"]) + 1
        staff_bboxes = record["native_reference"]["primary_staff_bboxes"]
        sweep_out: list[dict[str, Any]] = []
        for point in record.get("sweep", []):
            point_count += 1
            source_num = point.get("source_found_num")
            if source_num == expected_num:
                source_correct += 1
            decision = choose_anchored_existing_evidence(point, staff_bboxes)
            selected_num = decision["selected_num"]
            if selected_num == expected_num:
                candidate_correct += 1
                outcome = "correct"
            elif selected_num is None:
                outcome = "abstain"
                unresolved.append(
                    {
                        "page_id": record["page_id"],
                        "fraction": point["fraction"],
                        "expected_num": expected_num,
                    }
                )
            else:
                outcome = "incorrect"
                candidate_incorrect_numeric.append(
                    {
                        "page_id": record["page_id"],
                        "fraction": point["fraction"],
                        "expected_num": expected_num,
                        "selected_num": selected_num,
                    }
                )
            result = {
                "fraction": float(point["fraction"]),
                "measure_bbox": list(point["measure_bbox"]),
                "expected_num": expected_num,
                "source_num": source_num,
                "source_correct": source_num == expected_num,
                "anchored_existing_evidence_num": selected_num,
                "outcome": outcome,
                **decision,
            }
            sweep_out.append(result)
            if abs(float(point["fraction"])) < 1e-12:
                native_zero.append(
                    {
                        "page_id": record["page_id"],
                        "expected_num": expected_num,
                        "source_num": source_num,
                        "candidate_num": selected_num,
                        "outcome": outcome,
                        "reason": decision["reason"],
                    }
                )
        records_out.append(
            {
                "page_id": record["page_id"],
                "score": record["score"],
                "page_name": record["page_name"],
                "key": record["key"],
                "expected_skip": record["expected_skip"],
                "sweep": sweep_out,
            }
        )

    payload = {
        "schema_version": "issue277.retained_mmr_anchor_consensus.v1",
        "status": "completed",
        "execution_contract": {
            "production_code_modified": False,
            "ocr_reexecuted": False,
            "cnn_reexecuted": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "input": "retained Issue #277 raw OCR provenance only",
            "frozen_A_geometry_used": False,
        },
        "policy": {
            "horizontal_anchor": "candidate center inside candidate-native measure x span",
            "vertical_anchor": "candidate center from one staff-height above through staff bottom",
            "evidence_unit": "one best anchored numeric candidate per preprocessing-variant/staff",
            "primary_consensus": "support>=2 wins",
            "fallback_rule": "two agreeing existing fallback views may override a conflicting primary singleton",
            "rapidocr_confidence": "recorded for diagnostics only; not used in decisions",
        },
        "summary": {
            "sweep_point_count": point_count,
            "source_correct": source_correct,
            "candidate_correct": candidate_correct,
            "candidate_abstain": len(unresolved),
            "candidate_incorrect_numeric": len(candidate_incorrect_numeric),
        },
        "native_zero": native_zero,
        "unresolved": unresolved,
        "incorrect_numeric_predictions": candidate_incorrect_numeric,
        "records": records_out,
    }
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.provenance, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                **payload["summary"],
                "unresolved": payload["unresolved"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
