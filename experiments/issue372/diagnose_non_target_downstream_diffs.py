#!/usr/bin/env python3
"""Classify non-target downstream differences after the Issue #372 production run.

Retained-only. No inference.

Checks:
1. exact final detector bbox equality for Festival Overture pages 001/002;
2. exact Phase-A/final measure-number arithmetic for Prokofiev Symphony 5 page 005;
3. whether production/control next-number metadata satisfies
   start + physical measures + applied MMR skips;
4. local serialized number sequences and any movement-boundary metadata.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from experiments.issue372.run_fresh_downstream_semantic_replay import (
    _extract_boxes,
    _find_page_file,
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def logical(payload: Mapping[str, Any]) -> dict[str, Any]:
    pages = payload.get("pages", [])
    if len(pages) != 1:
        raise ValueError("expected one-page payload")
    systems = []
    for system in pages[0].get("systems", []):
        measures = [m for m in system.get("measures", []) if isinstance(m, Mapping)]
        systems.append(
            {
                "measure_count": len(measures),
                "numbers": [m.get("number", m.get("measure_number")) for m in measures],
                "attributes": [
                    m.get("attribute")
                    for m in measures
                    if m.get("attribute") is not None
                ],
                "bboxes": [m.get("bbox") for m in measures],
            }
        )
    return {"systems": systems}


def override_rows(payload: Mapping[str, Any]) -> list[dict[str, int]]:
    rows = payload.get("measure_overrides", [])
    result = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            try:
                result.append(
                    {
                        "page": int(row["page"]),
                        "system": int(row["system"]),
                        "measure": int(row["measure"]),
                        "skip": int(row["skip"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    return result


def arithmetic(
    *,
    payload: Mapping[str, Any],
    overrides: list[dict[str, int]],
) -> dict[str, Any]:
    metadata = payload.get("numbering_metadata")
    if isinstance(metadata, Mapping):
        start = int(metadata["start_number"])
        nxt = int(metadata["next_number"])
        boundaries = metadata.get("movement_boundaries", [])
    else:
        start = None
        nxt = None
        boundaries = []

    sig = logical(payload)
    measure_count = sum(system["measure_count"] for system in sig["systems"])
    skip_sum = sum(row["skip"] for row in overrides)
    expected = None if start is None else start + measure_count + skip_sum
    return {
        "start": start,
        "next": nxt,
        "measure_count": measure_count,
        "skip_sum": skip_sum,
        "expected_next_without_reset": expected,
        "next_matches_simple_arithmetic": nxt == expected if nxt is not None else None,
        "movement_boundaries": boundaries,
        "number_sequences": [system["numbers"] for system in sig["systems"]],
        "serialized_attributes": [system["attributes"] for system in sig["systems"]],
        "measure_bboxes": [system["bboxes"] for system in sig["systems"]],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    production = load(args.production_report.resolve())
    corrected_root = args.corrected_control_root.resolve()
    x4_root = args.x4_run_root.resolve()

    prod_rows = {}
    for score_summary in production["score_summaries"]:
        score = str(score_summary["score"])
        for page, row in score_summary["page_results"].items():
            prod_rows[(score, str(page))] = row

    festival = {}
    control_detector_root = x4_root / "control" / "aggregate_probe_output"
    for page in ("page_001", "page_002"):
        key = ("Shostakovich-Festival_Overture_Va", page)
        control_path = _find_page_file(
            control_detector_root,
            key[0],
            key[1],
            "pipeline2_no_peak_filtered_cnn.json",
        )
        production_path = Path(str(prod_rows[key]["final_detector"]))
        control_boxes = sorted(_extract_boxes(load(control_path)))
        production_boxes = sorted(_extract_boxes(load(production_path)))
        festival[page] = {
            "exact_final_detector_equal": control_boxes == production_boxes,
            "control_count": len(control_boxes),
            "production_count": len(production_boxes),
            "control_only": [list(x) for x in sorted(set(control_boxes) - set(production_boxes))],
            "production_only": [list(x) for x in sorted(set(production_boxes) - set(control_boxes))],
        }

    score = "Va__Prokofiev_Symphony5"
    page = "page_005"
    key = (score, page)

    control_final_path = (
        corrected_root
        / "current_control_corrected"
        / score
        / page
        / "numbering_final_continued.json"
    )
    control_override_path = (
        corrected_root
        / "current_control_corrected"
        / score
        / page
        / "overrides_mmr.json"
    )
    if not control_final_path.is_file():
        raise FileNotFoundError(control_final_path)
    if not control_override_path.is_file():
        raise FileNotFoundError(control_override_path)

    production_final_path = Path(str(prod_rows[key]["final_numbering"]))
    production_override_path = (
        production_final_path.parents[2]
        / "intermediate"
        / page
        / "overrides_mmr.json"
    )
    # final_numbering is .../outputs/page_xxx/numbering_final.json;
    # pipeline run root is parents[2].
    if not production_override_path.is_file():
        raise FileNotFoundError(production_override_path)

    control_final = load(control_final_path)
    production_final = load(production_final_path)
    control_overrides_raw = override_rows(load(control_override_path))
    production_overrides_raw = override_rows(load(production_override_path))

    # Control replay has already rebased selected overrides to page-local before
    # numbering, while its raw persisted MMR file uses score-local page indices.
    # Select page_005 by score-local index 4 for arithmetic.
    control_applied = [
        {**row, "page": 0}
        for row in control_overrides_raw
        if row["page"] == 4
    ]
    production_applied = [
        {**row, "page": 0}
        for row in production_overrides_raw
        if row["page"] == 4
    ]

    prok = {
        "control_final_path": str(control_final_path),
        "production_final_path": str(production_final_path),
        "control_raw_overrides": control_overrides_raw,
        "production_raw_overrides": production_overrides_raw,
        "control_applied_overrides": control_applied,
        "production_applied_overrides": production_applied,
        "control": arithmetic(payload=control_final, overrides=control_applied),
        "production": arithmetic(payload=production_final, overrides=production_applied),
    }

    result = {
        "schema_version": "issue372.non_target_downstream_diffs.v1",
        "festival_detector_equality": festival,
        "prokofiev5_page005": prok,
    }

    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 non-target downstream diff diagnosis ===")
    print("\n=== Festival detector equality ===")
    for page_name, row in festival.items():
        print(page_name, json.dumps(row, ensure_ascii=False))
    print("\n=== Prokofiev5 page_005 arithmetic ===")
    for label in ("control", "production"):
        print(label, json.dumps(prok[label], ensure_ascii=False))
    print("control_applied_overrides=", control_applied)
    print("production_applied_overrides=", production_applied)
    print(f"\nOUTPUT={out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--corrected-control-root", type=Path, required=True)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
