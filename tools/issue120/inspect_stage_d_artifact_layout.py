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

from tools.issue120.eval_full68_from_intermediates import (  # noqa: E402
    PageRecord,
    find_page_file,
    iter_manifest,
)

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
    filename: str | None
    status: str
    top_level_type: str | None
    item_count: int | None
    keys: str | None
    box_like_count: int | None


@dataclass(frozen=True)
class ResolvedPair:
    filename: str | None
    historical_path: Path | None
    regenerated_path: Path | None
    comparable_artifact: bool


@dataclass(frozen=True)
class PageLayoutRow:
    score: str
    page: str
    artifact_filename: str | None
    comparable_artifact: bool
    historical_path: str | None
    regenerated_path: str | None
    historical_exists: bool
    regenerated_exists: bool
    historical_status: str
    regenerated_status: str
    historical_item_count: int | None
    regenerated_item_count: int | None
    historical_box_like_count: int | None
    regenerated_box_like_count: int | None
    count_delta: int | None
    box_like_delta: int | None
    historical_keys: str | None
    regenerated_keys: str | None


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        return {"__error__": "JSON_DECODE_ERROR", "message": str(exc)}
    except OSError as exc:
        return {"__error__": "READ_ERROR", "message": str(exc)}


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


def shape(path: Path | None, filename: str | None) -> FileShape:
    if path is None or not path.exists():
        return FileShape(
            False, str(path) if path else None, filename, "MISSING", None, None, None, None
        )
    payload = load_json(path)
    if isinstance(payload, dict) and payload.get("__error__"):
        return FileShape(
            exists=False,
            path=str(path),
            filename=filename,
            status=str(payload["__error__"]),
            top_level_type=None,
            item_count=None,
            keys=None,
            box_like_count=None,
        )
    top_type = type(payload).__name__
    keys = None
    if isinstance(payload, dict):
        keys = ",".join(sorted(str(k) for k in payload.keys())[:30])
    items = payload_items(payload)
    box_like_count = sum(1 for item in items if normalize_box(item) is not None)
    return FileShape(
        exists=True,
        path=str(path),
        filename=filename,
        status="OK",
        top_level_type=top_type,
        item_count=len(items),
        keys=keys,
        box_like_count=box_like_count,
    )


def resolve_filename(root: Path, record: PageRecord, filename: str) -> Path | None:
    return find_page_file(root, record, filename)


def resolve_pair(
    historical_root: Path,
    regenerated_root: Path,
    record: PageRecord,
    filenames: Iterable[str],
) -> ResolvedPair:
    first_historical: tuple[str, Path] | None = None
    first_regenerated: tuple[str, Path] | None = None
    for filename in filenames:
        historical_path = resolve_filename(historical_root, record, filename)
        regenerated_path = resolve_filename(regenerated_root, record, filename)
        if historical_path is not None and first_historical is None:
            first_historical = (filename, historical_path)
        if regenerated_path is not None and first_regenerated is None:
            first_regenerated = (filename, regenerated_path)
        if historical_path is not None and regenerated_path is not None:
            return ResolvedPair(filename, historical_path, regenerated_path, True)
    historical_path = first_historical[1] if first_historical else None
    regenerated_path = first_regenerated[1] if first_regenerated else None
    filename = (
        first_historical[0]
        if first_historical
        else (first_regenerated[0] if first_regenerated else None)
    )
    return ResolvedPair(filename, historical_path, regenerated_path, False)


def safe_delta(left: int | None, right: int | None, comparable: bool) -> int | None:
    if not comparable or left is None or right is None:
        return None
    return right - left


def inspect_layout(args: argparse.Namespace) -> list[PageLayoutRow]:
    rows: list[PageLayoutRow] = []
    for record in iter_manifest():
        pair = resolve_pair(args.historical, args.regenerated, record, args.filenames)
        historical_shape = shape(pair.historical_path, pair.filename)
        regenerated_shape = shape(pair.regenerated_path, pair.filename)
        comparable = (
            pair.comparable_artifact and historical_shape.exists and regenerated_shape.exists
        )
        rows.append(
            PageLayoutRow(
                score=record.score,
                page=record.page,
                artifact_filename=pair.filename,
                comparable_artifact=comparable,
                historical_path=historical_shape.path,
                regenerated_path=regenerated_shape.path,
                historical_exists=historical_shape.exists,
                regenerated_exists=regenerated_shape.exists,
                historical_status=historical_shape.status,
                regenerated_status=regenerated_shape.status,
                historical_item_count=historical_shape.item_count,
                regenerated_item_count=regenerated_shape.item_count,
                historical_box_like_count=historical_shape.box_like_count,
                regenerated_box_like_count=regenerated_shape.box_like_count,
                count_delta=safe_delta(
                    historical_shape.item_count, regenerated_shape.item_count, comparable
                ),
                box_like_delta=safe_delta(
                    historical_shape.box_like_count,
                    regenerated_shape.box_like_count,
                    comparable,
                ),
                historical_keys=historical_shape.keys,
                regenerated_keys=regenerated_shape.keys,
            )
        )
    return rows


def write_csv(rows: list[PageLayoutRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def render_markdown(rows: list[PageLayoutRow], args: argparse.Namespace) -> str:
    missing_historical = [row for row in rows if not row.historical_exists]
    missing_regenerated = [row for row in rows if not row.regenerated_exists]
    incomparable = [row for row in rows if not row.comparable_artifact]
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
        f"historical_missing_or_unreadable={len(missing_historical)}",
        f"regenerated_resolved={len(rows) - len(missing_regenerated)}",
        f"regenerated_missing_or_unreadable={len(missing_regenerated)}",
        f"incomparable_artifact_pages={len(incomparable)}",
        "```",
        "",
    ]

    def table(title: str, items: list[PageLayoutRow]) -> None:
        lines.extend(
            [
                f"## {title}",
                "",
                "| score | page | filename | comparable | historical status | regenerated status | historical count | regenerated count | count delta | historical boxes | regenerated boxes | box delta |",
                "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in items:
            lines.append(
                f"| {row.score} | {row.page} | {row.artifact_filename} | {row.comparable_artifact} | "
                f"{row.historical_status} | {row.regenerated_status} | "
                f"{row.historical_item_count} | {row.regenerated_item_count} | {row.count_delta} | "
                f"{row.historical_box_like_count} | {row.regenerated_box_like_count} | {row.box_like_delta} |"
            )
        lines.append("")

    table("Largest box-like count deltas", box_delta_rows)
    table("Largest item-count deltas", count_delta_rows)

    if incomparable:
        lines.extend(["## Incomparable artifact pages", ""])
        for row in incomparable[: args.limit]:
            lines.append(
                f"- `{row.score}/{row.page}` filename=`{row.artifact_filename}` "
                f"historical=`{row.historical_status}` regenerated=`{row.regenerated_status}`"
            )
        lines.append("")
    if missing_historical:
        lines.extend(["## Missing or unreadable historical pages", ""])
        for row in missing_historical[: args.limit]:
            lines.append(
                f"- `{row.score}/{row.page}` status=`{row.historical_status}` path=`{row.historical_path}`"
            )
        lines.append("")
    if missing_regenerated:
        lines.extend(["## Missing or unreadable regenerated pages", ""])
        for row in missing_regenerated[: args.limit]:
            lines.append(
                f"- `{row.score}/{row.page}` status=`{row.regenerated_status}` path=`{row.regenerated_path}`"
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation guide",
            "",
            "- Missing historical pages mean the local `scoring_input_eval2_v12` artifact is absent, unreadable, malformed, or not in the expected score/page tree shape.",
            "- Missing regenerated pages mean Stage-D composition did not produce a readable page file for that manifest entry.",
            "- Count deltas are only computed when both roots resolve the same artifact filename for a page.",
            "- Use `compare_box_tree_stats.py` for geometry statistics and the Stage-C verifier for detector metrics.",
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


def write_reports(rows: list[PageLayoutRow], args: argparse.Namespace) -> str:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "stage_d_artifact_layout.csv")
    markdown = render_markdown(rows, args)
    (args.output_dir / "stage_d_artifact_layout.md").write_text(markdown + "\n", encoding="utf-8")
    return markdown


def main() -> None:
    args = build_parser().parse_args()
    rows = inspect_layout(args)
    try:
        markdown = write_reports(rows, args)
    except PermissionError as exc:
        print(
            f"Permission denied while writing reports under {args.output_dir}: {exc}",
            file=sys.stderr,
        )
        print(
            "Fix ownership or choose a different --output-dir, for example: "
            f"sudo chown -R $(id -u):$(id -g) {args.output_dir}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(markdown)
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
