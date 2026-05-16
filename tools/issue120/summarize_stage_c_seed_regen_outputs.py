#!/usr/bin/env python3
"""Summarize Issue #120 Stage-C/Stage-D dense-seed regeneration outputs.

This #147 diagnostic compares the known historical dense candidate root with a
newly regenerated reproduce_clean_seed_v12.py output tree.  It also inspects the
intermediate consensus seed and raw probe-scan candidate files written by
reproduce_clean_seed_v12.py.

It does not run CNN scoring or evaluation.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools.issue120.eval_full68_from_intermediates import find_page_file, iter_manifest

DEFAULT_HISTORICAL_ROOT = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
)
DEFAULT_REGEN_ROOT = Path("logs/issue120_e2e_recovery/stage_d_issue36_repro")
DEFAULT_OUTPUT_DIR = Path("logs/issue120_e2e_recovery/stage_d_issue36_repro_diagnostics")


@dataclass(frozen=True)
class PageSeedRegenRow:
    score: str
    page: str
    historical_count: int | None
    consensus_seed_count: int | None
    raw_probe_count: int | None
    final_filtered_count: int | None
    raw_minus_historical: int | None
    final_minus_historical: int | None
    final_to_historical_ratio: float | None
    historical_path: str | None
    consensus_seed_path: str | None
    raw_probe_path: str | None
    final_filtered_path: str | None


def load_count(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("predictions", "bars", "barlines", "items", "candidates"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def safe_delta(left: int | None, right: int | None) -> int | None:
    if left is None or right is None:
        return None
    return right - left


def safe_ratio(right: int | None, left: int | None) -> float | None:
    if right is None or left is None or left == 0:
        return None
    return right / left


def build_rows(args: argparse.Namespace) -> list[PageSeedRegenRow]:
    rows: list[PageSeedRegenRow] = []
    final_root = args.regen_root / "probe_candidates_filtered_v12"
    for record in iter_manifest():
        historical_path = find_page_file(
            args.historical_root,
            record,
            "pipeline2_no_peak_candidates.json",
        )
        page_dir = args.regen_root / record.score / record.page
        consensus_path = page_dir / f"{record.page}.json"
        raw_probe_path = (
            page_dir / f"eval2_{record.score}_{record.page}" / "pipeline2_no_peak_candidates.json"
        )
        final_filtered_path = find_page_file(
            final_root,
            record,
            "pipeline2_no_peak_candidates.json",
        )
        historical_count = load_count(historical_path)
        consensus_count = load_count(consensus_path)
        raw_count = load_count(raw_probe_path)
        final_count = load_count(final_filtered_path)
        rows.append(
            PageSeedRegenRow(
                score=record.score,
                page=record.page,
                historical_count=historical_count,
                consensus_seed_count=consensus_count,
                raw_probe_count=raw_count,
                final_filtered_count=final_count,
                raw_minus_historical=safe_delta(historical_count, raw_count),
                final_minus_historical=safe_delta(historical_count, final_count),
                final_to_historical_ratio=safe_ratio(final_count, historical_count),
                historical_path=str(historical_path) if historical_path else None,
                consensus_seed_path=str(consensus_path) if consensus_path.exists() else None,
                raw_probe_path=str(raw_probe_path) if raw_probe_path.exists() else None,
                final_filtered_path=str(final_filtered_path) if final_filtered_path else None,
            )
        )
    return rows


def write_csv(rows: list[PageSeedRegenRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def render_markdown(rows: list[PageSeedRegenRow], args: argparse.Namespace) -> str:
    historical_total = sum(row.historical_count or 0 for row in rows)
    consensus_total = sum(row.consensus_seed_count or 0 for row in rows)
    raw_total = sum(row.raw_probe_count or 0 for row in rows)
    final_total = sum(row.final_filtered_count or 0 for row in rows)
    missing_consensus = [row for row in rows if row.consensus_seed_count is None]
    missing_raw = [row for row in rows if row.raw_probe_count is None]
    missing_final = [row for row in rows if row.final_filtered_count is None]
    empty_final = [row for row in rows if row.final_filtered_count == 0]

    by_final_loss = sorted(
        rows,
        key=lambda row: (
            row.final_to_historical_ratio if row.final_to_historical_ratio is not None else -1.0
        ),
    )[: args.limit]
    by_raw_loss = sorted(
        rows,
        key=lambda row: (
            row.raw_minus_historical if row.raw_minus_historical is not None else -(10**9)
        ),
    )[: args.limit]

    lines = [
        "# Issue 120 Stage-C seed regeneration output summary",
        "",
        f"Historical root: `{args.historical_root}`",
        f"Regeneration root: `{args.regen_root}`",
        "",
        "## Totals",
        "",
        "```text",
        f"pages={len(rows)}",
        f"historical_total={historical_total}",
        f"consensus_seed_total={consensus_total}",
        f"raw_probe_total={raw_total}",
        f"final_filtered_total={final_total}",
        f"missing_consensus={len(missing_consensus)}",
        f"missing_raw={len(missing_raw)}",
        f"missing_final={len(missing_final)}",
        f"empty_final={len(empty_final)}",
        "```",
        "",
        "## Largest final-filtered losses",
        "",
        "| score | page | historical | consensus seed | raw probe | final filtered | final/historical |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in by_final_loss:
        ratio = (
            "" if row.final_to_historical_ratio is None else f"{row.final_to_historical_ratio:.3f}"
        )
        lines.append(
            f"| {row.score} | {row.page} | {row.historical_count} | "
            f"{row.consensus_seed_count} | {row.raw_probe_count} | "
            f"{row.final_filtered_count} | {ratio} |"
        )

    lines.extend(
        [
            "",
            "## Largest raw-probe losses",
            "",
            "| score | page | historical | consensus seed | raw probe | final filtered | raw-historical |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in by_raw_loss:
        lines.append(
            f"| {row.score} | {row.page} | {row.historical_count} | "
            f"{row.consensus_seed_count} | {row.raw_probe_count} | "
            f"{row.final_filtered_count} | {row.raw_minus_historical} |"
        )

    if empty_final:
        lines.extend(["", "## Final-filtered empty pages", ""])
        for row in empty_final[: args.limit]:
            lines.append(
                f"- `{row.score}/{row.page}`: historical={row.historical_count}, "
                f"consensus={row.consensus_seed_count}, raw={row.raw_probe_count}"
            )

    lines.extend(
        [
            "",
            "## Interpretation guide",
            "",
            "- If `raw_probe_total` is already far below historical, the drift occurs in probe generation or seed loading before heuristic filtering.",
            "- If `raw_probe_total` is close to historical but `final_filtered_total` is low, the drift occurs in `filter_probe_candidates` or its image/staff-mask inputs.",
            "- If `consensus_seed_total` is very low, inspect the historical `hybrid_generalization/verify_fixed_v10` source boxes and scaling before probe scan.",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-root", type=Path, default=DEFAULT_HISTORICAL_ROOT)
    parser.add_argument("--regen-root", type=Path, default=DEFAULT_REGEN_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = build_rows(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "stage_c_seed_regen_output_summary.csv")
    markdown = render_markdown(rows, args)
    (args.output_dir / "stage_c_seed_regen_output_summary.md").write_text(
        markdown + "\n", encoding="utf-8"
    )
    print(markdown)
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
