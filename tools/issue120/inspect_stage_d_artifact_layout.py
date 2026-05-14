#!/usr/bin/env python3
"""Inspect Issue #120 Stage-D historical and regenerated artifact layouts.

This helper is intentionally lightweight.  It does not run HOMR/SR/OMR,
probe scan, CNN scoring, or evaluation.  It inspects local/generated directory
trees and reports whether the canonical 68-page manifest can resolve expected
per-page files from each artifact root.

Typical use:

    PYTHONPATH=. python3 tools/issue120/inspect_stage_d_artifact_layout.py \
      --historical logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
      --regenerated logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline

The outputs belong under ignored logs/ paths and should not be committed.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue120.eval_full68_from_intermediates import PageRecord, find_page_file, iter_manifest  # noqa: E402


DEFAULT_HISTORICAL_ROOT = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
)
DEFAULT_REGENERATED_ROOT = Path(
    "logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline"
)
DEFAULT_OUTPUT_DIR = Path("logs/issue120_e2e_recovery/stage_d_artifact_layout")
DEFAULT_FILENAMES = (
    "pipeline2_no_peak_candidates.json",
    "pipeline2_no_peak_filtered_cnn.json",
    "pipeline2_no_peak_scored.json",
    "bars.json",
    "barlines.json",
)


@dataclass(frozen=True)
class FileShape:
    exists: bool
    path: str | None
    top_level_type: str | None
    item_count: int | None
    keys: str | None
    box_like_count: int | None


@dataclass(frozen=True)
class PageLayoutRow:
    score: str
    page: str
    historical_path: str | None
    regenerated_path: str | None
    historical_exists: bool
    regenerated_exists: bool
    historical_item_count: int | None
    regenerated_item_count: int | None
    historical_box_like_count: int | None
    regenerated_box_like_count: int | None
    count_delta: int | None
    box_like_delta: int | None
    historical_keys: str | None
    regenerated_keys: str | None


def load_json(path: Path) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return {"__decode_error__": True}


def normalize_box(item: Any) -> tuple[float, float, float, float] | None:
    if isinstance(item, dict):
        if "bbox" in item:
            item = item["bbox"]
        elif "barline_location" in item:
            item = item["barline_location"]
        elif "orig_bbox" in item:
            item = item["orig_bbox"]
        else:
            return None
    if not isinstance(item, list) or len(item) < 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in item[:4]]
    except (TypeError, ValueError):
        return None
    return (x1, y1, x2, y2)


def payload_items(payload: Any) -> list[Any]:
    if isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
        return payload["predictions"]
    if isinstance(payload, dict) and isinstance(payload.get("bars"), list):
        return payload["bars"]
    if isinstance(payload, dict) and isinstance(payload.get("barlines"), list):
        return payload["barlines"]
    if isinstance(payload, list):
        return payload
    return []


def shape(path: Path | None) -> FileShape:
    if path is None or not path.exists():
        return FileShape(False, str(path) if path else None, None, None, None, None)
    payload = load_json(path)
    top_type = type(payload).__name__
    keys = None
    if isinstance(payload, dict):
        keys = ",".join(sorted(str(k) for k in payload.keys())[:30])
    items = payload_items(payload)
    box_like_count = sum(1 for item in items if normalize_box(item) is not None)
    return FileShape(
        exists=True,
        path=str(path),
        top_level_type=top_type,
        item_count=len(items),
        keys=keys,
        box_like_count=box_like_count,
    )


def resolve(root: Path, record: PageRecord, filenames: Iterable[str]) -> Path | None:
    for filename in filenames:
        found = find_page_file(root, record, filename)
        if found is not None:
            return found
    return None


def safe_delta(left: int | None, right: int | None) -> int | None:
    if left is None or right is None:
        return None
    return right - left


def inspect_layout(args: argparse.Namespace) -> list[PageLayoutRow]:
    rows: list[PageLayoutRow] = []
    for record in iter_manifest():
        historical_path = resolve(args.historical, record, args.filenames)
        regenerated_path = resolve(args.regenerated, record, args.filenames)
        historical_shape = shape(historical_path)
        regenerated_shape = shape(regenerated_path)
        rows.append(
            PageLayoutRow(
                score=record.score,
                page=record.page,
                historical_path=historical_shape.path,
                regenerated_path=regenerated_shape.path,
                historical_exists=historical_shape.exists,
                regenerated_exists=regenerated_shape.exists,
                historical_item_count=historical_shape.item_count,
                regenerated_item_count=regenerated_shape.item_count,
                historical_box_like_count=historical_shape.box_like_count,
                regenerated_box_like_count=regenerated_shape.box_like_count,
                count_delta=safe_delta(historical_shape.item_count, regenerated_shape.item_count),
                box_like_delta=safe_delta(historical_shape.box_like_count, regenerated_shape.box_like_count),
                historical_keys=historical_shape.keys,
                regenerated_keys=regenerated_shape.keys,
            )
        )
    return rows


def write_csv(rows: list[PageLayoutRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def render_markdown(rows: list[PageLayoutRow], args: argparse.Namespace) -> str:
    missing_historical = [row for row in rows if not row.historical_exists]
    missing_regenerated = [row for row in rows if not row.regenerated_exists]
    box_delta_rows = sorted(
        rows,
        key=lambda row: abs(row.box_like_delta) if row.box_like_delta is not None else -1,
        reverse=True,
    )[: args.limit]
    count_delta_rows = sorted(
        rows,
        key=lambda row: abs(row.count_delta) if row.count_delta is not None else -1,
        reverse=True,
    )[: args.limit]

    lines = [
        "# Issue 120 Stage-D artifact layout inspection",
        "",
        f"Historical root: `{args.historical}`",
        f"Regenerated root: `{args.regenerated}`",
        f"Filenames: `{', '.join(args.filenames)}`",
        "",
        "## Summary",
        "",
        "```text",
        f"manifest_pages={len(rows)}",
        f"historical_resolved={len(rows) - len(missing_historical)}",
        f"historical_missing={len(missing_historical)}",
        f"regenerated_resolved={len(rows) - len(missing_regenerated)}",
        f"regenerated_missing={len(missing_regenerated)}",
        "```",
        "",
    ]

    def table(title: str, items: list[PageLayoutRow]) -> None:
        lines.extend(
            [
                f"## {title}",
                "",
                "| score | page | historical count | regenerated count | count delta | historical boxes | regenerated boxes | box delta |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in items:
            lines.append(
                f"| {row.score} | {row.page} | {row.historical_item_count} | "
                f"{row.regenerated_item_count} | {row.count_delta} | "
                f"{row.historical_box_like_count} | {row.regenerated_box_like_count} | {row.box_like_delta} |"
            )
        lines.append("")

    table("Largest box-like count deltas", box_delta_rows)
    table("Largest item-count deltas", count_delta_rows)

    if missing_historical:
        lines.extend(["## Missing historical pages", ""])
        for row in missing_historical[: args.limit]:
            lines.append(f"- `{row.score}/{row.page}`")
        lines.append("")
    if missing_regenerated:
        lines.extend(["## Missing regenerated pages", ""])
        for row in missing_regenerated[: args.limit]:
            lines.append(f"- `{row.score}/{row.page}`")
        lines.append("")

    lines.extend(
        [
            "## Interpretation guide",
            "",
            "- Missing historical pages mean the local `scoring_input_eval2_v12` artifact is absent or not in the expected score/page tree shape.",
            "- Missing regenerated pages mean Stage-D composition did not produce a page file for that manifest entry.",
            "- Count deltas are structural signals only; use `compare_box_tree_stats.py` for geometry statistics and the Stage-C verifier for detector metrics.",
            "- This report does not alter detector, scoring, NMS, or full-pipeline behavior.",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, default=DEFAULT_HISTORICAL_ROOT)
    parser.add_argument("--regenerated", type=Path, default=DEFAULT_REGENERATED_ROOT)
    parser.add_argument("--filenames", nargs="+", default=list(DEFAULT_FILENAMES))
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = inspect_layout(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "stage_d_artifact_layout.csv")
    markdown = render_markdown(rows, args)
    (args.output_dir / "stage_d_artifact_layout.md").write_text(markdown + "\n", encoding="utf-8")
    print(markdown)
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
