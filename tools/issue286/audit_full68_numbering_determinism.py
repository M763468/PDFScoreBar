#!/usr/bin/env python3
"""Audit Issue #286 against historical 68-page Phase-A observations.

No detector, HOMR, SR, OMR-DLN, CNN, or OCR inference is performed. The audit
replays only Phase-A numbering from the same canonical images, final barline
artifacts, Proxy/SR staff geometry, and connector-semantic discovery contract
used by the Issue #264/#274 evaluation route.

Issue #286 exists because historical Phase-A numbering can differ when exact-x
barline duplicates reach ``MeasureNumberer`` through an unordered set. Therefore
this audit deliberately accepts multiple historical run roots. It first measures
where those historical Phase-A outputs disagree, then asks whether the new
explicit equal-x rule:

1. preserves every page whose historical observations were already stable; and
2. on historically unstable pages, selects one observed historical semantic
   variant rather than creating a novel topology/geometry result.

The report also inventories every system that contains multiple distinct assigned
barline boxes with the exact same x1. Near-duplicates with distinct x1 remain
governed by the existing ascending-x1 / 15 px policy and are outside this
change's scope.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.common.connector_artifacts import connector_mask_paths_for_numbering
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import load_json
from tools.issue264.run_phase_c_mmr_regression import build_page_specs


def _recursive_diff(left: Any, right: Any, path: str = "$", *, limit: int = 200) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(a: Any, b: Any, here: str) -> None:
        if len(out) >= limit:
            return
        if type(a) is not type(b):
            out.append({"path": here, "left": a, "right": b, "kind": "type_or_value"})
            return
        if isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                if len(out) >= limit:
                    return
                child = f"{here}.{key}"
                if key not in a:
                    out.append({"path": child, "left": None, "right": b[key], "kind": "missing_left"})
                elif key not in b:
                    out.append({"path": child, "left": a[key], "right": None, "kind": "missing_right"})
                else:
                    walk(a[key], b[key], child)
            return
        if isinstance(a, list):
            if len(a) != len(b):
                out.append({"path": f"{here}.length", "left": len(a), "right": len(b), "kind": "length"})
            for index, (av, bv) in enumerate(zip(a, b)):
                if len(out) >= limit:
                    return
                walk(av, bv, f"{here}[{index}]")
            return
        if a != b:
            out.append({"path": here, "left": a, "right": b, "kind": "value"})

    walk(left, right, path)
    return out


def _semantic(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep the Phase-A topology/geometry fields relevant to numbering."""

    pages: list[dict[str, Any]] = []
    for page in payload.get("pages", []):
        systems: list[dict[str, Any]] = []
        for system in page.get("systems", []):
            systems.append(
                {
                    "staves": [staff.get("bbox") for staff in system.get("staves", [])],
                    "measures": [
                        {"number": item.get("number"), "bbox": item.get("bbox")}
                        for item in system.get("measures", [])
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


def _bbox_tuple(barline: Any) -> tuple[int, int, int, int]:
    bbox = barline.bbox
    return int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)


def _equal_x_ties(page_obj: Any) -> list[dict[str, Any]]:
    ties: list[dict[str, Any]] = []
    for system_index, system in enumerate(page_obj.systems):
        unique = {_bbox_tuple(barline) for staff in system.staves for barline in staff.barlines}
        by_x1: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
        for bbox in sorted(unique):
            by_x1[bbox[0]].append(bbox)
        for x1, boxes in sorted(by_x1.items()):
            if len(boxes) < 2:
                continue
            x2_choices = sorted({box[2] for box in boxes})
            if len(x2_choices) < 2:
                continue
            ordered = sorted(
                boxes,
                key=lambda box: (
                    box[0],
                    -(box[2] - box[0]),
                    box[1],
                    box[3],
                    box[2],
                ),
            )
            selected = ordered[0]
            ties.append(
                {
                    "system_index": system_index,
                    "x1": x1,
                    "boxes": [list(box) for box in boxes],
                    "x2_choices": x2_choices,
                    "deterministic_selected": list(selected),
                    "deterministic_measure_left_x": selected[2],
                }
            )
    return ties


def _replay_page(spec: Any) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    image = load_image(spec.image)
    h, w = image.shape[:2]
    raw_barlines = load_json(spec.barlines)
    barline_boxes = normalize_barlines(raw_barlines)
    pipeline = MeasureNumberingPipeline()
    page_obj = pipeline.process_page(
        barline_boxes,
        spec.staff_mask,
        (w, h),
        page_number=spec.global_index + 1,
        assume_one_staff_per_system=False,
        image=image,
    )
    ties = _equal_x_ties(page_obj)
    score = Score()
    score.pages.append(page_obj)
    pipeline.numberer.number_score(score, start_number=1)
    connector_paths = connector_mask_paths_for_numbering(spec.staff_mask)
    connector_info = {
        "source": "proxy_symbol_layers" if connector_paths else "page_image_ink",
        "paths": {key: str(path) for key, path in (connector_paths or {}).items()},
    }
    return score_to_dict(score), ties, connector_info


def _run_report(root: Path) -> dict[str, Any] | None:
    path = root / "phase_c_mmr_regression_report.json"
    if not path.is_file():
        return None
    payload = load_json(path)
    return {
        "path": str(path),
        "status": payload.get("status"),
        "current": payload.get("current"),
        "gates": payload.get("gates"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-root",
        type=Path,
        action="append",
        required=True,
        help=(
            "Historical 68-page run root containing intermediate/page_*/numbering_base.json. "
            "Pass at least two roots when auditing nondeterministic historical outputs."
        ),
    )
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    reference_roots = [path.resolve() for path in args.reference_root]
    if len(reference_roots) < 2:
        raise ValueError("Issue #286 full68 audit requires at least two --reference-root values")
    if len(set(reference_roots)) != len(reference_roots):
        raise ValueError("Duplicate --reference-root values are not useful for the nondeterminism audit")

    specs = build_page_specs()
    if len(specs) != 68:
        raise RuntimeError(f"Expected 68 canonical pages, got {len(specs)}")

    missing: list[str] = []
    for spec in specs:
        for label, path in (
            ("image", spec.image),
            ("barlines", spec.barlines),
            ("staff_mask", spec.staff_mask),
        ):
            if not path.is_file():
                missing.append(f"{spec.page_id} {label}: {path}")
        for root in reference_roots:
            retained = root / "intermediate" / spec.page_id / "numbering_base.json"
            if not retained.is_file():
                missing.append(f"{spec.page_id} reference_numbering_base [{root.name}]: {retained}")
    if missing:
        raise FileNotFoundError("Missing full-68 audit inputs:\n" + "\n".join(f"- {item}" for item in missing))

    page_reports: list[dict[str, Any]] = []
    for spec in specs:
        references: list[dict[str, Any]] = []
        reference_semantics: list[dict[str, Any]] = []
        for root in reference_roots:
            path = root / "intermediate" / spec.page_id / "numbering_base.json"
            payload = load_json(path)
            semantic = _semantic(payload)
            reference_semantics.append(semantic)
            references.append({"root": str(root), "path": str(path), "semantic": semantic})

        replayed, ties, connector_info = _replay_page(spec)
        replayed_sem = _semantic(replayed)
        historical_stable = all(
            semantic == reference_semantics[0] for semantic in reference_semantics[1:]
        )
        matching_reference_indices = [
            index for index, semantic in enumerate(reference_semantics) if replayed_sem == semantic
        ]
        matching_reference_roots = [str(reference_roots[index]) for index in matching_reference_indices]

        reference_pair_diffs: list[dict[str, Any]] = []
        for index in range(1, len(reference_semantics)):
            diff = _recursive_diff(reference_semantics[0], reference_semantics[index])
            if diff:
                reference_pair_diffs.append(
                    {
                        "left_root": str(reference_roots[0]),
                        "right_root": str(reference_roots[index]),
                        "diff": diff,
                    }
                )

        page_reports.append(
            {
                "page_id": spec.page_id,
                "score": spec.score,
                "page_name": spec.page_name,
                "historical_stable": historical_stable,
                "candidate_matches_any_historical_variant": bool(matching_reference_roots),
                "candidate_matching_reference_roots": matching_reference_roots,
                "candidate_diff_vs_first_reference": _recursive_diff(
                    replayed_sem, reference_semantics[0]
                ),
                "historical_reference_diffs": reference_pair_diffs,
                "equal_x_tie_count": len(ties),
                "equal_x_ties": ties,
                "connector_evidence": connector_info,
            }
        )

    tie_pages = [item["page_id"] for item in page_reports if item["equal_x_tie_count"]]
    historical_disagreement = [item for item in page_reports if not item["historical_stable"]]
    stable_candidate_changes = [
        item for item in page_reports
        if item["historical_stable"] and not item["candidate_matches_any_historical_variant"]
    ]
    unstable_candidate_observed = [
        item for item in historical_disagreement if item["candidate_matches_any_historical_variant"]
    ]
    unstable_candidate_novel = [
        item for item in historical_disagreement if not item["candidate_matches_any_historical_variant"]
    ]
    total_ties = sum(int(item["equal_x_tie_count"]) for item in page_reports)

    safe_scope = not stable_candidate_changes and not unstable_candidate_novel
    payload = {
        "schema_version": "issue286.full68_numbering_determinism_audit.v2",
        "status": "completed",
        "reference_roots": [str(root) for root in reference_roots],
        "reference_reports": [
            {"root": str(root), "report": _run_report(root)} for root in reference_roots
        ],
        "scope": {
            "pages": len(page_reports),
            "inference_rerun": False,
            "changed_rule": "exact x1 ties prefer wider barline; distinct-x1 ordering unchanged",
            "reference_use": (
                "Historical Phase-A observations only. Overall run status is reported but is not "
                "treated as proof that one historical numbering variant is canonical."
            ),
        },
        "summary": {
            "pages_audited": len(page_reports),
            "pages_with_equal_x_ties": len(tie_pages),
            "equal_x_tie_group_count": total_ties,
            "historical_stable_pages": len(page_reports) - len(historical_disagreement),
            "historical_disagreement_pages": [item["page_id"] for item in historical_disagreement],
            "candidate_changed_stable_pages": [item["page_id"] for item in stable_candidate_changes],
            "candidate_resolves_to_observed_variant_pages": [
                item["page_id"] for item in unstable_candidate_observed
            ],
            "candidate_novel_on_historically_unstable_pages": [
                item["page_id"] for item in unstable_candidate_novel
            ],
            "candidate_within_historical_semantic_envelope": safe_scope,
        },
        "tie_pages": tie_pages,
        "pages": page_reports,
        "acceptance_interpretation": (
            "Candidate changes no historically stable page and resolves every historically unstable "
            "page to an already observed Phase-A semantic variant. This supports Issue #286 as a "
            "determinization of existing behavior rather than a new page-specific geometry policy."
            if safe_scope
            else "Candidate leaves the observed historical semantic envelope on one or more pages. "
            "Inspect those pages before Issue #286 can proceed."
        ),
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    return 0 if safe_scope else 2


if __name__ == "__main__":
    raise SystemExit(main())
