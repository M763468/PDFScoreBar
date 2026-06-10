#!/usr/bin/env python3
"""Issue #202 helper: render visual review crops for FP/FN regressions.

This script is analysis-only. It reads existing scored outputs, GT annotations, and
page images, then writes local PNGs/HTML-like Markdown so a human reviewer can
inspect whether an FP/FN affects downstream measure counting.

Typical usage:

    python tools/issue202/visualize_barline_regressions.py \
      --run old=data/evaluation2/golden_baseline_eval2_bc23deb \
      --run l1=logs/issue202_l1/seed_44/eval_scoring \
      --run l15=logs/issue202_l15/seed_44/eval_scoring_best \
      --targets-csv logs/issue202_l15/impact_targets.csv \
      --output-dir logs/issue202_l15/impact_visuals \
      --score-threshold 0.1

Target CSV columns are shared with
``analyze_score_movement_and_downstream_risk.py``:

    target_id,page_name,bbox,target_kind,note

The generated files are for local review and must not be committed.
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

from PIL import Image, ImageDraw, ImageFont

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
PAGE_NAME_RE = re.compile(r"^(?P<score>.+)_page_(?P<page_num>\d+)$")

# RGB colors used in output images.
COLOR_TARGET = (255, 64, 64)
COLOR_GT = (0, 180, 0)
COLOR_SELECTED_PRED = (48, 112, 255)
COLOR_TARGET_CANDIDATE = (255, 160, 0)
COLOR_BACKGROUND = (255, 255, 255)
COLOR_TEXT = (20, 20, 20)
COLOR_HEADER = (245, 245, 245)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render local visual overlays for Issue #202 FP/FN regressions."
    )
    parser.add_argument("--run", action="append", default=[], metavar="NAME=DIR")
    parser.add_argument("--targets-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--images-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--scored-file", default="pipeline2_no_peak_scored.json")
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--rule-name", default="center_anchor")
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--pad-x", type=int, default=320)
    parser.add_argument("--pad-y", type=int, default=260)
    parser.add_argument(
        "--show-selected-radius",
        type=float,
        default=90.0,
        help="Draw selected predictions within this x distance from target center.",
    )
    return parser.parse_args()


def parse_runs(values: Iterable[str]) -> list[RunSpec]:
    runs: list[RunSpec] = []
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--run must be NAME=DIR, got: {value}")
        name, root = value.split("=", 1)
        if not name:
            raise SystemExit(f"Empty run name: {value}")
        runs.append(RunSpec(name, Path(root)))
    if not runs:
        raise SystemExit("At least one --run NAME=DIR is required")
    return runs


def parse_page_name(page_name: str) -> tuple[str, str]:
    match = PAGE_NAME_RE.match(page_name)
    if not match:
        raise ValueError(f"Invalid page_name: {page_name}")
    return match.group("score"), f"page_{match.group('page_num')}"


def parse_bbox(value: str) -> Box:
    return normalize_box(json.loads(value))


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
    out: list[ScoredCandidate] = []
    for item in payload:
        if isinstance(item, dict) and "bbox" in item:
            out.append(ScoredCandidate(normalize_box(item["bbox"]), float(item.get("score", 0.0)), item))
        elif isinstance(item, list):
            out.append(ScoredCandidate(normalize_box(item), None, item))
    return out


def selected_boxes(candidates: Sequence[ScoredCandidate], threshold: float) -> list[Box]:
    return [c.bbox for c in candidates if c.score is None or c.score >= threshold]


def choose_candidate(target: Box, candidates: Sequence[ScoredCandidate]) -> ScoredCandidate | None:
    for cand in candidates:
        if cand.bbox == target:
            return cand
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda c: (
            barline_vertical_overlap(target, c.bbox),
            -center_distance_x(target, c.bbox),
            c.score if c.score is not None else 1.0,
        ),
    )


def load_gt_boxes(gt_root: Path, target: Target) -> list[Box]:
    gt_path = gt_root / target.score_name / target.page / "boxes_sorted.json"
    if not gt_path.exists():
        raise FileNotFoundError(f"GT not found: {gt_path}")
    return boxes_from_gt(load_json(gt_path))


def image_candidates(images_root: Path, target: Target) -> list[Path]:
    return [
        images_root / target.score_name / f"{target.page}.png",
        images_root / target.score_name / f"{target.page}.jpg",
        images_root / target.score_name / target.page / "page.png",
        images_root / target.score_name / target.page / "page.jpg",
        images_root / f"{target.page_name}.png",
        images_root / f"{target.page_name}.jpg",
    ]


def load_page_image(images_root: Path, target: Target) -> tuple[Image.Image, Path]:
    for path in image_candidates(images_root, target):
        if path.exists():
            return Image.open(path).convert("RGB"), path
    raise FileNotFoundError(
        "Page image not found. Tried:\n" + "\n".join(str(p) for p in image_candidates(images_root, target))
    )


def crop_bounds(image: Image.Image, box: Box, pad_x: int, pad_y: int) -> Box:
    width, height = image.size
    x1, y1, x2, y2 = box
    return (
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(width, x2 + pad_x),
        min(height, y2 + pad_y),
    )


def translate(box: Box, origin: Box) -> Box:
    ox, oy, _, _ = origin
    return box[0] - ox, box[1] - oy, box[2] - ox, box[3] - oy


def intersects(a: Box, b: Box) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def draw_box(draw: ImageDraw.ImageDraw, box: Box, color: tuple[int, int, int], width: int = 3) -> None:
    for i in range(width):
        draw.rectangle((box[0] - i, box[1] - i, box[2] + i, box[3] + i), outline=color)


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: tuple[int, int, int]) -> None:
    try:
        font = ImageFont.load_default()
    except Exception:  # pragma: no cover
        font = None
    x, y = xy
    bbox = draw.textbbox((x, y), text, font=font)
    draw.rectangle((bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2), fill=COLOR_BACKGROUND)
    draw.text((x, y), text, fill=color, font=font)


def matching_info(target: Box, gt_boxes: Sequence[Box], selected: Sequence[Box], args: argparse.Namespace) -> tuple[int, int]:
    match = greedy_barline_match(
        selected,
        gt_boxes,
        rule_name=args.rule_name,
        vov_threshold=args.vov_threshold,
        xdist_threshold=args.xdist_threshold,
    )
    target_pred_index = next((i for i, b in enumerate(selected) if b == target), None)
    target_gt_index = next((i for i, b in enumerate(gt_boxes) if b == target), None)
    selected_matched = 0
    gt_matched = 0
    for pair in match.matches:
        if target_pred_index is not None and pair.pred_index == target_pred_index:
            selected_matched = 1
        if target_gt_index is not None and pair.gt_index == target_gt_index:
            gt_matched = 1
    return selected_matched, gt_matched


def render_target_run(
    *,
    target: Target,
    run: RunSpec,
    image: Image.Image,
    image_path: Path,
    gt_boxes: Sequence[Box],
    candidates: Sequence[ScoredCandidate],
    args: argparse.Namespace,
    output_dir: Path,
) -> dict[str, Any]:
    selected = selected_boxes(candidates, args.score_threshold)
    candidate = choose_candidate(target.bbox, candidates)
    candidate_score = candidate.score if candidate else None
    candidate_bbox = candidate.bbox if candidate else None
    bounds = crop_bounds(image, target.bbox, args.pad_x, args.pad_y)
    crop = image.crop(bounds)
    draw = ImageDraw.Draw(crop)

    # Draw GT boxes within the crop.
    for gt in gt_boxes:
        if intersects(gt, bounds):
            draw_box(draw, translate(gt, bounds), COLOR_GT, width=2)

    # Draw selected predictions near the target to avoid visual clutter.
    for pred in selected:
        if not intersects(pred, bounds):
            continue
        if center_distance_x(target.bbox, pred) <= args.show_selected_radius:
            draw_box(draw, translate(pred, bounds), COLOR_SELECTED_PRED, width=2)

    # Draw chosen candidate and target last.
    if candidate_bbox is not None and intersects(candidate_bbox, bounds):
        draw_box(draw, translate(candidate_bbox, bounds), COLOR_TARGET_CANDIDATE, width=3)
    draw_box(draw, translate(target.bbox, bounds), COLOR_TARGET, width=4)

    score_text = "n/a" if candidate_score is None else f"{candidate_score:.4f}"
    header = (
        f"{target.target_id} {target.target_kind} | {run.name} | score={score_text} | "
        f"threshold={args.score_threshold}"
    )
    canvas = Image.new("RGB", (crop.width, crop.height + 34), COLOR_HEADER)
    canvas.paste(crop, (0, 34))
    canvas_draw = ImageDraw.Draw(canvas)
    draw_label(canvas_draw, (6, 8), header, COLOR_TEXT)

    out_path = output_dir / f"{target.target_id}_{run.name}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)

    target_selected = int(candidate_score is None or candidate_score >= args.score_threshold) if candidate else 0
    selected_matched, gt_matched = matching_info(target.bbox, gt_boxes, selected, args)
    return {
        "target_id": target.target_id,
        "target_kind": target.target_kind,
        "page_name": target.page_name,
        "run": run.name,
        "image_path": str(image_path),
        "visual_path": str(out_path),
        "score": "" if candidate_score is None else f"{candidate_score:.6f}",
        "selected_at_threshold": target_selected,
        "candidate_bbox": "" if candidate_bbox is None else json.dumps(list(candidate_bbox)),
        "target_selected_matched_to_gt": selected_matched,
        "target_gt_matched_by_selected_pred": gt_matched,
    }


def make_contact_sheet(target: Target, run_rows: Sequence[dict[str, Any]], output_dir: Path) -> Path | None:
    images: list[Image.Image] = []
    for row in run_rows:
        path = Path(str(row["visual_path"]))
        if path.exists():
            images.append(Image.open(path).convert("RGB"))
    if not images:
        return None
    max_height = max(img.height for img in images)
    total_width = sum(img.width for img in images)
    sheet = Image.new("RGB", (total_width, max_height), COLOR_BACKGROUND)
    x = 0
    for img in images:
        sheet.paste(img, (x, 0))
        x += img.width
    out_path = output_dir / f"{target.target_id}_contact_sheet.png"
    sheet.save(out_path)
    return out_path


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_index(path: Path, rows_by_target: dict[str, list[dict[str, Any]]], contact_sheets: dict[str, Path]) -> None:
    lines = ["# Issue #202 visual regression review", ""]
    lines.append("Legend: red=target bbox, green=GT, blue=selected prediction, orange=matched/nearest candidate.")
    lines.append("")
    for target_id, rows in rows_by_target.items():
        lines.append(f"## {target_id}")
        sheet = contact_sheets.get(target_id)
        if sheet:
            lines.append(f"![{target_id}]({sheet.name})")
            lines.append("")
        lines.append("| run | score | selected | matched-to-gt | visual |")
        lines.append("|---|---:|---:|---:|---|")
        for row in rows:
            visual = Path(str(row["visual_path"])).name
            lines.append(
                f"| {row['run']} | {row['score']} | {row['selected_at_threshold']} | "
                f"{row['target_selected_matched_to_gt'] or row['target_gt_matched_by_selected_pred']} | [{visual}]({visual}) |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    runs = parse_runs(args.run)
    targets = read_targets(args.targets_csv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    rows_by_target: dict[str, list[dict[str, Any]]] = {}
    contact_sheets: dict[str, Path] = {}

    for target in targets:
        image, image_path = load_page_image(args.images_root, target)
        gt_boxes = load_gt_boxes(args.gt_root, target)
        target_rows: list[dict[str, Any]] = []
        for run in runs:
            record = PageRecord(target.score_name, target.page)
            scored_path = find_page_file(run.root, record, args.scored_file)
            if scored_path is None:
                raise FileNotFoundError(
                    f"scored file not found for run={run.name} page={target.page_name} under {run.root}"
                )
            candidates = read_scored_candidates(scored_path)
            row = render_target_run(
                target=target,
                run=run,
                image=image,
                image_path=image_path,
                gt_boxes=gt_boxes,
                candidates=candidates,
                args=args,
                output_dir=args.output_dir,
            )
            rows.append(row)
            target_rows.append(row)
        rows_by_target[target.target_id] = target_rows
        sheet = make_contact_sheet(target, target_rows, args.output_dir)
        if sheet:
            contact_sheets[target.target_id] = sheet

    write_csv(args.output_dir / "visual_index.csv", rows)
    write_index(args.output_dir / "visual_review_index.md", rows_by_target, contact_sheets)
    print(f"Wrote {len(rows)} visual rows to {args.output_dir}")


if __name__ == "__main__":
    main()
