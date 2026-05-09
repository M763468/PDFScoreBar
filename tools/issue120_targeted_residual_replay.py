#!/usr/bin/env python3
"""Trace selected Issue 120 residuals through existing detection artifacts.

This harness does not rerun the full pipeline. It reads already generated
probe/CNN/filter JSON files and classifies where each residual is present or lost.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.common.barline_evaluation import (
    barline_iou,
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)

LAYER_FILES = {
    "probe_candidates": "pipeline2_no_peak_candidates.json",
    "scored_json": "pipeline2_no_peak_scored.json",
    "filtered_cnn_json": "pipeline2_no_peak_filtered_cnn.json",
}


Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class ManifestItem:
    score: str
    run_id: str
    pages: tuple[str, ...]


def parse_box(value: Any) -> Box | None:
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return None
    if isinstance(value, dict):
        value = value.get("box") or value.get("bbox") or value.get("barline_location")
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return tuple(int(round(float(v))) for v in value[:4])  # type: ignore[return-value]
    return None


def box_from_record(record: Any) -> Box | None:
    return parse_box(record)


def score_from_record(record: Any) -> float | None:
    if isinstance(record, dict) and record.get("score") is not None:
        return float(record["score"])
    return None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_json_records(path: Path) -> list[Any]:
    if not path.exists():
        return []
    data = load_json(path)
    return data if isinstance(data, list) else []


def boxes_from_records(records: Iterable[Any]) -> list[Box]:
    boxes: list[Box] = []
    for record in records:
        box = box_from_record(record)
        if box is not None:
            boxes.append(box)
    return boxes


def load_gt_boxes(path: Path) -> list[Box]:
    boxes: list[Box] = []
    for item in load_json(path):
        if isinstance(item, dict):
            loc = item.get("barline_location") or item.get("box") or item.get("bbox")
        else:
            loc = item
        box = parse_box(loc)
        if box is not None:
            boxes.append(box)
    return boxes


def find_gt_file(gt_root: Path, score: str, page: str) -> Path | None:
    base = gt_root / score / page
    candidates = sorted(base.glob("boxes_sorted*.json"), reverse=True)
    return candidates[0] if candidates else None


def load_manifest(path: Path | None) -> dict[tuple[str, str], ManifestItem]:
    if path is None:
        return {}
    items = {}
    for item in load_json(path):
        score = item["score"]
        pages = tuple(item.get("pages", []))
        manifest_item = ManifestItem(score=score, run_id=item["run_id"], pages=pages)
        for page in pages:
            items[(score, page)] = manifest_item
    return items


def find_page_dir(
    *,
    run_root: Path,
    score: str,
    page: str,
    manifest_map: dict[tuple[str, str], ManifestItem],
) -> Path | None:
    item = manifest_map.get((score, page))
    if item is not None:
        run_dir = run_root / item.run_id
        probe_scan = run_dir / "intermediate" / "probe_scan"
        expected = probe_scan / f"eval2_{item.run_id}_{page}"
        if expected.exists():
            return expected
        matches = sorted(probe_scan.glob(f"*_{page}"))
        if matches:
            return matches[0]

    # Legacy issue120_final_v1 layout: <run_root>/<score>/intermediate/probe_scan/<page-dir>
    score_probe = run_root / score / "intermediate" / "probe_scan"
    if score_probe.exists():
        matches = sorted(score_probe.glob(f"*_{page}"))
        if matches:
            return matches[0]

    # Full-run layout without a manifest: <run_root>/<run-id-containing-score>/...
    for run_dir in sorted(run_root.glob(f"*{score}*")):
        probe_scan = run_dir / "intermediate" / "probe_scan"
        if not probe_scan.exists():
            continue
        matches = sorted(probe_scan.glob(f"*_{page}"))
        if matches:
            return matches[0]
    return None


def iter_residual_rows(
    residuals_csv: Path,
    *,
    residual_type: str,
    residual_layer: str | None,
    score_filter: str | None,
    page_filter: str | None,
    max_rows: int | None,
) -> Iterable[dict[str, str]]:
    with residuals_csv.open(newline="") as handle:
        reader = csv.DictReader(handle)
        yielded = 0
        for row in reader:
            row_type = row.get("type", "")
            if residual_type == "FN":
                type_matches = row_type.startswith("FN")
            elif residual_type == "FP":
                type_matches = row_type == "FP"
            else:
                type_matches = True
            if not type_matches:
                continue
            if residual_layer and row.get("layer") and row.get("layer") != residual_layer:
                continue
            if score_filter and row.get("score") != score_filter:
                continue
            if page_filter and row.get("page") != page_filter:
                continue
            if parse_box(row.get("bbox")) is None:
                continue
            yield row
            yielded += 1
            if max_rows is not None and yielded >= max_rows:
                break


def best_layer_match(
    records: list[Any],
    target: Box,
    gt_boxes: list[Box],
    *,
    row_type: str,
    eval_rule: str,
    vov_threshold: float,
    xdist_threshold: float,
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for index, record in enumerate(records):
        box = box_from_record(record)
        if box is None:
            continue
        xdist = center_distance_x(box, target)
        vov = barline_vertical_overlap(box, target)
        iou = barline_iou(box, target)
        hard_match = is_barline_match(
            box,
            target,
            eval_rule,
            vov_threshold=vov_threshold,
            xdist_threshold=xdist_threshold,
        )
        rank = (1 if hard_match else 0, vov, -xdist, iou)
        candidate = {
            "index": index,
            "box": box,
            "score": score_from_record(record),
            "xdist": xdist,
            "vov": vov,
            "iou": iou,
            "hard_match": hard_match,
            "rank": rank,
        }
        if best is None or candidate["rank"] > best["rank"]:
            best = candidate
    gt_index = ""
    gt_matched: bool | str = ""
    if row_type.startswith("FN") and gt_boxes:
        gt_ranks = [
            (
                (
                    barline_iou(target, gt),
                    barline_vertical_overlap(target, gt),
                    -center_distance_x(target, gt),
                ),
                index,
            )
            for index, gt in enumerate(gt_boxes)
        ]
        gt_index = max(gt_ranks)[1]
        match_result = greedy_barline_match(
            boxes_from_records(records),
            gt_boxes,
            rule_name=eval_rule,
            vov_threshold=vov_threshold,
            xdist_threshold=xdist_threshold,
        )
        gt_matched = gt_index not in set(match_result.false_negative_indices)

    if best is None:
        return {
            "present": False,
            "gt_index": gt_index,
            "gt_matched": gt_matched,
            "best_index": "",
            "best_box": "",
            "best_score": "",
            "best_xdist": "",
            "best_vov": "",
            "best_iou": "",
            "hard_match": False,
        }
    return {
        "present": bool(best["hard_match"]),
        "gt_index": gt_index,
        "gt_matched": gt_matched,
        "best_index": best["index"],
        "best_box": list(best["box"]),
        "best_score": "" if best["score"] is None else best["score"],
        "best_xdist": best["xdist"],
        "best_vov": best["vov"],
        "best_iou": best["iou"],
        "hard_match": bool(best["hard_match"]),
    }


def classify_stage(
    *,
    row_type: str,
    candidate: bool,
    scored: bool,
    filtered: bool,
    filtered_gt_matched: bool | str,
    best_score: Any,
) -> str:
    if not candidate:
        return "candidate_absent"
    if not scored:
        return "scoring_absent"
    if not filtered:
        if best_score == "":
            return "post_filter_or_score_unknown"
        return "cnn_low_score_or_post_filter"
    if row_type.startswith("FN") and filtered_gt_matched is False:
        return "survived_filtered_unmatched_greedy"
    return "survived_filtered"


def trace_residual(
    row: dict[str, str], page_dir: Path | None, args: argparse.Namespace
) -> dict[str, Any]:
    target = parse_box(row.get("bbox"))
    assert target is not None
    base = {
        "type": row.get("type", ""),
        "source_layer": row.get("layer", ""),
        "source_threshold": row.get("threshold", ""),
        "score": row.get("score", ""),
        "page": row.get("page", ""),
        "source_index": row.get("index", row.get("id", "")),
        "source_reason": row.get("reason", ""),
        "bbox": list(target),
        "page_dir": str(page_dir) if page_dir else "",
    }
    if page_dir is None:
        return {**base, "trace_stage": "page_dir_missing"}

    gt_path = find_gt_file(args.gt_root, row.get("score", ""), row.get("page", ""))
    gt_boxes = load_gt_boxes(gt_path) if gt_path else []
    base["gt_path"] = str(gt_path) if gt_path else ""
    base["gt_count"] = len(gt_boxes)

    layer_summaries = {}
    for layer, filename in LAYER_FILES.items():
        path = page_dir / filename
        records = load_json_records(path)
        match = best_layer_match(
            records,
            target,
            gt_boxes,
            row_type=row.get("type", ""),
            eval_rule=args.eval_rule,
            vov_threshold=args.vov_threshold,
            xdist_threshold=args.xdist_threshold,
        )
        layer_summaries[layer] = match
        base[f"{layer}_path"] = str(path) if path.exists() else ""
        base[f"{layer}_count"] = len(records)
        for key, value in match.items():
            if key == "rank":
                continue
            base[f"{layer}_{key}"] = value

    candidate_present = bool(layer_summaries["probe_candidates"]["present"])
    scored_present = bool(layer_summaries["scored_json"]["present"])
    filtered_present = bool(layer_summaries["filtered_cnn_json"]["present"])
    base["trace_stage"] = classify_stage(
        row_type=row.get("type", ""),
        candidate=candidate_present,
        scored=scored_present,
        filtered=filtered_present,
        filtered_gt_matched=layer_summaries["filtered_cnn_json"]["gt_matched"],
        best_score=layer_summaries["scored_json"]["best_score"],
    )
    return base


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (str(row.get("type", "")), str(row.get("score", "")), str(row.get("trace_stage", "")))
        counts[key] = counts.get(key, 0) + 1
    return [
        {"type": key[0], "score": key[1], "trace_stage": key[2], "count": count}
        for key, count in sorted(counts.items())
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--residuals", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--residual-type", choices=["FN", "FP", "all"], default="FN")
    parser.add_argument("--residual-layer", default="filtered_cnn_json")
    parser.add_argument("--score")
    parser.add_argument("--page")
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--eval-rule", default="center_anchor")
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    args = parser.parse_args()

    manifest_map = load_manifest(args.manifest)
    rows = []
    for row in iter_residual_rows(
        args.residuals,
        residual_type=args.residual_type,
        residual_layer=args.residual_layer,
        score_filter=args.score,
        page_filter=args.page,
        max_rows=args.max_rows,
    ):
        page_dir = find_page_dir(
            run_root=args.run_root,
            score=row.get("score", ""),
            page=row.get("page", ""),
            manifest_map=manifest_map,
        )
        rows.append(trace_residual(row, page_dir, args))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "residual_replay.csv", rows)
    summary = summarize(rows)
    write_csv(args.output_dir / "summary_by_stage.csv", summary)
    (args.output_dir / "summary_by_stage.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    print(f"Wrote {args.output_dir / 'residual_replay.csv'}")
    print(f"Wrote {args.output_dir / 'summary_by_stage.csv'}")


if __name__ == "__main__":
    main()
