#!/usr/bin/env python3
"""Audit Issue #286 against the retained canonical 68-page Phase-A outputs.

No detector, HOMR, SR, OMR-DLN, CNN, or OCR inference is performed. The audit
replays only Phase-A numbering from the same canonical images, final barline
artifacts, Proxy/SR staff geometry, and connector-semantic discovery contract
used by the accepted Issue #264/#274 evaluation route. It then compares the
new deterministic equal-x tie rule with retained ``numbering_base.json`` files.

The report also inventories every system that contains multiple distinct
assigned barline boxes with the exact same x1, because only those groups can be
reordered by Issue #286. Near-duplicates with distinct x1 remain governed by the
existing ascending-x1 / 15 px policy and are outside this change's scope.
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
                # Multiple vertical fragments with identical horizontal geometry
                # are deterministic already and cannot change a measure boundary.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retained-root",
        type=Path,
        required=True,
        help="Accepted 68-page Phase-C/full-pipeline run root containing intermediate/page_*/numbering_base.json",
    )
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    retained_root = args.retained_root.resolve()
    specs = build_page_specs()
    if len(specs) != 68:
        raise RuntimeError(f"Expected 68 canonical pages, got {len(specs)}")

    page_reports: list[dict[str, Any]] = []
    missing: list[str] = []
    for spec in specs:
        retained = retained_root / "intermediate" / spec.page_id / "numbering_base.json"
        for label, path in (
            ("image", spec.image),
            ("barlines", spec.barlines),
            ("staff_mask", spec.staff_mask),
            ("retained_numbering_base", retained),
        ):
            if not path.is_file():
                missing.append(f"{spec.page_id} {label}: {path}")
    if missing:
        raise FileNotFoundError("Missing full-68 audit inputs:\n" + "\n".join(f"- {item}" for item in missing))

    for spec in specs:
        retained_path = retained_root / "intermediate" / spec.page_id / "numbering_base.json"
        retained = load_json(retained_path)
        replayed, ties, connector_info = _replay_page(spec)
        retained_sem = _semantic(retained)
        replayed_sem = _semantic(replayed)
        page_reports.append(
            {
                "page_id": spec.page_id,
                "score": spec.score,
                "page_name": spec.page_name,
                "retained_numbering_base": str(retained_path),
                "raw_equal": replayed == retained,
                "semantics_equal": replayed_sem == retained_sem,
                "semantic_diff": _recursive_diff(replayed_sem, retained_sem),
                "equal_x_tie_count": len(ties),
                "equal_x_ties": ties,
                "connector_evidence": connector_info,
            }
        )

    tie_pages = [item["page_id"] for item in page_reports if item["equal_x_tie_count"]]
    changed = [item for item in page_reports if not item["semantics_equal"]]
    changed_with_ties = [item["page_id"] for item in changed if item["equal_x_tie_count"]]
    changed_without_ties = [item["page_id"] for item in changed if not item["equal_x_tie_count"]]
    total_ties = sum(int(item["equal_x_tie_count"]) for item in page_reports)

    payload = {
        "schema_version": "issue286.full68_numbering_determinism_audit.v1",
        "status": "completed",
        "retained_root": str(retained_root),
        "scope": {
            "pages": len(page_reports),
            "inference_rerun": False,
            "changed_rule": "exact x1 ties prefer wider barline; distinct-x1 ordering unchanged",
        },
        "summary": {
            "pages_audited": len(page_reports),
            "pages_with_equal_x_ties": len(tie_pages),
            "equal_x_tie_group_count": total_ties,
            "semantic_equal_pages": len(page_reports) - len(changed),
            "semantic_changed_pages": len(changed),
            "changed_pages_with_equal_x_ties": changed_with_ties,
            "changed_pages_without_equal_x_ties": changed_without_ties,
            "all_retained_semantics_preserved": not changed,
        },
        "tie_pages": tie_pages,
        "changed_pages": changed,
        "pages": page_reports,
        "acceptance_interpretation": (
            "The deterministic rule preserves all retained Phase-A semantics across full68."
            if not changed
            else "One or more retained Phase-A outputs change; inspect every changed tie before Issue #286 can merge."
        ),
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    return 0 if not changed else 2


if __name__ == "__main__":
    raise SystemExit(main())
