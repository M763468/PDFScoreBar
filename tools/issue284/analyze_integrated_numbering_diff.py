"""Attribute Issue #284 integrated one-page numbering drift from retained artifacts.

No inference is performed.  The analyzer compares the baseline and candidate
artifacts in production order so a raw final-JSON mismatch is not mistaken for
an SR failure without locating the first semantic divergence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _recursive_diff(
    left: Any, right: Any, path: str = "$", *, limit: int = 200
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(a: Any, b: Any, here: str) -> None:
        if len(out) >= limit:
            return
        if type(a) is not type(b):
            out.append({"path": here, "left": a, "right": b, "kind": "type_or_value"})
            return
        if isinstance(a, dict):
            keys = sorted(set(a) | set(b))
            for key in keys:
                if len(out) >= limit:
                    return
                child = f"{here}.{key}"
                if key not in a:
                    out.append(
                        {"path": child, "left": None, "right": b[key], "kind": "missing_left"}
                    )
                elif key not in b:
                    out.append(
                        {"path": child, "left": a[key], "right": None, "kind": "missing_right"}
                    )
                else:
                    walk(a[key], b[key], child)
            return
        if isinstance(a, list):
            if len(a) != len(b):
                out.append(
                    {"path": f"{here}.length", "left": len(a), "right": len(b), "kind": "length"}
                )
            for index, (av, bv) in enumerate(zip(a, b)):
                if len(out) >= limit:
                    return
                walk(av, bv, f"{here}[{index}]")
            return
        if a != b:
            out.append({"path": here, "left": a, "right": b, "kind": "value"})

    walk(left, right, path)
    return out


def _numbering_semantics(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    pages = []
    for page in payload.get("pages", []):
        systems = []
        for system in page.get("systems", []):
            systems.append(
                {
                    "staves": [staff.get("bbox") for staff in system.get("staves", [])],
                    "measures": [
                        {"number": measure.get("number"), "bbox": measure.get("bbox")}
                        for measure in system.get("measures", [])
                    ],
                }
            )
        pages.append(
            {
                "page_number": page.get("page_number"),
                "width": page.get("width"),
                "height": page.get("height"),
                "systems": systems,
                "empty_systems": page.get("empty_systems", []),
            }
        )
    return {"pages": pages}


def _artifact(run_root: Path, page: str, name: str) -> Path:
    return run_root / "intermediate" / page / name


def _compare_artifact(
    left_path: Path, right_path: Path, *, semantics: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "candidate": str(left_path),
        "reference": str(right_path),
        "candidate_exists": left_path.is_file(),
        "reference_exists": right_path.is_file(),
    }
    if not left_path.is_file() or not right_path.is_file():
        result["available"] = False
        return result
    left = _load(left_path)
    right = _load(right_path)
    result.update(
        {
            "available": True,
            "raw_equal": left == right,
            "raw_diff": _recursive_diff(left, right),
        }
    )
    if semantics:
        left_sem = _numbering_semantics(left)
        right_sem = _numbering_semantics(right)
        result["semantics_equal"] = left_sem == right_sem
        result["semantic_diff"] = _recursive_diff(left_sem, right_sem)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    summary = _load(args.candidate_summary.resolve())
    if summary.get("status") != "completed":
        raise ValueError("Candidate summary is not completed")

    candidate_final = Path(summary["numbering_final"]["candidate"]).resolve()
    reference_final = Path(summary["numbering_final"]["reference"]).resolve()
    candidate_run = candidate_final.parents[2]
    reference_run = reference_final.parents[2]
    page = candidate_final.parent.name

    numbering_base = _compare_artifact(
        _artifact(candidate_run, page, "numbering_base.json"),
        _artifact(reference_run, page, "numbering_base.json"),
        semantics=True,
    )
    mmr_support = _compare_artifact(
        _artifact(candidate_run, page, "mmr_support.json"),
        _artifact(reference_run, page, "mmr_support.json"),
    )
    overrides_mmr = _compare_artifact(
        _artifact(candidate_run, page, "overrides_mmr.json"),
        _artifact(reference_run, page, "overrides_mmr.json"),
    )
    final = _compare_artifact(candidate_final, reference_final, semantics=True)

    # The support sidecar embeds run-specific source paths in provenance.  Compare
    # the views separately because those are what MMR actually consumes.
    if mmr_support.get("available"):
        cand_support = _load(Path(mmr_support["candidate"]))
        ref_support = _load(Path(mmr_support["reference"]))
        cand_views = cand_support.get("views") if isinstance(cand_support, dict) else None
        ref_views = ref_support.get("views") if isinstance(ref_support, dict) else None
        mmr_support["views_equal"] = cand_views == ref_views
        mmr_support["views_diff"] = _recursive_diff(cand_views, ref_views)
        cand_mappings = (cand_support.get("provenance") or {}).get("mappings", [])
        ref_mappings = (ref_support.get("provenance") or {}).get("mappings", [])
        mmr_support["mappings_equal"] = cand_mappings == ref_mappings
        mmr_support["mappings_diff"] = _recursive_diff(cand_mappings, ref_mappings)

    first_divergence = "none"
    if numbering_base.get("available") and not numbering_base.get("semantics_equal", False):
        first_divergence = "numbering_base"
    elif mmr_support.get("available") and not mmr_support.get("views_equal", False):
        first_divergence = "mmr_support"
    elif overrides_mmr.get("available") and not overrides_mmr.get("raw_equal", False):
        first_divergence = "overrides_mmr"
    elif final.get("available") and not final.get("semantics_equal", False):
        first_divergence = "finalization"
    elif final.get("available") and not final.get("raw_equal", False):
        first_divergence = "final_raw_only"

    if first_divergence == "mmr_support":
        interpretation = (
            "Phase-A numbering is preserved, but current-x4 staff geometry supplied to MMR changed; "
            "inspect whether the changed support causes different MMR overrides."
        )
    elif first_divergence == "overrides_mmr":
        interpretation = (
            "Numbering base and MMR support views are equal, but MMR overrides differ; "
            "this points to MMR/OCR run-to-run behavior rather than SR geometry."
        )
    elif first_divergence == "final_raw_only":
        interpretation = "Production numbering topology is equal; the integrated runner's raw JSON equality gate is too strict."
    elif first_divergence == "numbering_base":
        interpretation = "The first semantic difference is before MMR; investigate dense grouping/numbering inputs."
    elif first_divergence == "finalization":
        interpretation = "Inputs through MMR overrides agree, but final numbering semantics differ during finalization."
    else:
        interpretation = "No retained production-semantic divergence was found."

    payload = {
        "schema_version": "issue284.integrated_numbering_diff.v1",
        "status": "completed",
        "page": page,
        "hybrid_equal": bool(summary.get("hybrid", {}).get("parsed_equal")),
        "numbering_base": numbering_base,
        "mmr_support": mmr_support,
        "overrides_mmr": overrides_mmr,
        "numbering_final": final,
        "first_divergence": first_divergence,
        "interpretation": interpretation,
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
