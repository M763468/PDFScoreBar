#!/usr/bin/env python3
"""Read-only current-production equal-x audit for Issue #286.

The tool consumes retained pipeline run manifests. It does not run detector,
HOMR, SR, OMR-DLN, CNN, MMR, or OCR inference. It replays Phase-A numbering
with the current checkout, inventories exact-x representative ambiguity, and
screens deterministic selectors without selecting a production rule.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from src.pipeline.core.config import load_yaml
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import load_json
from tools.issue120.eval_full68_from_intermediates import SCORES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_CONFIG = PROJECT_ROOT / "configs/dense_full_pipeline.yaml"
BBoxTuple = tuple[int, int, int, int]
Selector = Callable[[list[BBoxTuple], dict[BBoxTuple, tuple[int, int]]], BBoxTuple]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def canonical_keys() -> set[tuple[str, str]]:
    return {(score, page) for score, pages in SCORES.items() for page in pages}


def production_contract(config: dict[str, Any]) -> dict[str, Any]:
    detection = config.get("detection") or {}
    steps = config.get("steps") or {}
    numbering = config.get("numbering") or {}
    return {
        "steps": {
            key: steps.get(key)
            for key in ("detection", "apply_barline_overrides", "numbering_base")
        },
        "detection": {
            key: detection.get(key)
            for key in (
                "sr_scale",
                "sr_compile_mode",
                "homr_profile",
                "detector_route",
                "cnn_model_manifest",
                "cnn_threshold",
                "cnn_apply_nms",
                "divisi_rescue",
                "scan_gap_rescue",
                "scan_x_peak_rescue",
                "scan_rightmost_rescue",
                "scan_center_on_peak",
            )
        },
        "numbering": {"force_single_system": numbering.get("force_single_system")},
    }


def contract_diff(expected: Any, actual: Any, path: str = "$") -> list[dict[str, Any]]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        result: list[dict[str, Any]] = []
        for key in sorted(expected):
            child = f"{path}.{key}"
            if key not in actual:
                result.append({"path": child, "expected": expected[key], "actual": None})
            else:
                result.extend(contract_diff(expected[key], actual[key], child))
        return result
    if expected != actual:
        return [{"path": path, "expected": expected, "actual": actual}]
    return []


def resolve_artifact(raw: str | Path, project_root: Path = PROJECT_ROOT) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        return (project_root / path).resolve()
    if path.exists():
        return path
    try:
        relative = path.relative_to("/workspace")
    except ValueError:
        return path
    return (project_root / relative).resolve()


def discover_run_roots(inputs: list[Path]) -> list[Path]:
    roots: set[Path] = set()
    for raw in inputs:
        root = raw.resolve()
        if (root / "manifest.json").is_file():
            roots.add(root)
        elif root.is_dir():
            roots.update(path.parent.resolve() for path in root.rglob("manifest.json"))
        else:
            raise FileNotFoundError(f"Run root not found: {root}")
    if not roots:
        raise FileNotFoundError("No manifest.json found below supplied run roots")
    return sorted(roots)


def page_identity(image_path: Path) -> tuple[str, str]:
    key = (image_path.parent.name, image_path.stem)
    if key in canonical_keys():
        return key
    matches = [score for score in SCORES if score in image_path.parts]
    if len(matches) == 1 and image_path.stem in SCORES[matches[0]]:
        return matches[0], image_path.stem
    raise ValueError(f"Cannot map image to canonical full68 page: {image_path}")


def semantic(payload: dict[str, Any]) -> dict[str, Any]:
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


def topology(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "pages": [
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
            for page in payload.get("pages", [])
        ]
    }


def bbox_tuple(barline: Any) -> BBoxTuple:
    box = barline.bbox
    return int(box.x1), int(box.y1), int(box.x2), int(box.y2)


def groups(system: Any) -> tuple[dict[int, list[BBoxTuple]], dict[BBoxTuple, tuple[int, int]]]:
    unique: dict[BBoxTuple, None] = {}
    rank: dict[BBoxTuple, tuple[int, int]] = {}
    for staff_index, staff in enumerate(system.staves):
        for bar_index, barline in enumerate(staff.barlines):
            box = bbox_tuple(barline)
            unique.setdefault(box, None)
            rank.setdefault(box, (staff_index, bar_index))
    by_x1: dict[int, list[BBoxTuple]] = defaultdict(list)
    for box in unique:
        by_x1[box[0]].append(box)
    relevant = {
        x1: sorted(boxes)
        for x1, boxes in by_x1.items()
        if len(boxes) > 1 and len({box[2] for box in boxes}) > 1
    }
    return relevant, rank


def staff_first(boxes: list[BBoxTuple], rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (rank[box], box))


def staff_last(boxes: list[BBoxTuple], rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return max(boxes, key=lambda box: (rank[box], box))


def topmost(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (box[1], box[3], box[2], box))


def bottommost(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return max(boxes, key=lambda box: (box[1], box[3], box[2], box))


def narrower(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (box[2] - box[0], box))


def wider(boxes: list[BBoxTuple], _rank: dict[BBoxTuple, tuple[int, int]]) -> BBoxTuple:
    return min(boxes, key=lambda box: (-(box[2] - box[0]), box))


SELECTORS: dict[str, Selector] = {
    "staff_order_first": staff_first,
    "staff_order_last": staff_last,
    "topmost": topmost,
    "bottommost": bottommost,
    "narrower": narrower,
    "wider": wider,
}


def inventory_ties(page_obj: Any) -> list[dict[str, Any]]:
    result = []
    for system_index, system in enumerate(page_obj.systems):
        exact_x, rank = groups(system)
        for x1, boxes in sorted(exact_x.items()):
            result.append(
                {
                    "system_index": system_index,
                    "x1": x1,
                    "x2_choices": sorted({box[2] for box in boxes}),
                    "occurrences": [
                        {
                            "bbox": list(box),
                            "staff_index": rank[box][0],
                            "bar_index": rank[box][1],
                        }
                        for box in boxes
                    ],
                }
            )
    return result


def apply_selector(page_obj: Any, selector_name: str) -> tuple[Any, list[dict[str, Any]]]:
    page = copy.deepcopy(page_obj)
    decisions = []
    selector = SELECTORS[selector_name]
    for system_index, system in enumerate(page.systems):
        exact_x, rank = groups(system)
        chosen: dict[int, BBoxTuple] = {}
        for x1, boxes in sorted(exact_x.items()):
            selected = selector(boxes, rank)
            chosen[x1] = selected
            decisions.append(
                {
                    "system_index": system_index,
                    "x1": x1,
                    "boxes": [list(box) for box in boxes],
                    "selected": list(selected),
                    "selected_measure_left_x": selected[2],
                    "selected_occurrence_rank": list(rank[selected]),
                }
            )
        for staff in system.staves:
            staff.barlines = [
                barline
                for barline in staff.barlines
                if bbox_tuple(barline)[0] not in chosen
                or bbox_tuple(barline) == chosen[bbox_tuple(barline)[0]]
            ]
    return page, decisions


def number(page_obj: Any) -> dict[str, Any]:
    score = Score()
    score.pages.append(page_obj)
    MeasureNumberer().number_score(score, start_number=1)
    return semantic(score_to_dict(score))


def make_page(
    image_path: Path,
    barlines_path: Path,
    staff_mask_path: Path,
    page_number: int,
    force_single_system: bool,
) -> Any:
    image = load_image(image_path)
    height, width = image.shape[:2]
    barlines = normalize_barlines(load_json(barlines_path))
    return MeasureNumberingPipeline().process_page(
        barlines,
        staff_mask_path,
        (width, height),
        page_number=page_number,
        assume_one_staff_per_system=force_single_system,
        image=image,
    )


def audit_page(
    run_root: Path,
    manifest: dict[str, Any],
    page_entry: dict[str, Any],
) -> tuple[tuple[str, str], dict[str, Any]]:
    page_id = str(page_entry["page_id"])
    image_path = resolve_artifact(str(page_entry["image_path"]))
    barlines_path = resolve_artifact(str(page_entry["barlines_json"]))
    staff_mask_path = resolve_artifact(str(page_entry["staff_mask"]))
    retained_path = run_root / "intermediate" / page_id / "numbering_base.json"
    required = (image_path, barlines_path, staff_mask_path, retained_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing artifacts for {run_root} {page_id}: {missing}")

    retained = load_json(retained_path)
    retained_semantic = semantic(retained)
    retained_topology = topology(retained)
    page_number = int(retained["pages"][0]["page_number"])
    force_single = bool(
        ((manifest.get("config") or {}).get("numbering") or {}).get("force_single_system", False)
    )
    page_obj = make_page(
        image_path,
        barlines_path,
        staff_mask_path,
        page_number,
        force_single,
    )
    replay = number(copy.deepcopy(page_obj))
    selector_results = {}
    for name in SELECTORS:
        selected_page, decisions = apply_selector(page_obj, name)
        candidate = number(selected_page)
        selector_results[name] = {
            "topology_equal_to_retained": topology(candidate) == retained_topology,
            "semantic_equal_to_retained": candidate == retained_semantic,
            "decisions": decisions,
        }

    identity = page_identity(image_path)
    return identity, {
        "run_root": str(run_root),
        "run_id": manifest.get("run_id"),
        "page_id": page_id,
        "score": identity[0],
        "page": identity[1],
        "inputs": {
            "image": str(image_path),
            "barlines": str(barlines_path),
            "staff_mask": str(staff_mask_path),
            "numbering_base": str(retained_path),
        },
        "sha256": {
            "barlines": sha256(barlines_path),
            "staff_mask": sha256(staff_mask_path),
            "numbering_base": sha256(retained_path),
        },
        "replay": {
            "semantic_equal_to_retained": replay == retained_semantic,
            "topology_equal_to_retained": topology(replay) == retained_topology,
        },
        "equal_x_ties": inventory_ties(page_obj),
        "selectors": selector_results,
    }


def summarize(pages: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    tie_pages = [key for key, value in pages.items() if value["equal_x_ties"]]
    replay_mismatch = [
        key for key, value in pages.items() if not value["replay"]["semantic_equal_to_retained"]
    ]
    selector_summary = {}
    for name in SELECTORS:
        topology_changed = [
            key
            for key, value in pages.items()
            if not value["selectors"][name]["topology_equal_to_retained"]
        ]
        semantic_changed = [
            key
            for key, value in pages.items()
            if not value["selectors"][name]["semantic_equal_to_retained"]
        ]
        selector_summary[name] = {
            "topology_changed_pages": [f"{score}/{page}" for score, page in topology_changed],
            "semantic_changed_pages": [f"{score}/{page}" for score, page in semantic_changed],
        }
    return {
        "page_count": len(pages),
        "equal_x_tie_page_count": len(tie_pages),
        "equal_x_tie_group_count": sum(len(pages[key]["equal_x_ties"]) for key in tie_pages),
        "equal_x_tie_pages": [f"{score}/{page}" for score, page in tie_pages],
        "replay_mismatch_pages": [f"{score}/{page}" for score, page in replay_mismatch],
        "selectors": selector_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, action="append", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument(
        "--allow-config-drift",
        action="store_true",
        help="Permit non-current manifests for explicitly historical diagnostics.",
    )
    args = parser.parse_args()

    expected_contract = production_contract(load_yaml(CURRENT_CONFIG))
    pages: dict[tuple[str, str], dict[str, Any]] = {}
    manifests = []
    for run_root in discover_run_roots(args.run_root):
        manifest_path = run_root / "manifest.json"
        manifest = load_json(manifest_path)
        config = manifest.get("config") or {}
        if (config.get("steps") or {}).get("apply_barline_overrides"):
            raise ValueError("Issue #286 audit requires apply_barline_overrides=false")
        actual_contract = production_contract(config)
        drift = contract_diff(expected_contract, actual_contract)
        if drift and not args.allow_config_drift:
            raise ValueError(
                f"Manifest differs from current production contract: {run_root}: {drift}"
            )
        manifests.append(
            {
                "run_root": str(run_root),
                "manifest_sha256": sha256(manifest_path),
                "run_id": manifest.get("run_id"),
                "current_production_contract_match": not drift,
                "contract_drift": drift,
            }
        )
        page_entries = manifest.get("pages")
        if not isinstance(page_entries, list):
            raise ValueError(f"Manifest pages must be a list: {manifest_path}")
        for entry in page_entries:
            identity, report = audit_page(run_root, manifest, entry)
            if identity in pages:
                raise ValueError(f"Duplicate canonical page: {identity}")
            pages[identity] = report

    expected = canonical_keys()
    observed = set(pages)
    if observed != expected:
        raise ValueError(
            "Supplied manifests do not form canonical full68: "
            f"observed={len(observed)} missing={sorted(expected - observed)} "
            f"extra={sorted(observed - expected)}"
        )

    summary = summarize(pages)
    result = {
        "schema_version": "issue286.current_full68_equal_x_audit.v1",
        "source_commit": git_head(),
        "purpose": "Current Phase-A replay and exact-x sensitivity; no production selector chosen.",
        "current_production_contract": expected_contract,
        "manifests": manifests,
        "summary": summary,
        "pages": {
            f"{score}/{page}": pages[(score, page)]
            for score, canonical_pages in SCORES.items()
            for page in canonical_pages
        },
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 2 if summary["replay_mismatch_pages"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
