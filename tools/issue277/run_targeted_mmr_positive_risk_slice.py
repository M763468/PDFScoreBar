#!/usr/bin/env python3
"""Evaluate a conservative targeted MMR retry against merged J2 on retained positives.

This is experiment-only Issue #277 tooling.  It preserves the production one-shot
OCR result whenever its existing spatial score is above the merged J2 trigger.
Only low-score or no-number one-shot results may use the candidate-native
normalized retry and the scale-relative +1% x1 retry.  Low-CNN and one-bar-sensitive
cases delegate to merged J2, and unresolved low-score positives also delegate to
merged J2.

The script reuses the all-positive retained harness from
``run_composed_mmr_positive_risk_slice.py``.  No production source is modified and
no detector/HOMR/SR/OMR/numbering/full68 scan is executed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRProcessor
from tools.issue277 import run_composed_mmr_positive_risk_slice as base

DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "logs/issue277/issue277_targeted_positive_risk_slice_01/"
    "targeted_mmr_positive_risk_slice_01.json"
)


def retry_candidate_acceptable(number: int | None, score: float) -> bool:
    """A targeted retry must be a span value and have positive spatial support."""

    return number is not None and int(number) >= 2 and float(score) > 0.0


class TargetedRetryProcessor(base.ComposedProcessor):
    """Conservative candidate: keep high-score one-shot output, target J2 work only."""

    def _production_once(
        self,
        image: Any,
        system: Mapping[str, Any],
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        prob: float,
        w_img: int,
        h_img: int,
    ):
        return MMRProcessor._detect_number_with_evidence_once(
            self, image, system, x1, y1, x2, y2, prob, w_img, h_img
        )

    def _production_j2(
        self,
        image: Any,
        system: Mapping[str, Any],
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        prob: float,
        w_img: int,
        h_img: int,
    ):
        return MMRProcessor._detect_number_with_evidence_j2(
            self, image, system, x1, y1, x2, y2, prob, w_img, h_img
        )

    def _detect_number_with_evidence(
        self,
        image: Any,
        system: Mapping[str, Any],
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        prob: float,
        w_img: int,
        h_img: int,
    ):
        measure_bbox = [int(x1), int(y1), int(x2), int(y2)]
        one_shot = self._production_once(
            image, system, x1, y1, x2, y2, prob, w_img, h_img
        )
        found, score, debug, one_bar_evidence = one_shot
        one_bar_evidence = int(one_bar_evidence)

        # Preserve existing low-CNN / one-bar-veto behavior exactly.  The
        # candidate is intended to replace J2 geometry retries, not those contracts.
        if prob <= self.threshold or (
            self.threshold < prob < self.ONE_BAR_VETO_PROB_MAX
            and one_bar_evidence >= self.ONE_BAR_VETO_MIN_EVIDENCE
        ):
            result = self._production_j2(
                image, system, x1, y1, x2, y2, prob, w_img, h_img
            )
            self.decision_trace.append(
                {
                    "stage": "merged_j2_contract_fallback",
                    "one_shot": {
                        "selected_num": found,
                        "selected_score": float(score),
                        "one_bar_evidence": one_bar_evidence,
                    },
                    "selected_num": result[0],
                }
            )
            return result

        # J2 itself does not perturb high-score results.  Preserve that invariant
        # so the lighter candidate cannot create unrelated high-score regressions.
        if found is not None and float(score) > self.JITTER_SCORE_TRIGGER:
            self.decision_trace.append(
                {
                    "stage": "one_shot_high_score_passthrough",
                    "one_shot": {
                        "selected_num": int(found),
                        "selected_score": float(score),
                        "one_bar_evidence": one_bar_evidence,
                    },
                    "selected_num": int(found),
                }
            )
            return one_shot

        staves = system.get("staves", [])
        normalized_values = [
            self._run_normalized_staff(
                image, measure_bbox, stave["bbox"], w_img, h_img
            )
            for stave in staves
        ]
        normalized_num, normalized_score = self._aggregate_staff(normalized_values)
        if retry_candidate_acceptable(normalized_num, normalized_score):
            result = (
                int(normalized_num),
                float(normalized_score),
                "issue277_targeted_normalized_unmasked_heavy_dilate",
                one_bar_evidence,
            )
            self.decision_trace.append(
                {
                    "stage": "targeted_normalized_unmasked_heavy_dilate",
                    "one_shot": {
                        "selected_num": found,
                        "selected_score": float(score),
                        "one_bar_evidence": one_bar_evidence,
                    },
                    "normalized_values": normalized_values,
                    "selected_num": result[0],
                }
            )
            return result

        shifted_bbox = base.scale_relative_x1_bbox(measure_bbox)
        shifted_values: list[tuple[int | None, float]] = []
        if shifted_bbox[0] != measure_bbox[0]:
            shifted_values = [
                self._run_shifted_staff(
                    image, shifted_bbox, stave["bbox"], w_img, h_img
                )
                for stave in staves
            ]
        shifted_num, shifted_score = self._aggregate_staff(shifted_values)
        if retry_candidate_acceptable(shifted_num, shifted_score):
            result = (
                int(shifted_num),
                float(shifted_score),
                "issue277_targeted_scale_relative_x1_retry",
                one_bar_evidence,
            )
            self.decision_trace.append(
                {
                    "stage": "targeted_scale_relative_x1_retry",
                    "one_shot": {
                        "selected_num": found,
                        "selected_score": float(score),
                        "one_bar_evidence": one_bar_evidence,
                    },
                    "normalized_values": normalized_values,
                    "shifted_bbox": shifted_bbox,
                    "shifted_values": shifted_values,
                    "selected_num": result[0],
                }
            )
            return result

        # A no-number one-shot is already a terminal result in merged J2.  Avoid
        # paying to repeat the same one-shot call merely to reproduce None.
        if found is None:
            self.decision_trace.append(
                {
                    "stage": "one_shot_none_passthrough",
                    "one_shot": {
                        "selected_num": None,
                        "selected_score": float(score),
                        "one_bar_evidence": one_bar_evidence,
                    },
                    "normalized_values": normalized_values,
                    "shifted_bbox": shifted_bbox,
                    "shifted_values": shifted_values,
                    "selected_num": None,
                }
            )
            return one_shot

        # If the targeted evidence is not strong enough, retain the validated J2
        # result.  This may duplicate the one-shot OCR on rare unresolved cases;
        # the retained risk slice measures whether the overall tradeoff still wins.
        result = self._production_j2(
            image, system, x1, y1, x2, y2, prob, w_img, h_img
        )
        self.decision_trace.append(
            {
                "stage": "merged_j2_low_score_fallback",
                "one_shot": {
                    "selected_num": int(found),
                    "selected_score": float(score),
                    "one_bar_evidence": one_bar_evidence,
                },
                "normalized_values": normalized_values,
                "shifted_bbox": shifted_bbox,
                "shifted_values": shifted_values,
                "selected_num": result[0],
            }
        )
        return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    original = base.ComposedProcessor
    base.ComposedProcessor = TargetedRetryProcessor
    try:
        payload = base.run(
            positive_audit_path=args.positive_audit,
            reuse_root=args.reuse_root,
            numbering_root=args.numbering_root,
            page033_causal_path=args.page033_causal,
            model_path=args.model,
            output_path=args.output,
            provider_mode=args.provider,
            preflight_only=args.preflight,
        )
    finally:
        base.ComposedProcessor = original

    if args.preflight:
        payload["schema_version"] = "issue277.targeted_mmr_positive_risk_slice.preflight.v1"
    else:
        payload["schema_version"] = "issue277.targeted_mmr_positive_risk_slice.v1"
        payload["execution_contract"]["candidate"] = (
            "production one-shot high-score passthrough; candidate-native full-span "
            "unmasked heavy_dilate then +1% x1 masked no_dilate only for low-score/None; "
            "positive retry spatial score required; merged-J2 fallback for unresolved "
            "low-score, low-CNN, and one-bar-sensitive cases"
        )
        payload["evaluation_note"] = (
            "Exact-vs-J2 is diagnostic only: a difference may be an accepted-GT improvement. "
            "Use rescore_targeted_mmr_positive_risk_slice.py before interpreting differences."
        )
    base._write_json(args.output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-audit", type=Path, default=base.DEFAULT_POSITIVE_AUDIT)
    parser.add_argument("--reuse-root", type=Path, default=base.DEFAULT_REUSE_ROOT)
    parser.add_argument("--numbering-root", type=Path, default=base.DEFAULT_NUMBERING_ROOT)
    parser.add_argument("--page033-causal", type=Path, default=base.DEFAULT_PAGE033_CAUSAL)
    parser.add_argument("--model", type=Path, default=base.DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    payload = run(args)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "summary": payload.get("summary"),
                "runtime": payload.get("runtime"),
                "gates": payload.get("gates"),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
