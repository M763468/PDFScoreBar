#!/usr/bin/env python3
"""Temporary read-only source attribution for Issue #284 dense_raw regressions.

Inspects retained artifacts only; no pipeline/model/GPU execution. Remove before PR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path("/workspace")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.barline_evaluation import barline_iou, is_barline_match  # noqa: E402
from src.pipeline.steps.hybrid_consensus import load_json_boxes  # noqa: E402
from tools.issue120.eval_full68_from_intermediates import boxes_from_candidates  # noqa: E402
from tools.issue284.diagnose_stage_e_fn_regression import (  # noqa: E402
    ancestor_named,
    discover_page_artifacts,
    load_json,
    normalize_box,
    reconstruction_paths,
)

VOV = 0.5
XDIST = 12.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snap(
    path: Path | None,
    gt: tuple[int, int, int, int],
    *,
    candidates: bool = False,
) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"available": False, "path": None if path is None else str(path)}
    raw = boxes_from_candidates(load_json(path)) if candidates else load_json_boxes(path)
    boxes = [normalize_box(box) for box in raw]
    matches = [
        box
        for box in boxes
        if is_barline_match(
            box,
            gt,
            rule_name="center_anchor",
            vov_threshold=VOV,
            xdist_threshold=XDIST,
        )
    ]
    ious = [barline_iou(box, gt) for box in boxes]
    return {
        "available": True,
        "path": str(path),
        "count": len(boxes),
        "matching_count": len(matches),
        "exact_gt_geometry_count": sum(box == gt for box in boxes),
        "matching_boxes": [list(box) for box in matches],
        "max_iou_to_gt": max(ious) if ious else None,
        "has_iou_gt_0_5": any(iou > 0.5 for iou in ious),
    }


def find_inventory(final: Path) -> Path:
    route = ancestor_named(final, "dense_full_pipeline_route")
    if route is None:
        raise RuntimeError(f"dense route ancestor not found: {final}")
    path = route.parent / "dense_full_pipeline_inputs" / "inventory.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def record_for(path: Path, score: str, page: str) -> dict[str, Any]:
    payload = load_json(path)
    rows = [
        row
        for row in payload.get("records", [])
        if isinstance(row, dict)
        and row.get("score") == score
        and row.get("page") == page
    ]
    if len(rows) != 1:
        raise RuntimeError(f"{score}/{page}: expected 1 inventory row, found {len(rows)}")
    return dict(rows[0])


def existing(raw: Any) -> Path | None:
    """Resolve retained paths, including historical Docker /workspace paths."""
    if not raw:
        return None
    p = Path(str(raw))
    probes = [p]
    if not p.is_absolute():
        probes.append(ROOT / p)
    else:
        try:
            relative = p.relative_to(WORKSPACE_ROOT)
        except ValueError:
            relative = None
        if relative is not None:
            probes.append(ROOT / relative)

    seen: set[Path] = set()
    for probe in probes:
        try:
            candidate = probe.resolve()
        except OSError:
            candidate = probe
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    return p


def detection_json(page_root: Path | None) -> Path | None:
    if page_root is None or not page_root.is_dir():
        return None
    rows = sorted(page_root.glob("*_detections.json"))
    return rows[0].resolve() if rows else None


def support_paths(hybrid: Path | None, score: str, page: str) -> dict[str, Any]:
    if hybrid is None:
        return {}
    result = hybrid.parent.parent / "current_support" / score / page / "result.json"
    if not result.is_file():
        return {"result": str(result)}
    data = load_json(result)
    out: dict[str, Any] = {"result": str(result.resolve())}
    for key in ("current_sr_detection", "current_omr", "sr_image"):
        out[key] = existing(data.get(key))
    out["sr_sha256_recorded"] = data.get("sr_sha256")
    out["sr_execution_scope"] = data.get("sr_execution_scope")
    return out


def inspect(
    root: Path,
    artifacts: dict[tuple[str, str], dict[str, Any]],
    score: str,
    page: str,
    gt: tuple[int, int, int, int],
) -> dict[str, Any]:
    final = Path(artifacts[(score, page)]["final"])
    inventory = find_inventory(final)
    rec = record_for(inventory, score, page)
    hybrid = existing(rec.get("hybrid_predictions"))
    baseline_page = existing(rec.get("run_dir"))
    support = support_paths(hybrid, score, page)
    recon = reconstruction_paths(final, score, page)

    image = existing(rec.get("image"))
    sr_image = support.get("sr_image")
    sources = {
        "baseline_homr": snap(detection_json(baseline_page), gt),
        "current_sr_homr": snap(
            support.get("current_sr_detection")
            if isinstance(support.get("current_sr_detection"), Path)
            else None,
            gt,
        ),
        "current_omr": snap(
            support.get("current_omr")
            if isinstance(support.get("current_omr"), Path)
            else None,
            gt,
        ),
        "hybrid_consensus": snap(hybrid, gt),
        "dense_raw": snap(recon["dense_raw"], gt, candidates=True),
    }
    hybrid_available = bool(sources["hybrid_consensus"].get("available"))
    if hybrid_available and sources["hybrid_consensus"].get("exact_gt_geometry_count", 0):
        origin = "hybrid_existing_box"
    elif hybrid_available and sources["dense_raw"].get("exact_gt_geometry_count", 0):
        origin = "probe_generated"
    elif not hybrid_available and sources["dense_raw"].get("exact_gt_geometry_count", 0):
        origin = "unresolved_upstream_unavailable"
    else:
        origin = "absent"

    return {
        "root": str(root),
        "inventory": str(inventory),
        "image": None if image is None else str(image),
        "image_sha256": sha256(image) if image is not None and image.is_file() else None,
        "support": {
            **{k: (str(v) if isinstance(v, Path) else v) for k, v in support.items()},
            "sr_sha256_actual": (
                sha256(sr_image)
                if isinstance(sr_image, Path) and sr_image.is_file()
                else None
            ),
        },
        "sources": sources,
        "dense_exact_origin": origin,
        "upstream_source_resolution_complete": all(
            sources[name].get("available")
            for name in (
                "baseline_homr",
                "current_sr_homr",
                "current_omr",
                "hybrid_consensus",
            )
        ),
    }


def compare(a: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    stages = (
        "baseline_homr",
        "current_sr_homr",
        "current_omr",
        "hybrid_consensus",
        "dense_raw",
    )

    def comparable(stage: str) -> bool:
        return bool(a["sources"][stage].get("available")) and bool(
            c["sources"][stage].get("available")
        )

    exact_div = next(
        (
            s
            for s in stages
            if comparable(s)
            and a["sources"][s].get("exact_gt_geometry_count")
            != c["sources"][s].get("exact_gt_geometry_count")
        ),
        None,
    )
    match_div = next(
        (
            s
            for s in stages
            if comparable(s)
            and a["sources"][s].get("matching_boxes")
            != c["sources"][s].get("matching_boxes")
        ),
        None,
    )
    unresolved_stages = [s for s in stages if not comparable(s)]

    if a["dense_exact_origin"] == "hybrid_existing_box":
        boundary = "hybrid_or_component_source"
    elif a["dense_exact_origin"] == "probe_generated":
        boundary = "probe_generation_conditioned_by_hybrid"
    elif a["dense_exact_origin"] == "unresolved_upstream_unavailable":
        boundary = "unresolved_upstream_source_paths"
    else:
        boundary = "unresolved"

    image_equal: bool | None
    if a["image_sha256"] is None or c["image_sha256"] is None:
        image_equal = None
    else:
        image_equal = a["image_sha256"] == c["image_sha256"]

    sr_a = a["support"].get("sr_sha256_actual")
    sr_c = c["support"].get("sr_sha256_actual")
    sr_equal = None if not sr_a or not sr_c else sr_a == sr_c

    return {
        "input_image_sha256_equal": image_equal,
        "sr_image_sha256_equal": sr_equal,
        "accepted_dense_exact_origin": a["dense_exact_origin"],
        "current_dense_exact_origin": c["dense_exact_origin"],
        "first_exact_geometry_divergence": exact_div,
        "first_center_anchor_match_set_divergence": match_div,
        "unresolved_comparison_stages": unresolved_stages,
        "likely_boundary": boundary,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--competition-json", type=Path, required=True)
    ap.add_argument("--accepted-root", type=Path, required=True)
    ap.add_argument("--current-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    comp = load_json(args.competition_json)
    targets = [
        row
        for row in comp.get("false_negatives", [])
        if row.get("classification") == "regression"
        and isinstance(row.get("first_target_match_set_divergence"), dict)
        and row["first_target_match_set_divergence"].get("stage") == "dense_raw"
    ]
    aroot, croot = args.accepted_root.resolve(), args.current_root.resolve()
    aa, ca = discover_page_artifacts(aroot), discover_page_artifacts(croot)
    results, errors = [], []
    for row in targets:
        score, page = str(row["score"]), str(row["page"])
        gt = normalize_box(row["gt_box"])
        try:
            a = inspect(aroot, aa, score, page, gt)
            c = inspect(croot, ca, score, page, gt)
            results.append(
                {
                    "score": score,
                    "page": page,
                    "gt_index": row["gt_index"],
                    "gt_box": list(gt),
                    "accepted": a,
                    "current": c,
                    "comparison": compare(a, c),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "score": score,
                    "page": page,
                    "gt_index": row.get("gt_index"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    payload = {
        "schema_version": "issue284.dense_raw_source_attribution.v2",
        "read_only": True,
        "target_count": len(targets),
        "completed_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "target_count": len(targets),
                "completed_count": len(results),
                "error_count": len(errors),
                "results": [
                    {
                        "score": r["score"],
                        "page": r["page"],
                        "gt_index": r["gt_index"],
                        **r["comparison"],
                    }
                    for r in results
                ],
                "errors": errors,
                "output": str(args.output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if len(results) == 4 and not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
