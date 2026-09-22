#!/usr/bin/env python3
"""Trace Issue #372 newly missing GTs across retained candidate stages.

This is a read-only diagnostic. It compares the accepted Issue #274/D27
retained dense-route artifacts with the Issue #43 current-production retained
upstream/reconstruction artifacts. No inference or candidate regeneration runs.

For each new FN already identified by compare_retained_detector_contracts.py,
the report checks legacy D27 center-anchor coverage at:

    hybrid_predictions -> raw -> filtered -> rescue

for both D27 and current production. This locates the first stage at which the
current path loses candidate coverage that D27 retained.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    is_barline_match,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_box(raw: Any) -> tuple[int, int, int, int] | None:
    if isinstance(raw, Mapping):
        raw = (
            raw.get("bbox")
            or raw.get("pred_bbox")
            or raw.get("orig_bbox")
            or raw.get("barline_location")
        )
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 4:
        return None
    return tuple(int(round(float(value))) for value in raw[:4])


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = _load_json(path)
    records: Any = payload
    if isinstance(payload, Mapping):
        records = payload.get("predictions", payload.get("boxes", payload))
    if not isinstance(records, list):
        return []
    result: list[tuple[int, int, int, int]] = []
    for item in records:
        box = _normalize_box(item)
        if box is not None:
            result.append(box)
    return result


def _is_legacy_match(box: tuple[int, int, int, int], gt: tuple[int, int, int, int]) -> bool:
    return is_barline_match(
        box,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _coverage(path: Path, gt: tuple[int, int, int, int]) -> dict[str, Any]:
    boxes = _load_boxes(path)
    matches = [box for box in boxes if _is_legacy_match(box, gt)]
    nearest = None
    if boxes:
        ranked = sorted(
            boxes,
            key=lambda box: (
                -barline_vertical_overlap(box, gt),
                center_distance_x(box, gt),
            ),
        )
        box = ranked[0]
        nearest = {
            "bbox": list(box),
            "vov": barline_vertical_overlap(box, gt),
            "xdist": center_distance_x(box, gt),
        }
    return {
        "path": str(path),
        "box_count": len(boxes),
        "covered": bool(matches),
        "matching_boxes": [list(box) for box in matches],
        "nearest": nearest,
    }


def _host_path(value: str | Path, repo_root: Path) -> Path:
    path = Path(value)
    try:
        return repo_root / path.relative_to("/workspace")
    except ValueError:
        return path


def _find_page_file(root: Path, score: str, page: str) -> Path:
    filename = "pipeline2_no_peak_candidates.json"
    candidates = (
        root / score / page / filename,
        root / f"eval2_{score}_{page}" / filename,
        root / score / f"eval2_{score}_{page}" / filename,
    )
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted(root.rglob(f"eval2_{score}_{page}/{filename}"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(
        f"Unable to resolve {score}/{page} under {root}; matches={len(matches)}"
    )


def _inventory_record(inventory_path: Path, score: str, page: str) -> Mapping[str, Any]:
    payload = _load_json(inventory_path)
    records = payload.get("records", []) if isinstance(payload, Mapping) else []
    hits = [
        item
        for item in records
        if isinstance(item, Mapping)
        and str(item.get("score")) == score
        and str(item.get("page")) == page
    ]
    if len(hits) != 1:
        raise ValueError(
            f"Expected one inventory record for {score}/{page} in {inventory_path}, got {len(hits)}"
        )
    return hits[0]


def _d27_inventory(d27_run_root: Path, score: str) -> Path:
    path = (
        d27_run_root
        / "runs"
        / score
        / "intermediate"
        / "dense_full_pipeline_inputs"
        / "inventory.json"
    )
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _d27_stage_root(d27_run_root: Path, score: str, stage: str) -> Path:
    path = (
        d27_run_root
        / "runs"
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / stage
    )
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def _current_inventory_by_score(
    issue43_report: Mapping[str, Any],
    *,
    issue43_repo_root: Path,
) -> dict[str, Path]:
    provenance = issue43_report.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("Issue #43 report lacks provenance")
    groups = provenance.get("upstream_groups")
    if not isinstance(groups, list):
        raise ValueError("Issue #43 report lacks provenance.upstream_groups")
    result: dict[str, Path] = {}
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        score = str(group.get("score"))
        inventory = group.get("inventory")
        if not inventory:
            continue
        result[score] = _host_path(str(inventory), issue43_repo_root)
    return result


def _current_stage_roots(
    issue43_report: Mapping[str, Any],
    *,
    issue43_repo_root: Path,
) -> dict[str, Path]:
    variants = issue43_report.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("Issue #43 report lacks variants")
    full_width = variants.get("full_width")
    if not isinstance(full_width, Mapping):
        raise ValueError("Issue #43 report lacks variants.full_width")
    mapping = {
        "raw": "raw_candidates_root",
        "filtered": "filtered_candidates_root",
        "rescue": "probe_rescue_root",
    }
    result: dict[str, Path] = {}
    for stage, field in mapping.items():
        raw = full_width.get(field)
        if not raw:
            raise ValueError(f"Issue #43 full_width lacks {field}")
        path = _host_path(str(raw), issue43_repo_root)
        if not path.is_dir():
            raise FileNotFoundError(path)
        result[stage] = path
    return result


def _first_loss_stage(current: Mapping[str, Mapping[str, Any]]) -> str:
    order = ("hybrid", "raw", "filtered", "rescue")
    previous_covered = None
    for stage in order:
        covered = bool(current[stage]["covered"])
        if not covered:
            if stage == "hybrid":
                return "hybrid"
            if previous_covered:
                return stage
        previous_covered = covered
    if bool(current["rescue"]["covered"]):
        return "not_lost_before_rescue"
    return "already_missing_before_observed_boundary"


def run(args: argparse.Namespace) -> dict[str, Any]:
    comparison_path = args.comparison.resolve()
    d27_run_root = args.d27_run_root.resolve()
    issue43_report_path = args.issue43_report.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    d27_repo_root = args.d27_repo_root.resolve()
    output = args.output.resolve()

    comparison = _load_json(comparison_path)
    issue43_report = _load_json(issue43_report_path)
    if not isinstance(comparison, Mapping) or not isinstance(issue43_report, Mapping):
        raise ValueError("Input reports must be JSON objects")

    regression = comparison.get("d27_to_current_legacy_fixed12")
    if not isinstance(regression, Mapping):
        raise ValueError("Comparison lacks d27_to_current_legacy_fixed12")
    new_fns = regression.get("new_fns")
    if not isinstance(new_fns, list):
        raise ValueError("Comparison lacks new_fns[]")

    current_inventories = _current_inventory_by_score(
        issue43_report, issue43_repo_root=issue43_repo_root
    )
    current_stage_roots = _current_stage_roots(
        issue43_report, issue43_repo_root=issue43_repo_root
    )

    rows: list[dict[str, Any]] = []
    loss_counts: Counter[str] = Counter()
    d27_rescue_missing = 0

    for item in new_fns:
        if not isinstance(item, Mapping):
            continue
        score = str(item["score"])
        page = str(item["page"])
        gt = _normalize_box(item["gt_bbox"])
        if gt is None:
            raise ValueError(f"Invalid GT bbox: {item}")

        d27_inventory_path = _d27_inventory(d27_run_root, score)
        current_inventory_path = current_inventories.get(score)
        if current_inventory_path is None:
            raise FileNotFoundError(f"No current inventory for score {score}")
        if not current_inventory_path.is_file():
            raise FileNotFoundError(current_inventory_path)

        d27_record = _inventory_record(d27_inventory_path, score, page)
        current_record = _inventory_record(current_inventory_path, score, page)

        d27_hybrid_path = _host_path(str(d27_record["hybrid_predictions"]), d27_repo_root)
        current_hybrid_path = _host_path(
            str(current_record["hybrid_predictions"]), issue43_repo_root
        )
        if not d27_hybrid_path.is_file():
            raise FileNotFoundError(d27_hybrid_path)
        if not current_hybrid_path.is_file():
            raise FileNotFoundError(current_hybrid_path)

        d27 = {
            "hybrid": _coverage(d27_hybrid_path, gt),
            "raw": _coverage(
                _find_page_file(
                    _d27_stage_root(d27_run_root, score, "probe_candidates_from_inventory"),
                    score,
                    page,
                ),
                gt,
            ),
            "filtered": _coverage(
                _find_page_file(
                    _d27_stage_root(d27_run_root, score, "probe_candidates_filtered"),
                    score,
                    page,
                ),
                gt,
            ),
            "rescue": _coverage(
                _find_page_file(
                    _d27_stage_root(d27_run_root, score, "probe_rescue_candidates"),
                    score,
                    page,
                ),
                gt,
            ),
        }
        current = {
            "hybrid": _coverage(current_hybrid_path, gt),
            "raw": _coverage(
                _find_page_file(current_stage_roots["raw"], score, page), gt
            ),
            "filtered": _coverage(
                _find_page_file(current_stage_roots["filtered"], score, page), gt
            ),
            "rescue": _coverage(
                _find_page_file(current_stage_roots["rescue"], score, page), gt
            ),
        }

        if not d27["rescue"]["covered"]:
            d27_rescue_missing += 1

        loss_stage = _first_loss_stage(current)
        loss_counts[loss_stage] += 1
        rows.append(
            {
                "score": score,
                "page": page,
                "gt_bbox": list(gt),
                "comparison_stage": item.get("stage"),
                "d27": d27,
                "current": current,
                "current_first_loss_stage": loss_stage,
                "d27_rescue_covered": bool(d27["rescue"]["covered"]),
                "current_rescue_covered": bool(current["rescue"]["covered"]),
                "d27_hybrid_covered": bool(d27["hybrid"]["covered"]),
                "current_hybrid_covered": bool(current["hybrid"]["covered"]),
                "staff_mask_paths": {
                    "d27": str(_host_path(str(d27_record["staff_mask"]), d27_repo_root)),
                    "current": str(
                        _host_path(str(current_record["staff_mask"]), issue43_repo_root)
                    ),
                },
                "clef_mask_paths": {
                    "d27": str(_host_path(str(d27_record["clef_mask"]), d27_repo_root)),
                    "current": str(
                        _host_path(str(current_record["clef_mask"]), issue43_repo_root)
                    ),
                },
            }
        )

    result = {
        "schema_version": "issue372.retained_candidate_loss_trace.v1",
        "inputs": {
            "comparison": str(comparison_path),
            "d27_run_root": str(d27_run_root),
            "issue43_report": str(issue43_report_path),
            "issue43_repo_root": str(issue43_repo_root),
            "d27_repo_root": str(d27_repo_root),
        },
        "new_fn_count": len(rows),
        "d27_rescue_missing_count": d27_rescue_missing,
        "current_first_loss_stage_counts": dict(sorted(loss_counts.items())),
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 retained candidate-loss trace ===")
    print(f"new_fn_count={len(rows)}")
    print(f"d27_rescue_missing_count={d27_rescue_missing}")
    print(f"current_first_loss_stage_counts={dict(sorted(loss_counts.items()))}")
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--issue43-report", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--d27-repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
