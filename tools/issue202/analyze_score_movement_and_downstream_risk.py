#!/usr/bin/env python3
"""Issue #202 helper: compare CNN score movement and downstream risk hints.

This script is intentionally analysis-only.  It does not train, mutate datasets, or
change thresholds.  It reads existing scored/eval outputs and produces reviewable
CSV/Markdown tables for PR discussion.

Typical usage:

    python tools/issue202/analyze_score_movement_and_downstream_risk.py \
      --run old=data/evaluation2/golden_baseline_eval2_bc23deb \
      --run l1=logs/issue202_l1/seed_44/eval_scoring \
      --run l15=logs/issue202_l15/seed_44/eval_scoring_best \
      --targets-csv logs/issue202_l15/impact_targets.csv \
      --output-dir logs/issue202_l15/impact_analysis \
      --score-threshold 0.1

The target CSV must contain at least:

    target_id,page_name,bbox,target_kind

where page_name is the dataset page key, for example
``Va_Prokofiev_Symphony1_page_004``.  ``target_kind`` should be one of
``fp``, ``fn``, ``hard_negative``, ``known_fn``, or another reviewer-facing
label.  Extra columns are preserved in the output when useful.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from PIL import Image
except Exception:  # pragma: no cover - image dimensions are optional evidence
    Image = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import (  # noqa: E402
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
)
from tools.issue120.eval_full68_from_intermediates import (  # noqa: E402
    PageRecord,
    boxes_from_gt,
    find_page_file,
    load_json,
    normalize_box,
)

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class RunSpec:
    name: str
    root: Path


@dataclass(frozen=True)
class ScoredCandidate:
    bbox: Box
    score: float | None
    raw: Any


@dataclass(frozen=True)
class Target:
    target_id: str
    page_name: str
    score_name: str
    page: str
    bbox: Box
    target_kind: str
    note: str = ""


PAGE_NAME_RE = re.compile(r"^(?P<score>.+)_page_(?P<page_num>\d+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Issue #202 target score movement and downstream-risk hints."
    )
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        metavar="NAME=DIR",
        help="Named scored-output root. May be supplied multiple times.",
    )
    parser.add_argument("--targets-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=Path("data/evaluation2/annotations"),
        help="GT annotation root.",
    )
    parser.add_argument(
        "--images-root",
        type=Path,
        default=Path("data/evaluation2/images"),
        help="Optional image root used only to identify terminal/end-barline hints.",
    )
    parser.add_argument("--scored-file", default="pipeline2_no_peak_scored.json")
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--rule-name", default="center_anchor")
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument(
        "--side-candidate-xdist",
        type=float,
        default=40.0,
        help="Distance used for downstream duplicate/side-candidate risk hints.",
    )
    return parser.parse_args()


def parse_runs(values: Iterable[str]) -> list[RunSpec]:
    runs: list[RunSpec] = []
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--run must be NAME=DIR, got: {value}")
        name, root = value.split("=", 1)
        name = name.strip()
        if not name:
            raise SystemExit(f"Empty run name in --run {value!r}")
        runs.append(RunSpec(name=name, root=Path(root)))
    if not runs:
        raise SystemExit("At least one --run NAME=DIR is required")
    return runs


def parse_page_name(page_name: str) -> tuple[str, str]:
    match = PAGE_NAME_RE.match(page_name)
    if not match:
        raise ValueError(f"Invalid page_name, expected '<score>_page_NNN': {page_name}")
    score = match.group("score")
    page = f"page_{match.group('page_num')}"
    return score, page


def parse_bbox(value: str) -> Box:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError(f"bbox must be a JSON list, got: {value}")
    return normalize_box(parsed)


def read_targets(path: Path) -> list[Target]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"target_id", "page_name", "bbox", "target_kind"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"targets CSV missing required columns: {sorted(missing)}")
        targets: list[Target] = []
        for row in reader:
            score, page = parse_page_name(row["page_name"])
            targets.append(
                Target(
                    target_id=row["target_id"],
                    page_name=row["page_name"],
                    score_name=score,
                    page=page,
                    bbox=parse_bbox(row["bbox"]),
                    target_kind=row["target_kind"],
                    note=row.get("note", ""),
                )
            )
    if not targets:
        raise SystemExit(f"No targets in {path}")
    return targets


def read_scored_candidates(path: Path) -> list[ScoredCandidate]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"scored payload must be a list: {path}")
    candidates: list[ScoredCandidate] = []
    for item in payload:
        if isinstance(item, dict) and "bbox" in item:
            score = float(item.get("score", 0.0))
            candidates.append(ScoredCandidate(normalize_box(item["bbox"]), score, item))
        elif isinstance(item, list):
            candidates.append(ScoredCandidate(normalize_box(item), None, item))
    return candidates


def selected_boxes(candidates: Iterable[ScoredCandidate], threshold: float) -> list[Box]:
    boxes: list[Box] = []
    for cand in candidates:
        # Plain-list scored files are treated as already filtered.
        if cand.score is None or cand.score >= threshold:
            boxes.append(cand.bbox)
    return boxes


def centre_y(box: Box) -> float:
    return (box[1] + box[3]) / 2.0


def candidate_sort_key(target: Box, cand: ScoredCandidate) -> tuple[float, float, float]:
    vov = barline_vertical_overlap(target, cand.bbox)
    xdist = center_distance_x(target, cand.bbox)
    score = cand.score if cand.score is not None else 1.0
    return (vov, -xdist, score)


def choose_candidate(target: Box, candidates: list[ScoredCandidate]) -> tuple[ScoredCandidate | None, str]:
    for cand in candidates:
        if cand.bbox == target:
            return cand, "exact_bbox"
    if not candidates:
        return None, "no_candidates"
    best = max(candidates, key=lambda c: candidate_sort_key(target, c))
    if barline_vertical_overlap(target, best.bbox) <= 0:
        return best, "nearest_no_vertical_overlap"
    return best, "nearest_vertical_overlap"


def nearest_box(target: Box, boxes: Sequence[Box]) -> tuple[Box | None, float | None, float | None]:
    if not boxes:
        return None, None, None
    best = min(
        boxes,
        key=lambda b: (
            center_distance_x(target, b),
            abs(centre_y(target) - centre_y(b)),
            -barline_vertical_overlap(target, b),
        ),
    )
    return best, center_distance_x(target, best), barline_vertical_overlap(target, best)


def page_record(target: Target) -> PageRecord:
    return PageRecord(target.score_name, target.page)


def load_gt_boxes(gt_root: Path, target: Target) -> list[Box]:
    path = gt_root / target.score_name / target.page / "boxes_sorted.json"
    if not path.exists():
        raise FileNotFoundError(f"GT not found for {target.page_name}: {path}")
    return boxes_from_gt(load_json(path))


def image_width(images_root: Path, target: Target) -> int | None:
    if Image is None:
        return None
    candidates = [
        images_root / target.score_name / f"{target.page}.png",
        images_root / target.score_name / target.page / "page.png",
        images_root / f"{target.page_name}.png",
    ]
    for path in candidates:
        if path.exists():
            with Image.open(path) as img:
                return int(img.size[0])
    return None


def terminal_hint(box: Box, width: int | None) -> str:
    if width is None or width <= 0:
        return "unknown"
    cx = (box[0] + box[2]) / 2.0
    if cx >= width * 0.92:
        return "near_right_edge"
    if cx <= width * 0.08:
        return "near_left_edge"
    return "not_edge"


def risk_hint(
    *,
    target_kind: str,
    target_box: Box,
    selected: Sequence[Box],
    gt_boxes: Sequence[Box],
    width: int | None,
    side_candidate_xdist: float,
) -> tuple[str, str]:
    kind = target_kind.lower()
    term = terminal_hint(target_box, width)
    if kind in {"fp", "false_positive"}:
        _, xdist, vov = nearest_box(target_box, gt_boxes)
        if xdist is not None and vov is not None and vov >= 0.8 and xdist <= side_candidate_xdist:
            return "low", f"near_gt_side_or_duplicate:x={xdist:.1f},vov={vov:.3f};terminal={term}"
        if term in {"near_left_edge", "near_right_edge"}:
            return "medium", f"extra_terminal_candidate_may_affect_reset;terminal={term}"
        return "high", f"extra_barline_candidate_may_split_measure;nearest_gt_x={xdist};nearest_gt_vov={vov};terminal={term}"

    if kind in {"fn", "false_negative", "known_fn"}:
        nearest_pred, xdist, vov = nearest_box(target_box, selected)
        if nearest_pred is not None and vov is not None and vov >= 0.8 and xdist is not None and xdist <= side_candidate_xdist:
            return "low", f"nearby_selected_side_or_duplicate_remains:x={xdist:.1f},vov={vov:.3f};terminal={term}"
        if term in {"near_left_edge", "near_right_edge"}:
            return "medium", f"terminal_fn_may_affect_section_reset;terminal={term}"
        return "high", f"barline_missing_may_merge_measures;nearest_pred_x={xdist};nearest_pred_vov={vov};terminal={term}"

    return "review", f"target_kind={target_kind};terminal={term}"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def box_to_json(box: Box | None) -> str:
    return "" if box is None else json.dumps(list(box), ensure_ascii=False)


def analyze(args: argparse.Namespace) -> None:
    runs = parse_runs(args.run)
    targets = read_targets(args.targets_csv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    score_rows: list[dict[str, Any]] = []
    impact_rows: list[dict[str, Any]] = []

    # Cache page/run payloads to avoid rereading the same files repeatedly.
    scored_cache: dict[tuple[str, str, str], list[ScoredCandidate]] = {}
    gt_cache: dict[str, list[Box]] = {}
    width_cache: dict[str, int | None] = {}

    for target in targets:
        gt_boxes = gt_cache.setdefault(target.page_name, load_gt_boxes(args.gt_root, target))
        width = width_cache.setdefault(target.page_name, image_width(args.images_root, target))
        nearest_gt, nearest_gt_xdist, nearest_gt_vov = nearest_box(target.bbox, gt_boxes)

        for run in runs:
            record = page_record(target)
            cache_key = (run.name, target.score_name, target.page)
            if cache_key not in scored_cache:
                scored_path = find_page_file(run.root, record, args.scored_file)
                if scored_path is None:
                    raise FileNotFoundError(
                        f"scored file not found for run={run.name} page={target.page_name} under {run.root}"
                    )
                scored_cache[cache_key] = read_scored_candidates(scored_path)
            candidates = scored_cache[cache_key]
            selected = selected_boxes(candidates, args.score_threshold)
            chosen, match_kind = choose_candidate(target.bbox, candidates)
            chosen_box = chosen.bbox if chosen else None
            score = chosen.score if chosen else None
            selected_flag = bool(score is None or score >= args.score_threshold) if chosen else False
            target_xdist = center_distance_x(target.bbox, chosen_box) if chosen_box else None
            target_vov = barline_vertical_overlap(target.bbox, chosen_box) if chosen_box else None
            risk, risk_note = risk_hint(
                target_kind=target.target_kind,
                target_box=target.bbox,
                selected=selected,
                gt_boxes=gt_boxes,
                width=width,
                side_candidate_xdist=args.side_candidate_xdist,
            )
            score_rows.append(
                {
                    "target_id": target.target_id,
                    "target_kind": target.target_kind,
                    "page_name": target.page_name,
                    "bbox": box_to_json(target.bbox),
                    "run": run.name,
                    "score": "" if score is None else f"{score:.6f}",
                    "selected_at_threshold": int(selected_flag),
                    "matched_candidate_bbox": box_to_json(chosen_box),
                    "candidate_match_kind": match_kind,
                    "candidate_xdist_to_target": "" if target_xdist is None else f"{target_xdist:.3f}",
                    "candidate_vov_to_target": "" if target_vov is None else f"{target_vov:.6f}",
                    "nearest_gt_bbox": box_to_json(nearest_gt),
                    "nearest_gt_xdist": "" if nearest_gt_xdist is None else f"{nearest_gt_xdist:.3f}",
                    "nearest_gt_vov": "" if nearest_gt_vov is None else f"{nearest_gt_vov:.6f}",
                    "terminal_hint": terminal_hint(target.bbox, width),
                    "heuristic_downstream_risk": risk,
                    "heuristic_risk_note": risk_note,
                    "note": target.note,
                }
            )

        # One impact row per target using the last run as the primary current state.
        current_run = runs[-1]
        current_candidates = scored_cache[(current_run.name, target.score_name, target.page)]
        current_selected = selected_boxes(current_candidates, args.score_threshold)
        risk, risk_note = risk_hint(
            target_kind=target.target_kind,
            target_box=target.bbox,
            selected=current_selected,
            gt_boxes=gt_boxes,
            width=width,
            side_candidate_xdist=args.side_candidate_xdist,
        )
        impact_rows.append(
            {
                "target_id": target.target_id,
                "target_kind": target.target_kind,
                "page_name": target.page_name,
                "bbox": box_to_json(target.bbox),
                "terminal_hint": terminal_hint(target.bbox, width),
                "heuristic_downstream_risk": risk,
                "heuristic_risk_note": risk_note,
                "manual_review_required": 1,
                "reviewer_measure_count_delta": "",
                "reviewer_numbering_reset_risk": "",
                "reviewer_final_risk": "",
                "reviewer_note": "",
            }
        )

    score_fields = [
        "target_id",
        "target_kind",
        "page_name",
        "bbox",
        "run",
        "score",
        "selected_at_threshold",
        "matched_candidate_bbox",
        "candidate_match_kind",
        "candidate_xdist_to_target",
        "candidate_vov_to_target",
        "nearest_gt_bbox",
        "nearest_gt_xdist",
        "nearest_gt_vov",
        "terminal_hint",
        "heuristic_downstream_risk",
        "heuristic_risk_note",
        "note",
    ]
    impact_fields = [
        "target_id",
        "target_kind",
        "page_name",
        "bbox",
        "terminal_hint",
        "heuristic_downstream_risk",
        "heuristic_risk_note",
        "manual_review_required",
        "reviewer_measure_count_delta",
        "reviewer_numbering_reset_risk",
        "reviewer_final_risk",
        "reviewer_note",
    ]
    score_path = args.output_dir / "score_movement.csv"
    impact_path = args.output_dir / "downstream_impact_review.csv"
    write_csv(score_path, score_rows, score_fields)
    write_csv(impact_path, impact_rows, impact_fields)
    write_report(args.output_dir / "impact_analysis_report.md", runs, targets, score_path, impact_path)


def write_report(path: Path, runs: Sequence[RunSpec], targets: Sequence[Target], score_path: Path, impact_path: Path) -> None:
    run_list = "\n".join(f"- `{run.name}`: `{run.root}`" for run in runs)
    target_list = "\n".join(
        f"- `{target.target_id}` {target.target_kind}: `{target.page_name}` `{list(target.bbox)}`"
        for target in targets
    )
    path.write_text(
        f"""# Issue #202 score movement / downstream impact analysis

This report was generated by `tools/issue202/analyze_score_movement_and_downstream_risk.py`.

## Runs

{run_list}

## Targets

{target_list}

## Outputs

- Score movement CSV: `{score_path}`
- Downstream impact review CSV: `{impact_path}`

## Review notes

The downstream-risk columns are heuristic hints, not final acceptance evidence.
A human reviewer must fill the `reviewer_*` columns in `downstream_impact_review.csv`,
especially for terminal/end-barline and double-barline-side cases.

Use this output to decide whether #202 should remain detector-metric based, move to
downstream-risk acceptance, or stop the CNN retraining path.
""",
        encoding="utf-8",
    )


def main() -> None:
    analyze(parse_args())


if __name__ == "__main__":
    main()
