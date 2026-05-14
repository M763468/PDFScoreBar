#!/usr/bin/env python3
"""Inspect payload schema differences between Issue #120 Stage-D artifact roots.

This is a lightweight #147 diagnostic.  It samples canonical manifest pages from
one or more artifact roots and reports JSON top-level shape, keys, item keys,
box field usage, and box statistics.  It does not run detection, scoring, or
evaluation.

The immediate use case is to compare the historical local artifact:

    logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12

against regenerated Stage-D roots such as:

    logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline

Outputs are diagnostics under ignored logs/ paths and should not be committed.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue120.eval_full68_from_intermediates import PageRecord, find_page_file, iter_manifest  # noqa: E402


DEFAULT_FILENAMES = (
    "pipeline2_no_peak_candidates.json",
    "pipeline2_no_peak_scored.json",
    "pipeline2_no_peak_filtered_cnn.json",
    "bars.json",
    "barlines.json",
    "predictions.json",
)


@dataclass(frozen=True)
class SchemaRow:
    label: str
    score: str
    page: str
    path: str | None
    exists: bool
    top_type: str | None
    top_keys: str | None
    item_count: int | None
    item_type_counts: str | None
    item_keys: str | None
    box_field_counts: str | None
    scored_item_count: int | None
    score_key_count: int | None
    median_w: float | None
    median_h: float | None
    min_y: float | None
    max_y: float | None


def load_json(path: Path | None) -> Any | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve(root: Path, record: PageRecord, filenames: Iterable[str]) -> Path | None:
    for filename in filenames:
        found = find_page_file(root, record, filename)
        if found is not None:
            return found
    return None


def payload_items(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        for key in ("predictions", "bars", "barlines", "items", "candidates"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []
    if isinstance(payload, list):
        return payload
    return []


def normalize_box(item: Any) -> tuple[float, float, float, float] | None:
    box = item
    if isinstance(item, dict):
        for key in ("bbox", "barline_location", "orig_bbox", "box"):
            value = item.get(key)
            if isinstance(value, list):
                box = value
                break
        else:
            return None
    if not isinstance(box, list) or len(box) < 4:
        return None
    try:
        return tuple(float(v) for v in box[:4])  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def box_field(item: Any) -> str | None:
    if isinstance(item, list) and len(item) >= 4:
        return "list"
    if isinstance(item, dict):
        for key in ("bbox", "barline_location", "orig_bbox", "box"):
            if isinstance(item.get(key), list):
                return key
    return None


def summarize_keys(keys: Iterable[str], *, limit: int) -> str:
    values = sorted(set(keys))[:limit]
    return ",".join(values)


def inspect_one(label: str, root: Path, record: PageRecord, filenames: Iterable[str]) -> SchemaRow:
    path = resolve(root, record, filenames)
    payload = load_json(path)
    if payload is None:
        return SchemaRow(
            label=label,
            score=record.score,
            page=record.page,
            path=str(path) if path else None,
            exists=False,
            top_type=None,
            top_keys=None,
            item_count=None,
            item_type_counts=None,
            item_keys=None,
            box_field_counts=None,
            scored_item_count=None,
            score_key_count=None,
            median_w=None,
            median_h=None,
            min_y=None,
            max_y=None,
        )

    items = payload_items(payload)
    type_counts = Counter(type(item).__name__ for item in items)
    key_counter: Counter[str] = Counter()
    box_counter: Counter[str] = Counter()
    score_key_count = 0
    boxes: list[tuple[float, float, float, float]] = []
    for item in items:
        if isinstance(item, dict):
            key_counter.update(str(key) for key in item.keys())
            if "score" in item:
                score_key_count += 1
        field = box_field(item)
        if field is not None:
            box_counter[field] += 1
        box = normalize_box(item)
        if box is not None:
            boxes.append(box)

    widths = [abs(box[2] - box[0]) for box in boxes]
    heights = [abs(box[3] - box[1]) for box in boxes]
    ys = [value for box in boxes for value in (box[1], box[3])]
    top_keys = None
    if isinstance(payload, dict):
        top_keys = summarize_keys((str(key) for key in payload.keys()), limit=40)

    return SchemaRow(
        label=label,
        score=record.score,
        page=record.page,
        path=str(path) if path else None,
        exists=True,
        top_type=type(payload).__name__,
        top_keys=top_keys,
        item_count=len(items),
        item_type_counts=json.dumps(dict(sorted(type_counts.items())), sort_keys=True),
        item_keys=summarize_keys(key_counter.keys(), limit=40) if key_counter else None,
        box_field_counts=json.dumps(dict(sorted(box_counter.items())), sort_keys=True),
        scored_item_count=score_key_count,
        score_key_count=score_key_count,
        median_w=statistics.median(widths) if widths else None,
        median_h=statistics.median(heights) if heights else None,
        min_y=min(ys) if ys else None,
        max_y=max(ys) if ys else None,
    )


def write_csv(rows: list[SchemaRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def render_markdown(rows: list[SchemaRow], args: argparse.Namespace) -> str:
    lines = [
        "# Issue 120 Stage-D payload schema inspection",
        "",
        "## Roots",
        "",
    ]
    for label, root in args.root:
        lines.append(f"- `{label}`: `{root}`")
    lines.extend(
        [
            "",
            f"Filenames: `{', '.join(args.filenames)}`",
            "",
            "## Summary by root",
            "",
            "| label | resolved | missing | median item count | median width | median height | scored items | box fields | item keys |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )

    by_label: dict[str, list[SchemaRow]] = {}
    for row in rows:
        by_label.setdefault(row.label, []).append(row)
    for label, label_rows in by_label.items():
        resolved = [row for row in label_rows if row.exists]
        counts = [row.item_count for row in resolved if row.item_count is not None]
        widths = [row.median_w for row in resolved if row.median_w is not None]
        heights = [row.median_h for row in resolved if row.median_h is not None]
        scored = sum(row.score_key_count or 0 for row in resolved)
        box_fields = Counter(row.box_field_counts or "" for row in resolved)
        item_keys = Counter(row.item_keys or "" for row in resolved)
        lines.append(
            "| "
            f"{label} | {len(resolved)} | {len(label_rows) - len(resolved)} | "
            f"{statistics.median(counts) if counts else ''} | "
            f"{statistics.median(widths) if widths else ''} | "
            f"{statistics.median(heights) if heights else ''} | "
            f"{scored} | {box_fields.most_common(1)[0][0] if box_fields else ''} | "
            f"{item_keys.most_common(1)[0][0] if item_keys else ''} |"
        )

    lines.extend(
        [
            "",
            "## Sampled pages",
            "",
            "| label | score | page | count | top type | top keys | item keys | box fields | score keys | median w | median h |",
            "| --- | --- | --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    sample_rows = rows[: args.limit * len(args.root)]
    for row in sample_rows:
        lines.append(
            "| "
            f"{row.label} | {row.score} | {row.page} | {row.item_count} | "
            f"{row.top_type} | {row.top_keys or ''} | {row.item_keys or ''} | "
            f"{row.box_field_counts or ''} | {row.score_key_count} | "
            f"{'' if row.median_w is None else f'{row.median_w:.1f}'} | "
            f"{'' if row.median_h is None else f'{row.median_h:.1f}'} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation guide",
            "",
            "- A root with list payloads and no `score` keys is candidate/box-like, not CNN-scored evidence.",
            "- A root with dict items containing `bbox` and `score` is scored candidate evidence.",
            "- Large item-count differences with similar schema suggest generation density drift.",
            "- Different item keys or box fields suggest a file-family/schema mismatch before geometry analysis.",
        ]
    )
    return "\n".join(lines)


def parse_root(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--root must be LABEL=PATH")
    label, path = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("--root label must be non-empty")
    return label, Path(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=parse_root,
        action="append",
        required=True,
        help="Artifact root as LABEL=PATH. Can be repeated.",
    )
    parser.add_argument("--filenames", nargs="+", default=list(DEFAULT_FILENAMES))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_d_payload_schema"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows: list[SchemaRow] = []
    for record in iter_manifest():
        for label, root in args.root:
            rows.append(inspect_one(label, root, record, args.filenames))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "stage_d_payload_schema.csv")
    markdown = render_markdown(rows, args)
    (args.output_dir / "stage_d_payload_schema.md").write_text(markdown + "\n", encoding="utf-8")
    print(markdown)
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
