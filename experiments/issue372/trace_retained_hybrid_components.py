#!/usr/bin/env python3
"""Trace Issue #372 hybrid losses to baseline vs support components.

Read retained D27 and current-production source artifacts only. For each new
pre-CNN FN classified as a hybrid loss, inspect the exact components consumed
by apply_hybrid_consensus_filter():

- original-page baseline HOMR detections;
- current-x4 HOMR support detections;
- OMR-DLN support detections;
- resulting hybrid detections.

No inference is run.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common import barline_iou
from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    is_barline_match,
)
from src.pipeline.steps.hybrid_consensus import load_json_boxes

IOU_THRESHOLD = 0.5


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _host_path(value: str | Path, repo_root: Path) -> Path:
    path = Path(value)
    try:
        return repo_root / path.relative_to("/workspace")
    except ValueError:
        return path


def _normalize_box(raw: Any) -> tuple[int, int, int, int]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 4:
        raise ValueError(f"Invalid bbox: {raw!r}")
    return tuple(int(round(float(value))) for value in raw[:4])


def _legacy_match(box: Sequence[int], gt: Sequence[int]) -> bool:
    return is_barline_match(
        box,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _nearest(
    boxes: Sequence[Sequence[int]],
    gt: Sequence[int],
) -> dict[str, Any] | None:
    if not boxes:
        return None
    box = min(
        boxes,
        key=lambda candidate: (
            -barline_vertical_overlap(candidate, gt),
            center_distance_x(candidate, gt),
        ),
    )
    return {
        "bbox": [int(v) for v in box],
        "vov": barline_vertical_overlap(box, gt),
        "xdist": center_distance_x(box, gt),
    }


def _component_summary(path: Path, gt: tuple[int, int, int, int]) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    boxes = [tuple(int(v) for v in box) for box in load_json_boxes(path)]
    matching = [box for box in boxes if _legacy_match(box, gt)]
    return {
        "path": str(path),
        "box_count": len(boxes),
        "gt_covered": bool(matching),
        "matching_boxes": [list(box) for box in matching],
        "nearest": _nearest(boxes, gt),
        "_boxes": boxes,
    }


def _strip_private(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if not key.startswith("_")}


def _find_baseline_detection(record: Mapping[str, Any], repo_root: Path) -> Path:
    run_dir = record.get("run_dir")
    if not run_dir:
        raise ValueError(f"Inventory record lacks run_dir: {record}")
    page_dir = _host_path(str(run_dir), repo_root)
    if not page_dir.is_dir():
        raise FileNotFoundError(page_dir)

    image = Path(str(record.get("image", "")))
    expected = page_dir / f"{image.stem}_detections.json"
    if expected.is_file():
        return expected

    matches = sorted(page_dir.glob("*_detections.json"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected one baseline detections JSON under {page_dir}, got {len(matches)}"
        )
    return matches[0]


def _hybrid_path(record: Mapping[str, Any], repo_root: Path) -> Path:
    value = record.get("hybrid_predictions")
    if not value:
        raise ValueError(f"Inventory record lacks hybrid_predictions: {record}")
    path = _host_path(str(value), repo_root)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _hybrid_root(record: Mapping[str, Any], repo_root: Path) -> Path:
    hybrid = _hybrid_path(record, repo_root)
    if hybrid.parent.name != "hybrid_results":
        raise ValueError(f"Unexpected hybrid path: {hybrid}")
    return hybrid.parent.parent


def _find_source_result(
    record: Mapping[str, Any],
    *,
    score: str,
    page: str,
    repo_root: Path,
) -> Path:
    hybrid_root = _hybrid_root(record, repo_root)
    direct = hybrid_root / "source_page_workers" / score / page / "result.json"
    if direct.is_file():
        return direct

    worker_root = hybrid_root / "source_page_workers"
    if not worker_root.is_dir():
        raise FileNotFoundError(worker_root)

    hits: list[Path] = []
    for candidate in worker_root.rglob("result.json"):
        try:
            payload = _load_json(candidate)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        image = str(payload.get("image", ""))
        if image.endswith(f"/{score}/{page}.png") or (
            candidate.parent.name == page and candidate.parent.parent.name == score
        ):
            hits.append(candidate)
    if len(hits) != 1:
        raise FileNotFoundError(
            f"Unable to resolve source worker result for {score}/{page} under "
            f"{worker_root}; matches={len(hits)}"
        )
    return hits[0]


def _source_paths(
    record: Mapping[str, Any],
    *,
    score: str,
    page: str,
    repo_root: Path,
) -> dict[str, Path]:
    result_path = _find_source_result(
        record,
        score=score,
        page=page,
        repo_root=repo_root,
    )
    payload = _load_json(result_path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid source worker result: {result_path}")

    sr = payload.get("current_sr_detection")
    omr = payload.get("current_omr")
    if not sr or not omr:
        raise ValueError(
            f"Source worker result lacks current_sr_detection/current_omr: {result_path}"
        )
    sr_path = _host_path(str(sr), repo_root)
    omr_path = _host_path(str(omr), repo_root)
    if not sr_path.is_file():
        raise FileNotFoundError(sr_path)
    if not omr_path.is_file():
        raise FileNotFoundError(omr_path)

    return {
        "worker_result": result_path,
        "baseline": _find_baseline_detection(record, repo_root),
        "sr": sr_path,
        "omr": omr_path,
        "hybrid": _hybrid_path(record, repo_root),
    }


def _inventory_records(
    inventory_path: Path,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    payload = _load_json(inventory_path)
    records = payload.get("records", []) if isinstance(payload, Mapping) else []
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        key = (str(record.get("score")), str(record.get("page")))
        if key in result:
            raise ValueError(f"Duplicate inventory record: {key}")
        result[key] = record
    return result


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


def _current_inventory_paths(
    issue43_report: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Path]:
    provenance = issue43_report.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("Issue #43 report lacks provenance")
    groups = provenance.get("upstream_groups")
    if not isinstance(groups, list):
        raise ValueError("Issue #43 report lacks provenance.upstream_groups")
    result: dict[str, Path] = {}
    for group in groups:
        if not isinstance(group, Mapping) or not group.get("inventory"):
            continue
        score = str(group.get("score"))
        result[score] = _host_path(str(group["inventory"]), repo_root)
    return result


def _support_for_baseline(
    baseline_matching: Sequence[Sequence[int]],
    sr_boxes: Sequence[Sequence[int]],
    omr_boxes: Sequence[Sequence[int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for baseline in baseline_matching:
        sr_ranked = sorted(
            ((barline_iou(baseline, box), box) for box in sr_boxes),
            key=lambda item: item[0],
            reverse=True,
        )
        omr_ranked = sorted(
            ((barline_iou(baseline, box), box) for box in omr_boxes),
            key=lambda item: item[0],
            reverse=True,
        )
        sr_iou, sr_box = sr_ranked[0] if sr_ranked else (0.0, None)
        omr_iou, omr_box = omr_ranked[0] if omr_ranked else (0.0, None)
        rows.append(
            {
                "baseline_bbox": [int(v) for v in baseline],
                "best_sr_iou": float(sr_iou),
                "best_sr_bbox": [int(v) for v in sr_box] if sr_box is not None else None,
                "best_omr_iou": float(omr_iou),
                "best_omr_bbox": [int(v) for v in omr_box] if omr_box is not None else None,
                "supported": bool(sr_iou > IOU_THRESHOLD or omr_iou > IOU_THRESHOLD),
            }
        )
    return rows


def _classify_current(
    *,
    baseline: Mapping[str, Any],
    sr: Mapping[str, Any],
    omr: Mapping[str, Any],
    hybrid: Mapping[str, Any],
    support_rows: Sequence[Mapping[str, Any]],
) -> str:
    if hybrid["gt_covered"]:
        return "not_a_hybrid_loss"
    if not baseline["gt_covered"]:
        if sr["gt_covered"] or omr["gt_covered"]:
            return "baseline_missing_support_has_gt"
        return "baseline_missing_no_support_gt"
    if not any(bool(row["supported"]) for row in support_rows):
        return "baseline_present_but_unsupported"
    return "hybrid_contract_mismatch"


def _trace_one(
    paths: Mapping[str, Path],
    gt: tuple[int, int, int, int],
) -> dict[str, Any]:
    baseline = _component_summary(paths["baseline"], gt)
    sr = _component_summary(paths["sr"], gt)
    omr = _component_summary(paths["omr"], gt)
    hybrid = _component_summary(paths["hybrid"], gt)
    support_rows = _support_for_baseline(
        baseline["_boxes"],
        sr["_boxes"],
        omr["_boxes"],
    )
    # Only baseline boxes that themselves cover this GT matter to whether the
    # consensus can retain a GT-covering baseline coordinate.
    matching_set = {tuple(box) for box in baseline["matching_boxes"]}
    relevant_support_rows = [
        row for row in support_rows if tuple(row["baseline_bbox"]) in matching_set
    ]
    classification = _classify_current(
        baseline=baseline,
        sr=sr,
        omr=omr,
        hybrid=hybrid,
        support_rows=relevant_support_rows,
    )
    return {
        "worker_result": str(paths["worker_result"]),
        "baseline": _strip_private(baseline),
        "sr": _strip_private(sr),
        "omr": _strip_private(omr),
        "hybrid": _strip_private(hybrid),
        "baseline_gt_match_support": relevant_support_rows,
        "classification": classification,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    stage_trace = _load_json(args.stage_trace.resolve())
    issue43_report = _load_json(args.issue43_report.resolve())
    if not isinstance(stage_trace, Mapping) or not isinstance(issue43_report, Mapping):
        raise ValueError("Input reports must be JSON objects")

    current_inventory_paths = _current_inventory_paths(
        issue43_report,
        repo_root=args.issue43_repo_root.resolve(),
    )
    d27_cache: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    current_cache: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}

    rows: list[dict[str, Any]] = []
    current_class_counts: Counter[str] = Counter()
    page_class_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for source_row in stage_trace.get("rows", []):
        if not isinstance(source_row, Mapping):
            continue
        if source_row.get("current_first_loss_stage") != "hybrid":
            continue
        score = str(source_row["score"])
        page = str(source_row["page"])
        gt = _normalize_box(source_row["gt_bbox"])
        key = (score, page)

        if score not in d27_cache:
            d27_cache[score] = _inventory_records(
                _d27_inventory(args.d27_run_root.resolve(), score)
            )
        if score not in current_cache:
            inventory_path = current_inventory_paths.get(score)
            if inventory_path is None:
                raise FileNotFoundError(f"Current inventory missing for score {score}")
            current_cache[score] = _inventory_records(inventory_path)

        d27_record = d27_cache[score].get(key)
        current_record = current_cache[score].get(key)
        if d27_record is None or current_record is None:
            raise KeyError(f"Missing inventory record for {score}/{page}")

        d27_paths = _source_paths(
            d27_record,
            score=score,
            page=page,
            repo_root=args.d27_repo_root.resolve(),
        )
        current_paths = _source_paths(
            current_record,
            score=score,
            page=page,
            repo_root=args.issue43_repo_root.resolve(),
        )
        d27 = _trace_one(d27_paths, gt)
        current = _trace_one(current_paths, gt)
        classification = str(current["classification"])
        current_class_counts[classification] += 1
        page_class_counts[f"{score}/{page}"][classification] += 1
        rows.append(
            {
                "score": score,
                "page": page,
                "gt_bbox": list(gt),
                "d27": d27,
                "current": current,
            }
        )

    result = {
        "schema_version": "issue372.retained_hybrid_component_trace.v1",
        "hybrid_loss_count": len(rows),
        "current_classification_counts": dict(sorted(current_class_counts.items())),
        "page_classification_counts": {
            page: dict(sorted(counts.items()))
            for page, counts in sorted(page_class_counts.items())
        },
        "rows": rows,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 retained hybrid-component trace ===")
    print(f"hybrid_loss_count={len(rows)}")
    print(
        "current_classification_counts="
        f"{dict(sorted(current_class_counts.items()))}"
    )
    print("page_classification_counts=")
    for page, counts in result["page_classification_counts"].items():
        print(f"  {page}: {counts}")
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-trace", type=Path, required=True)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--d27-repo-root", type=Path, required=True)
    parser.add_argument("--issue43-report", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
