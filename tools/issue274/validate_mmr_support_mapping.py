"""Compare Issue #274 production support mapping with retained feasibility."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.pipeline.mmr_support_reuse import build_mmr_support_data
from src.pipeline.utils.io import load_json, write_json


def _visible_path(value: str, project_root: Path) -> Path:
    """Translate retained host paths when this validator runs in /workspace."""

    path = Path(value)
    if path.is_file():
        return path
    try:
        relative = path.parts[path.parts.index("logs") :]
    except ValueError:
        return path
    return project_root.joinpath(*relative)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feasibility", type=Path, required=True)
    parser.add_argument("--phase-a-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    retained = load_json(args.feasibility)
    project_root = Path(__file__).resolve().parents[2]
    results = []
    mismatches = []
    total_slots = total_mapped = total_fallback = total_union = 0
    for entry in retained["pages"]:
        page_id = entry["page_id"]
        base_path = args.phase_a_root / "intermediate" / page_id / "numbering_base.json"
        support = build_mmr_support_data(
            load_json(base_path), _visible_path(entry["shared_staff_mask"], project_root)
        )
        provenance = support["provenance"]
        expected = [item["effective_bbox"] for item in entry["mappings"]]
        actual = [item["effective_bbox"] for item in provenance["mappings"]]
        if expected != actual:
            mismatches.append({"page_id": page_id, "expected": expected, "actual": actual})
        total_slots += provenance["staff_slot_count"]
        total_mapped += provenance["mapped_count"]
        total_fallback += provenance["fallback_count"]
        total_union += provenance["union_count"]
        results.append(
            {
                "page_id": page_id,
                "staff_slots": provenance["staff_slot_count"],
                "mapped": provenance["mapped_count"],
                "fallback": provenance["fallback_count"],
                "union": provenance["union_count"],
                "effective_bbox_exact": expected == actual,
            }
        )
    write_json(
        args.output,
        {
            "schema_version": "issue274.production_mmr_support_mapping_validation.v1",
            "pages": len(results),
            "staff_slots": total_slots,
            "mapped": total_mapped,
            "fallback": total_fallback,
            "union": total_union,
            "effective_bbox_mismatches": mismatches,
            "page_results": results,
        },
    )


if __name__ == "__main__":
    main()
