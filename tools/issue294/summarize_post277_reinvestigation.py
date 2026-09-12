#!/usr/bin/env python3
"""Summarize the latest successful Issue #294 post-#277 reinvestigation artifacts.

Host-only. Reads the latest retry-evolution and HOMR-X-provenance JSON reports and
prints only the decision-relevant fields. No detector/HOMR/SR/OMR/CNN/OCR/MMR work
is executed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = PROJECT_ROOT / "logs/issue294"


def _latest(pattern: str) -> Path:
    candidates = sorted(LOG_ROOT.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No artifact matches {pattern}")
    return candidates[-1]


def _load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    if payload.get("status") != "completed":
        raise ValueError(f"Artifact is not completed: {path}: {payload.get('status')}")
    return payload


def _skip(value: Any) -> Any:
    return value.get("skip") if isinstance(value, Mapping) else None


def _score(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("score")
    return None if raw is None else round(float(raw), 3)


def _aggregate_staff(values: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [value for value in values if isinstance(value, Mapping)]
    nums = [row.get("number") for row in rows if row.get("number") is not None]
    if not nums:
        return {"numbers": [], "skips": [], "max_score": 0.0}
    return {
        "numbers": nums,
        "skips": [int(number) - 1 for number in nums],
        "max_score": round(max(float(row.get("score", 0.0)) for row in rows), 3),
    }


def _bool_pair(trace: Mapping[str, Any], side: str) -> dict[str, Any]:
    value = trace.get(side)
    if not isinstance(value, Mapping):
        return {}
    nearest = value.get("nearest_final")
    return {
        "final_exact_in_hybrid": value.get("final_box_exact_in_hybrid"),
        "final_exact_in_baseline": value.get("final_box_exact_in_baseline_detection"),
        "nearest_final_center_dx": (
            nearest.get("center_dx") if isinstance(nearest, Mapping) else None
        ),
        "nearest_hybrid_center_dx": (
            value.get("nearest_hybrid", {}).get("center_dx")
            if isinstance(value.get("nearest_hybrid"), Mapping)
            else None
        ),
        "nearest_baseline_center_dx": (
            value.get("nearest_baseline_detection", {}).get("center_dx")
            if isinstance(value.get("nearest_baseline_detection"), Mapping)
            else None
        ),
    }


def main() -> int:
    retry_path = _latest("issue294_post277_mmr_retry_evolution_*.json")
    provenance_path = _latest("issue294_post277_homr_x_provenance_*.json")
    retry = _load(retry_path)
    provenance = _load(provenance_path)

    print(f"retry_artifact={retry_path}")
    print(f"provenance_artifact={provenance_path}")
    print("\n=== MMR retry evolution ===")

    for page_id, page in sorted(retry.get("pages", {}).items()):
        if not isinstance(page, Mapping):
            continue
        for event in page.get("events", []):
            if not isinstance(event, Mapping):
                continue
            key = f"{page_id} s{event.get('system')} m{event.get('measure')}"
            baseline = event.get("baseline", {})
            current = event.get("current_policy_final", {})
            full = event.get("targeted_full_span", {})
            shifted = event.get("targeted_shifted", {})
            sweep = event.get("baseline_x1_sweep", {})
            expected = event.get("expected_skip")
            sweep_hits = [
                offset
                for offset, value in sweep.items()
                if isinstance(value, Mapping) and value.get("skip") == expected
            ]
            print(
                json.dumps(
                    {
                        "key": key,
                        "expected_skip": expected,
                        "bbox": event.get("bbox"),
                        "probability": round(float(event.get("probability", 0.0)), 6),
                        "baseline": {"skip": _skip(baseline), "score": _score(baseline)},
                        "current_policy": {"skip": _skip(current), "score": _score(current)},
                        "high_score_short_circuit": event.get("high_score_baseline_short_circuit"),
                        "x1_sweep_expected_hits": sweep_hits,
                        "full_span_current": _aggregate_staff(full.get("current_staff_relative", [])),
                        "full_span_pre_review": _aggregate_staff(
                            full.get("pre_review_legacy_geometry", [])
                        ),
                        "shifted_bbox": shifted.get("bbox"),
                        "shifted_current": _aggregate_staff(
                            shifted.get("current_staff_relative", [])
                        ),
                        "shifted_pre_review": _aggregate_staff(
                            shifted.get("pre_review_legacy_geometry", [])
                        ),
                    },
                    ensure_ascii=False,
                )
            )

    print("\n=== HOMR / evaluator X provenance ===")
    for page_id, page in sorted(provenance.get("pages", {}).items()):
        if not isinstance(page, Mapping):
            continue
        variants = page.get("variants", {})
        comparisons = page.get("comparisons", [])
        a_events = variants.get("A_production", {}).get("events", [])
        b_events = variants.get("B_b377_mapping_guarded", {}).get("events", [])
        for index, comparison in enumerate(comparisons):
            if not isinstance(comparison, Mapping):
                continue
            a_event = a_events[index] if index < len(a_events) else {}
            b_event = b_events[index] if index < len(b_events) else {}
            print(
                json.dumps(
                    {
                        "key": f"{page_id} s{comparison.get('system')} m{comparison.get('measure')}",
                        "bbox_delta_B_minus_A": comparison.get("measure_bbox_delta_B_minus_A"),
                        "A_left": _bool_pair(a_event, "left_boundary"),
                        "A_right": _bool_pair(a_event, "right_boundary"),
                        "B_left": _bool_pair(b_event, "left_boundary"),
                        "B_right": _bool_pair(b_event, "right_boundary"),
                    },
                    ensure_ascii=False,
                )
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
