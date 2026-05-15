#!/usr/bin/env python3
"""Compare Issue #120 box-tree statistics page by page.

This is a lightweight local diagnostic for Stage D.  It compares two directory
trees that contain canonical Issue #120 page files and reports simple geometry
statistics.  It does not run detection, scoring, or evaluation.

Typical comparisons:

1. Golden Baseline fixture vs regenerated Stage-D bands_from candidate:

   PYTHONPATH=. python3 tools/issue120/compare_box_tree_stats.py \
     --left data/evaluation2/golden_baseline_eval2_bc23deb \
     --right logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate

2. Historical local scoring_input_eval2_v12 vs regenerated Stage-D bands_from candidate:

   PYTHONPATH=. python3 tools/issue120/compare_box_tree_stats.py \
     --left logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
     --right logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue120.eval_full68_from_intermediates import PageRecord, find_page_file, iter_manifest  # noqa: E402


@dataclass(frozen=True)
class BoxStats:
    count: int
    min_x: float | None
    max_x: float | None
    median_cx: float | None
    median_cy: float | None
    median_w: float | None
    median_h: float | None
    p10_h: float | None
    p90_h: float | None


@dataclass(frozen=True)
class PageComparison:
    score: str
    page: str
    left_path: str | None
    right_path: str | None
    left_count: int | None
    right_count: int | None
    count_delta: int | None
    count_ratio: float | None
    left_median_h: float | None
    right_median_h: float | None
    median_h_delta: float | None
    left_median_w: float | None
    right_median_w: float | None
    median_w_delta: float | None
    left_median_cx: float | None
    right_median_cx: float | None
    median_cx_delta: float | None
    left_median_cy: float | None
    right_median_cy: float | None
    median_cy_delta: float | None


def normalize_box(box: Any) -> tuple[float, float, float, float] | None:
    if isinstance(box, dict):
        if "bbox" in box:
            box = box["bbox"]
        elif "barline_location" in box:
            box = box["barline_location"]
        elif "orig_bbox" in box:
            box = box["orig_bbox"]
        else:
            return None
    if not isinstance(box, list) or len(box) < 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in box[:4]]
    except (TypeError, ValueError):
        return None
    return (x1, y1, x2, y2)


def boxes_from_payload(payload: Any) -> list[tuple[float, float, float, float]]:
    if isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
        source = payload["predictions"]
    elif isinstance(payload, list):
        source = payload
    else:
        return []
    boxes: list[tuple[float, float, float, float]] = []
    for item in source:
        box = normalize_box(item)
        if box is not None:
            boxes.append(box)
    return boxes


def load_boxes(path: Path | None) -> list[tuple[float, float, float, float]] | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return boxes_from_payload(payload)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * q
    lo = int(index)
    hi = min(lo + 1, len(ordered) - 1)
    frac = index - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def stats(boxes: list[tuple[float, float, float, float]] | None) -> BoxStats | None:
    if boxes is None:
        return None
    if not boxes:
        return BoxStats(0, None, None, None, None, None, None, None, None)
    xs = [v for b in boxes for v in (b[0], b[2])]
    cxs = [(b[0] + b[2]) / 2.0 for b in boxes]
    cys = [(b[1] + b[3]) / 2.0 for b in boxes]
    ws = [abs(b[2] - b[0]) for b in boxes]
    hs = [abs(b[3] - b[1]) for b in boxes]
    return BoxStats(
        count=len(boxes),
        min_x=min(xs),
        max_x=max(xs),
        median_cx=statistics.median(cxs),
        median_cy=statistics.median(cys),
        median_w=statistics.median(ws),
        median_h=statistics.median(hs),
        p10_h=percentile(hs, 0.10),
        p90_h=percentile(hs, 0.90),
    )


def safe_delta(left: float | int | None, right: float | int | None) -> float | None:
    if left is None or right is None:
        return None
    return float(right) - float(left)


def safe_ratio(right: int | None, left: int | None) -> float | None:
    if right is None or left is None or left == 0:
        return None
    return right / left


def resolve_page_file(root: Path, record: PageRecord, filenames: Iterable[str]) -> Path | None:
    for filename in filenames:
        found = find_page_file(root, record, filename)
        if found is not None:
            return found
    return None


def compare(args: argparse.Namespace) -> list[PageComparison]:
    rows: list[PageComparison] = []
    for record in iter_manifest():
        left_path = resolve_page_file(args.left, record, args.left_filenames)
        right_path = resolve_page_file(args.right, record, args.right_filenames)
        left_stats = stats(load_boxes(left_path))
        right_stats = stats(load_boxes(right_path))

        left_count = left_stats.count if left_stats is not None else None
        right_count = right_stats.count if right_stats is not None else None
        rows.append(
            PageComparison(
                score=record.score,
                page=record.page,
                left_path=str(left_path) if left_path else None,
                right_path=str(right_path) if right_path else None,
                left_count=left_count,
                right_count=right_count,
                count_delta=None if left_count is None or right_count is None else right_count - left_count,
                count_ratio=safe_ratio(right_count, left_count),
                left_median_h=left_stats.median_h if left_stats else None,
                right_median_h=right_stats.median_h if right_stats else None,
                median_h_delta=safe_delta(
                    left_stats.median_h if left_stats else None,
                    right_stats.median_h if right_stats else None,
                ),
                left_median_w=left_stats.median_w if left_stats else None,
                right_median_w=right_stats.median_w if right_stats else None,
                median_w_delta=safe_delta(
                    left_stats.median_w if left_stats else None,
                    right_stats.median_w if right_stats else None,
                ),
                left_median_cx=left_stats.median_cx if left_stats else None,
                right_median_cx=right_stats.median_cx if right_stats else None,
                median_cx_delta=safe_delta(
                    left_stats.median_cx if left_stats else None,
                    right_stats.median_cx if right_stats else None,
                ),
                left_median_cy=left_stats.median_cy if left_stats else None,
                right_median_cy=right_stats.median_cy if right_stats else None,
                median_cy_delta=safe_delta(
                    left_stats.median_cy if left_stats else None,
                    right_stats.median_cy if right_stats else None,
                ),
            )
        )
    return rows


def count_loss_rank(row: PageComparison) -> tuple[int, float, int]:
    if row.left_count is None or row.right_count is None:
        return (0, 0.0, 0)
    if row.left_count > 0 and row.right_count == 0:
        return (1, 0.0, -row.left_count)
    if row.count_ratio is None:
        return (2, 1.0, 0)
    return (2, row.count_ratio, -abs(row.count_delta or 0))


def render_markdown(rows: list[PageComparison], args: argparse.Namespace) -> str:
    by_count_loss = sorted(rows, key=count_loss_rank)[: args.limit]
    by_height_delta = sorted(
        rows,
        key=lambda r: abs(r.median_h_delta) if r.median_h_delta is not None else -1.0,
        reverse=True,
    )[: args.limit]
    by_width_delta = sorted(
        rows,
        key=lambda r: abs(r.median_w_delta) if r.median_w_delta is not None else -1.0,
        reverse=True,
    )[: args.limit]

    lines = [
        "# Issue 120 box-tree statistics comparison",
        "",
        f"Left: `{args.left}`",
        f"Right: `{args.right}`",
        "",
    ]

    def table(title: str, items: list[PageComparison]) -> None:
        lines.extend(
            [
                f"## {title}",
                "",
                "| score | page | left count | right count | ratio | median h delta | median w delta | median cx delta | median cy delta |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in items:
            ratio = "" if row.count_ratio is None else f"{row.count_ratio:.3f}"
            h_delta = "" if row.median_h_delta is None else f"{row.median_h_delta:.1f}"
            w_delta = "" if row.median_w_delta is None else f"{row.median_w_delta:.1f}"
            cx_delta = "" if row.median_cx_delta is None else f"{row.median_cx_delta:.1f}"
            cy_delta = "" if row.median_cy_delta is None else f"{row.median_cy_delta:.1f}"
            lines.append(
                f"| {row.score} | {row.page} | {row.left_count} | {row.right_count} | {ratio} | "
                f"{h_delta} | {w_delta} | {cx_delta} | {cy_delta} |"
            )
        lines.append("")

    table("Largest count loss", by_count_loss)
    table("Largest median-height deltas", by_height_delta)
    table("Largest median-width deltas", by_width_delta)
    return "\n".join(lines)


def write_csv(rows: list[PageComparison], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def permission_error_message(exc: PermissionError, output_dir: Path) -> str:
    return (
        f"Permission denied while writing Stage-D box-tree outputs under: {output_dir}\n"
        "This usually happens when the output directory was previously created by sudo/root.\n"
        "Use a new --output-dir or fix ownership before rerunning, for example:\n\n"
        f"  sudo chown -R $USER:$USER {output_dir}\n\n"
        f"Original error: {exc}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument(
        "--left-filenames",
        nargs="+",
        default=["pipeline2_no_peak_candidates.json", "pipeline2_no_peak_scored.json"],
    )
    parser.add_argument(
        "--right-filenames",
        nargs="+",
        default=["pipeline2_no_peak_candidates.json", "pipeline2_no_peak_scored.json"],
    )
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_d_box_tree_stats"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = compare(args)
    markdown = render_markdown(rows, args)
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_csv(rows, args.output_dir / "box_tree_stats_comparison.csv")
        (args.output_dir / "box_tree_stats_comparison.md").write_text(markdown + "\n", encoding="utf-8")
    except PermissionError as exc:
        raise SystemExit(permission_error_message(exc, args.output_dir)) from exc
    print(markdown)
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
