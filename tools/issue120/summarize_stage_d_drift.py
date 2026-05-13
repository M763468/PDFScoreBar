#!/usr/bin/env python3
"""Summarize Issue #120 Stage-D detector drift from local log outputs.

This helper reads generated files under ignored `logs/` paths.  It does not run
HOMR/SR/OMR, probe scan, CNN scoring, or evaluation.  It is intended for the
post-run analysis step after:

    make regen-issue120-stage-d-upstream ISSUE120_CLEAN_OUTPUT=1
    make verify-issue120-stage-d
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_EVAL_DIR = Path("logs/issue120_e2e_recovery/stage_d_from_current_upstream_eval")
DEFAULT_UPSTREAM_DIR = Path("logs/issue120_e2e_recovery/stage_d_upstream_regen")


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_page_metrics(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Missing detector page metrics: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    numeric_fields = {"gt", "pred", "candidate_count", "tp", "fp", "fn", "fn_det", "fn_cnn"}
    float_fields = {"precision", "recall"}
    for row in rows:
        for field in numeric_fields:
            if row.get(field) not in (None, "", "None"):
                row[field] = int(float(row[field]))
            else:
                row[field] = None
        for field in float_fields:
            if row.get(field) not in (None, "", "None"):
                row[field] = float(row[field])
            else:
                row[field] = None
    return rows


def candidate_coverage_rows(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows")
    return rows if isinstance(rows, list) else []


def key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("score", "")), str(row.get("page", ""))


def format_detector(summary: dict[str, Any] | None) -> str:
    if not summary:
        return "detector_summary: unavailable"
    return (
        "detector_summary: "
        f"GT={summary.get('gt')} Pred={summary.get('pred')} "
        f"TP={summary.get('tp')} FP={summary.get('fp')} FN={summary.get('fn')} "
        f"FN_det={summary.get('fn_det')} FN_cnn={summary.get('fn_cnn')} "
        f"Precision={summary.get('precision')} Recall={summary.get('recall')}"
    )


def sort_rows(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    def rank(row: dict[str, Any]) -> tuple[Any, ...]:
        values = []
        for field in fields:
            value = row.get(field)
            values.append(value if value is not None else -1)
        return tuple(values)

    return sorted(rows, key=rank, reverse=True)


def render_markdown(
    *,
    eval_dir: Path,
    upstream_dir: Path,
    detector_summary: dict[str, Any] | None,
    page_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    upstream_summary: dict[str, Any] | None,
    limit: int,
) -> str:
    coverage_by_key = {key(row): row for row in coverage_rows}
    joined: list[dict[str, Any]] = []
    for row in page_rows:
        cov = coverage_by_key.get(key(row), {})
        joined.append(
            {
                "score": row.get("score"),
                "page": row.get("page"),
                "gt": row.get("gt"),
                "pred": row.get("pred"),
                "candidate_count": row.get("candidate_count"),
                "tp": row.get("tp"),
                "fp": row.get("fp"),
                "fn": row.get("fn"),
                "fn_det": row.get("fn_det"),
                "fn_cnn": row.get("fn_cnn"),
                "baseline_candidates": cov.get("baseline_count"),
                "stage_d_candidates": cov.get("candidate_count"),
                "candidate_delta": cov.get("delta"),
                "candidate_ratio": cov.get("candidate_to_baseline_ratio"),
            }
        )

    top_detector = sort_rows(joined, ("fn_det", "fn", "fp"))[:limit]
    top_fp = sort_rows(joined, ("fp", "fn", "fn_det"))[:limit]
    low_coverage = sorted(
        joined,
        key=lambda row: row.get("candidate_ratio") if row.get("candidate_ratio") is not None else -1,
    )[:limit]

    lines = [
        "# Issue 120 Stage-D drift summary",
        "",
        f"Evaluation dir: `{eval_dir}`",
        f"Upstream dir: `{upstream_dir}`",
        "",
        "## Detector summary",
        "",
        f"```text\n{format_detector(detector_summary)}\n```",
    ]
    if upstream_summary:
        lines.extend(
            [
                "",
                "## Upstream composition summary",
                "",
                "```text",
                f"expected_pages={upstream_summary.get('expected_pages')}",
                f"composed_pages={upstream_summary.get('composed_pages')}",
                f"missing_pages={upstream_summary.get('missing_pages')}",
                f"disable_sr={upstream_summary.get('disable_sr')}",
                f"sr_scale={upstream_summary.get('sr_scale')}",
                "```",
            ]
        )

    def table(title: str, rows: list[dict[str, Any]]) -> None:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| score | page | pred | fp | fn | fn_det | fn_cnn | baseline candidates | Stage-D candidates | ratio |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in rows:
            ratio = row.get("candidate_ratio")
            ratio_text = "" if ratio is None else f"{float(ratio):.3f}"
            lines.append(
                "| "
                f"{row.get('score')} | {row.get('page')} | {row.get('pred')} | "
                f"{row.get('fp')} | {row.get('fn')} | {row.get('fn_det')} | {row.get('fn_cnn')} | "
                f"{row.get('baseline_candidates')} | {row.get('stage_d_candidates')} | {ratio_text} |"
            )

    table("Worst pages by detector-side FN", top_detector)
    table("Worst pages by FP", top_fp)
    if coverage_rows:
        table("Lowest candidate coverage pages", low_coverage)

    lines.extend(
        [
            "",
            "## Interpretation guide",
            "",
            "- High `FN_det` indicates candidate-generation or upstream-band coverage loss before CNN scoring.",
            "- High `FN_cnn` with low `FN_det` indicates scoring/filtering loss after candidate generation.",
            "- High `FP` with increased candidate coverage suggests geometry or over-generation drift.",
            "- Candidate coverage ratios are candidate-count signals only; they do not prove geometric match quality.",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument("--upstream-dir", type=Path, default=DEFAULT_UPSTREAM_DIR)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_EVAL_DIR / "stage_d_drift_summary.md",
        help="Markdown summary path under ignored logs/.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    detector_contract = load_json(args.eval_dir / "evaluation_contract.json")
    detector_summary = None
    if isinstance(detector_contract, dict):
        detector_summary = detector_contract.get("detector_summary")

    page_rows = load_page_metrics(args.eval_dir / "detector_page_metrics.csv")
    coverage_rows = candidate_coverage_rows(args.eval_dir / "candidate_coverage_comparison.json")
    upstream_payload = load_json(args.upstream_dir / "stage_d_upstream_regen_provenance.json")
    upstream_summary = None
    if isinstance(upstream_payload, dict):
        upstream_summary = upstream_payload.get("summary")

    summary = render_markdown(
        eval_dir=args.eval_dir,
        upstream_dir=args.upstream_dir,
        detector_summary=detector_summary,
        page_rows=page_rows,
        coverage_rows=coverage_rows,
        upstream_summary=upstream_summary,
        limit=args.limit,
    )
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"\nWrote: {args.output_md}")


if __name__ == "__main__":
    main()
