#!/usr/bin/env python3
"""Screen deterministic exact-x barline selectors for Issue #286.

The production MeasureNumberer currently gathers system barlines in a set and
sorts only by x1. Equal-x candidates can therefore be ordered by set iteration.
This tool keeps the current Phase-A builder/grouping fixed, prunes only exact-x
candidate groups according to several deterministic selectors, and then runs the
unchanged production MeasureNumberer. No detector/HOMR/SR/OMR/MMR inference is
performed.

Historical Phase-A roots are used only to classify whether a selector changes a
page that was stable across retained runs, and whether an historically unstable
page resolves to an already-observed semantic variant. Selector-to-selector
comparisons use the same current page objects and therefore isolate the exact-x
selection policy from unrelated historical code drift.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import load_json
from tools.issue264.run_phase_c_mmr_regression import build_page_specs

BBoxTuple = tuple[int, int, int, int]
Selector = Callable[[list[BBoxTuple], dict[BBoxTuple, tuple[int, int]]], BBoxTuple]


def _bbox_tuple(barline: Any) -> BBoxTuple:
    bbox = barline.bbox
    return int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)


def _width(box: BBoxTuple) -> int:
    return box[2] - box[0]


def _height(box: BBoxTuple) -> int:
    return box[3] - box[1]


def _staff_order_first(boxes: list[BBoxTuple], rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (rank[box], box))


def _staff_order_last(boxes: list[BBoxTuple], rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return max(boxes, key=lambda box: (rank[box], box))


def _topmost(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (box[1], box[3], box[2], box))


def _bottommost(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return max(boxes, key=lambda box: (box[1], box[3], box[2], box))


def _narrower(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (_width(box), box[1], box[3], box[2], box))


def _wider(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (-_width(box), box[1], box[3], box[2], box))


def _tallest(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (-_height(box), box[1], box[3], box[2], box))


def _shortest(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (_height(box), box[1], box[3], box[2], box))


SELECTORS: dict[str, Selector] = {
    "staff_order_first": _staff_order_first,
    "staff_order_last": _staff_order_last,
    "topmost": _topmost,
    "bottommost": _bottommost,
    "narrower": _narrower,
    "wider": _wider,
    "tallest": _tallest,
    "shortest": _shortest,
}


def _semantic(payload: dict[str, Any]) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page in payload.get("pages", []):
        systems: list[dict[str, Any]] = []
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


def _topology(payload: dict[str, Any]) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page in payload.get("pages", []):
        pages.append(
            {
                "systems": [
                    {
                        "staff_count": len(system.get("staves", [])),
                        "measure_numbers": [
                            measure.get("number") for measure in system.get("measures", [])
                        ],
                    }
                    for system in page.get("systems", [])
                ],
                "empty_systems": page.get("empty_systems", []),
            }
        )
    return {"pages": pages}


def _recursive_diff(left: Any, right: Any, path: str = "$", *, limit: int = 80) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def walk(a: Any, b: Any, here: str) -> None:
        if len(result) >= limit:
            return
        if type(a) is not type(b):
            result.append({"path": here, "left": a, "right": b, "kind": "type_or_value"})
            return
        if isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                if len(result) >= limit:
                    return
                child = f"{here}.{key}"
                if key not in a:
                    result.append({"path": child, "left": None, "right": b[key], "kind": "missing_left"})
                elif key not in b:
                    result.append({"path": child, "left": a[key], "right": None, "kind": "missing_right"})
                else:
                    walk(a[key], b[key], child)
            return
        if isinstance(a, list):
            if len(a) != len(b):
                result.append({"path": f"{here}.length", "left": len(a), "right": len(b), "kind": "length"})
            for index, (av, bv) in enumerate(zip(a, b)):
                walk(av, bv, f"{here}[{index}]")
            return
        if a != b:
            result.append({"path": here, "left": a, "right": b, "kind": "value"})

    walk(left, right, path)
    return result


def _make_page(spec: Any) -> Any:
    image = load_image(spec.image)
    height, width = image.shape[:2]
    barline_boxes = normalize_barlines(load_json(spec.barlines))
    pipeline = MeasureNumberingPipeline()
    return pipeline.process_page(
        barline_boxes,
        spec.staff_mask,
        (width, height),
        page_number=spec.global_index + 1,
        assume_one_staff_per_system=False,
        image=image,
    )


def _groups(system: Any) -> tuple[dict[int, list[BBoxTuple]], dict[BBoxTuple, tuple[int, int]]]:
    unique: dict[BBoxTuple, None] = {}
    rank: dict[BBoxTuple, tuple[int, int]] = {}
    for staff_index, staff in enumerate(system.staves):
        for bar_index, barline in enumerate(staff.barlines):
            box = _bbox_tuple(barline)
            unique.setdefault(box, None)
            rank.setdefault(box, (staff_index, bar_index))

    by_x1: dict[int, list[BBoxTuple]] = defaultdict(list)
    for box in unique:
        by_x1[box[0]].append(box)
    relevant = {
        x1: sorted(boxes)
        for x1, boxes in by_x1.items()
        if len(boxes) >= 2 and len({box[2] for box in boxes}) >= 2
    }
    return relevant, rank


def _apply_selector(page_obj: Any, selector_name: str) -> tuple[Any, list[dict[str, Any]]]:
    selector = SELECTORS[selector_name]
    selected_page = copy.deepcopy(page_obj)
    decisions: list[dict[str, Any]] = []

    for system_index, system in enumerate(selected_page.systems):
        groups, rank = _groups(system)
        if not groups:
            continue

        chosen_by_x1: dict[int, BBoxTuple] = {}
        for x1, boxes in sorted(groups.items()):
            chosen = selector(boxes, rank)
            chosen_by_x1[x1] = chosen
            decisions.append(
                {
                    "system_index": system_index,
                    "x1": x1,
                    "boxes": [list(box) for box in boxes],
                    "occurrence_rank": {str(list(box)): list(rank[box]) for box in boxes},
                    "selected": list(chosen),
                    "selected_width": _width(chosen),
                    "selected_height": _height(chosen),
                    "selected_measure_left_x": chosen[2],
                }
            )

        for staff in system.staves:
            filtered = []
            for barline in staff.barlines:
                box = _bbox_tuple(barline)
                chosen = chosen_by_x1.get(box[0])
                if chosen is not None and box != chosen:
                    continue
                filtered.append(barline)
            staff.barlines = filtered

    return selected_page, decisions


def _number(page_obj: Any) -> dict[str, Any]:
    score = Score()
    score.pages.append(page_obj)
    MeasureNumberer().number_score(score, start_number=1)
    return _semantic(score_to_dict(score))


def _load_reference_semantics(roots: list[Path], page_id: str) -> list[dict[str, Any]]:
    return [
        _semantic(load_json(root / "intermediate" / page_id / "numbering_base.json"))
        for root in roots
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", action="append", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    roots = [root.resolve() for root in args.reference_root]
    if len(roots) < 2:
        raise ValueError("At least two --reference-root values are required")

    specs = build_page_specs()
    missing: list[str] = []
    for spec in specs:
        for root in roots:
            path = root / "intermediate" / spec.page_id / "numbering_base.json"
            if not path.is_file():
                missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing retained numbering_base files:\n" + "\n".join(missing[:20]))

    selector_pages: dict[str, list[dict[str, Any]]] = {name: [] for name in SELECTORS}
    page_metadata: list[dict[str, Any]] = []

    for spec in specs:
        page_obj = _make_page(spec)
        references = _load_reference_semantics(roots, spec.page_id)
        historical_stable = all(item == references[0] for item in references[1:])
        page_selector_semantics: dict[str, dict[str, Any]] = {}
        page_decisions: dict[str, list[dict[str, Any]]] = {}

        for selector_name in SELECTORS:
            selected_page, decisions = _apply_selector(page_obj, selector_name)
            semantics = _number(selected_page)
            page_selector_semantics[selector_name] = semantics
            page_decisions[selector_name] = decisions

            if historical_stable:
                reference_match = semantics == references[0]
                topology_match = _topology(semantics) == _topology(references[0])
                observed_variant = reference_match
            else:
                reference_match = any(semantics == ref for ref in references)
                topology_match = any(_topology(semantics) == _topology(ref) for ref in references)
                observed_variant = reference_match

            selector_pages[selector_name].append(
                {
                    "page_id": spec.page_id,
                    "historical_stable": historical_stable,
                    "matches_historical_semantics": reference_match,
                    "matches_historical_topology": topology_match,
                    "within_observed_variant": observed_variant,
                    "decision_count": len(decisions),
                    "decisions": decisions,
                    "diff_vs_reference0": _recursive_diff(semantics, references[0])
                    if semantics != references[0]
                    else [],
                }
            )

        baseline = page_selector_semantics["staff_order_first"]
        pairwise = {
            name: {
                "same_as_staff_order_first": semantics == baseline,
                "topology_same_as_staff_order_first": _topology(semantics) == _topology(baseline),
                "diff": _recursive_diff(semantics, baseline) if semantics != baseline else [],
            }
            for name, semantics in page_selector_semantics.items()
            if name != "staff_order_first"
        }
        page_metadata.append(
            {
                "page_id": spec.page_id,
                "score": spec.score,
                "page_name": spec.page_name,
                "historical_stable": historical_stable,
                "reference_roots": [str(root) for root in roots],
                "selector_pairwise": pairwise,
            }
        )

    summaries: dict[str, Any] = {}
    for selector_name, pages in selector_pages.items():
        stable_changed = [
            item["page_id"]
            for item in pages
            if item["historical_stable"] and not item["matches_historical_semantics"]
        ]
        stable_topology_changed = [
            item["page_id"]
            for item in pages
            if item["historical_stable"] and not item["matches_historical_topology"]
        ]
        unstable_observed = [
            item["page_id"]
            for item in pages
            if not item["historical_stable"] and item["within_observed_variant"]
        ]
        unstable_novel = [
            item["page_id"]
            for item in pages
            if not item["historical_stable"] and not item["within_observed_variant"]
        ]
        tie_pages = [item["page_id"] for item in pages if item["decision_count"]]
        summaries[selector_name] = {
            "pages_with_relevant_equal_x_ties": tie_pages,
            "relevant_equal_x_tie_page_count": len(tie_pages),
            "historical_stable_changed_pages": stable_changed,
            "historical_stable_changed_page_count": len(stable_changed),
            "historical_stable_topology_changed_pages": stable_topology_changed,
            "historical_stable_topology_changed_page_count": len(stable_topology_changed),
            "historically_unstable_resolves_to_observed_variant_pages": unstable_observed,
            "historically_unstable_novel_pages": unstable_novel,
        }

    ranking = sorted(
        summaries,
        key=lambda name: (
            summaries[name]["historical_stable_topology_changed_page_count"],
            len(summaries[name]["historically_unstable_novel_pages"]),
            summaries[name]["historical_stable_changed_page_count"],
            name,
        ),
    )

    pairwise_changed: dict[str, list[str]] = {}
    for selector_name in SELECTORS:
        if selector_name == "staff_order_first":
            continue
        pairwise_changed[selector_name] = [
            page["page_id"]
            for page in page_metadata
            if not page["selector_pairwise"][selector_name]["same_as_staff_order_first"]
        ]

    payload = {
        "schema_version": "issue286.equal_x_selector_screen.v1",
        "scope": {
            "pages": len(specs),
            "reference_roots": [str(root) for root in roots],
            "inference_rerun": False,
            "phase_a_builder_reused_once_per_page": True,
            "selector_only_changes_exact_x1_groups_with_multiple_x2": True,
        },
        "ranking": ranking,
        "summaries": summaries,
        "pairwise_vs_staff_order_first": pairwise_changed,
        "selectors": selector_pages,
        "pages": page_metadata,
        "interpretation": {
            "preferred_shape": (
                "Prefer selectors that change no historically stable topology, create no novel "
                "historically-unstable variant, and minimize stable coordinate-only changes."
            ),
            "staff_order_first_note": (
                "This is the minimal semantic interpretation of the existing 'keep first' rule: "
                "SystemBuilder staves are top-to-bottom and each staff's barlines retain assignment order."
            ),
        },
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ranking": ranking, "summaries": summaries}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
