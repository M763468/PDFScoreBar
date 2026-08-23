#!/usr/bin/env python3
"""Diagnose the first integrated Issue #284 numbering-base x-coordinate drift.

This is a no-inference artifact analyzer.  It compares the retained baseline and
integrated candidate source artifacts, then inspects hybrid barlines that can
feed the system/measure whose left x coordinate differs.  The goal is to
separate SR/current-HOMR drift from Phase-A barline deduplication/tie behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PAGE = "page_013"
SCORE = "Shostakovich-Sym5-Va"
DEDUP_THRESHOLD = 15


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bbox(value: Any) -> list[int] | None:
    if isinstance(value, Mapping):
        for key in ("bbox", "box", "barline_location"):
            raw = value.get(key)
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) >= 4:
                return [int(round(float(item))) for item in raw[:4]]
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 4:
        return [int(round(float(item))) for item in value[:4]]
    return None


def _boxes(payload: Any) -> list[list[int]]:
    if not isinstance(payload, list):
        raise ValueError("Hybrid payload must be a list")
    result = []
    for item in payload:
        box = _bbox(item)
        if box is not None:
            result.append(box)
    return result


def _overlaps_staff(bar: Sequence[int], staff: Sequence[int]) -> bool:
    inter_y1 = max(int(staff[1]), int(bar[1]))
    inter_y2 = min(int(staff[3]), int(bar[3]))
    if inter_y2 <= inter_y1:
        return False
    overlap_h = inter_y2 - inter_y1
    staff_h = int(staff[3]) - int(staff[1])
    return overlap_h > staff_h * 0.2 or overlap_h > 10


def _system_staff_boxes(numbering: Mapping[str, Any], system_index: int) -> list[list[int]]:
    page = numbering["pages"][0]
    system = page["systems"][system_index]
    return [[int(v) for v in staff["bbox"]] for staff in system.get("staves", [])]


def _system_barlines(hybrid_boxes: Iterable[list[int]], staff_boxes: list[list[int]]) -> list[list[int]]:
    return [box for box in hybrid_boxes if any(_overlaps_staff(box, staff) for staff in staff_boxes)]


def _dedup_groups(boxes: list[list[int]]) -> list[list[list[int]]]:
    ordered = sorted(boxes, key=lambda box: (box[0], box[2], box[1], box[3]))
    groups: list[list[list[int]]] = []
    for box in ordered:
        if not groups or abs(box[0] - groups[-1][-1][0]) >= DEDUP_THRESHOLD:
            groups.append([box])
        else:
            groups[-1].append(box)
    return groups


def _artifact_inventory(hybrid_root: Path) -> dict[str, dict[str, Any]]:
    baseline_page = hybrid_root / "baseline" / "batch" / PAGE
    current_page = (
        hybrid_root
        / "current_support"
        / SCORE
        / PAGE
        / "artifacts"
        / "current_homr"
        / "batch"
        / PAGE
    )
    patterns = {
        "baseline_detection": baseline_page / f"{PAGE}_detections.json",
        "baseline_staff_proxy": baseline_page / f"{PAGE}_proxy_debug_3_staff.png",
        "baseline_staff": baseline_page / f"{PAGE}_debug_3_staff.png",
        "baseline_staff_mask": baseline_page / f"{PAGE}_staff_mask.png",
        "current_detection": current_page / f"{PAGE}_detections.json",
        "current_staff_mask": current_page / f"{PAGE}_staff_mask.png",
        "current_connector_symbols": current_page / f"{PAGE}_connector_symbols.png",
        "current_connector_brace_dot": current_page / f"{PAGE}_connector_brace_dot.png",
    }
    return {
        name: {"path": str(path), "exists": path.is_file(), "sha256": _sha256(path)}
        for name, path in patterns.items()
    }


def _measure_left(numbering: Mapping[str, Any], system_index: int, measure_index: int) -> int:
    return int(numbering["pages"][0]["systems"][system_index]["measures"][measure_index]["bbox"][0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--system-index", type=int, default=3)
    parser.add_argument("--measure-index", type=int, default=3)
    args = parser.parse_args()

    summary = _load(args.candidate_summary.resolve())
    candidate_hybrid = Path(summary["hybrid"]["candidate"]).resolve()
    reference_hybrid = Path(summary["hybrid"]["reference"]).resolve()
    candidate_hybrid_root = candidate_hybrid.parents[1]
    reference_hybrid_root = reference_hybrid.parents[1]

    candidate_run = Path(summary["numbering_final"]["candidate"]).resolve().parents[2]
    reference_run = Path(summary["numbering_final"]["reference"]).resolve().parents[2]
    candidate_numbering = candidate_run / "intermediate" / PAGE / "numbering_base.json"
    reference_numbering = reference_run / "intermediate" / PAGE / "numbering_base.json"

    cand_num = _load(candidate_numbering)
    ref_num = _load(reference_numbering)
    cand_boxes = _boxes(_load(candidate_hybrid))
    ref_boxes = _boxes(_load(reference_hybrid))
    cand_staff = _system_staff_boxes(cand_num, args.system_index)
    ref_staff = _system_staff_boxes(ref_num, args.system_index)
    cand_system_boxes = _system_barlines(cand_boxes, cand_staff)
    ref_system_boxes = _system_barlines(ref_boxes, ref_staff)

    cand_left = _measure_left(cand_num, args.system_index, args.measure_index)
    ref_left = _measure_left(ref_num, args.system_index, args.measure_index)
    target_x2 = {cand_left, ref_left}

    groups = _dedup_groups(cand_system_boxes)
    relevant_groups = [
        group
        for group in groups
        if any(box[2] in target_x2 for box in group)
        or any(min(abs(box[2] - x) for x in target_x2) <= 4 for box in group)
    ]

    cand_artifacts = _artifact_inventory(candidate_hybrid_root)
    ref_artifacts = _artifact_inventory(reference_hybrid_root)
    artifact_comparison = {}
    for name in cand_artifacts:
        left = cand_artifacts[name]
        right = ref_artifacts[name]
        artifact_comparison[name] = {
            "candidate": left,
            "reference": right,
            "sha256_equal": bool(left["sha256"] and left["sha256"] == right["sha256"]),
        }

    payload = {
        "schema_version": "issue284.numbering_base_barline_choice.v1",
        "status": "completed",
        "system_index": args.system_index,
        "measure_index": args.measure_index,
        "measure_left_x": {"candidate": cand_left, "reference": ref_left},
        "hybrid_equal": cand_boxes == ref_boxes,
        "hybrid_box_count": len(cand_boxes),
        "system_staff_boxes_equal": cand_staff == ref_staff,
        "system_staff_boxes": {"candidate": cand_staff, "reference": ref_staff},
        "system_assigned_barlines_equal": sorted(cand_system_boxes) == sorted(ref_system_boxes),
        "system_assigned_barline_count": {
            "candidate": len(cand_system_boxes),
            "reference": len(ref_system_boxes),
        },
        "relevant_dedup_groups": relevant_groups,
        "relevant_group_has_multiple_x2_choices": any(
            len({box[2] for box in group}) > 1 for group in relevant_groups
        ),
        "artifact_comparison": artifact_comparison,
        "interpretation_hints": {
            "duplicate_choice_supported": (
                cand_boxes == ref_boxes
                and cand_staff == ref_staff
                and sorted(cand_system_boxes) == sorted(ref_system_boxes)
                and any(len({box[2] for box in group}) > 1 for group in relevant_groups)
            ),
            "baseline_profile_artifacts_equal": all(
                artifact_comparison[name]["sha256_equal"]
                for name in ("baseline_detection", "baseline_staff_proxy", "baseline_staff", "baseline_staff_mask")
                if artifact_comparison[name]["candidate"]["exists"]
                and artifact_comparison[name]["reference"]["exists"]
            ),
        },
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
