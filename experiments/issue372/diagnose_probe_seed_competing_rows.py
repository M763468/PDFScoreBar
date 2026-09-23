#!/usr/bin/env python3
"""Analyze competing-row geometry for Issue #372 probe seed trust.

Consumes the retained probe-seed-row trust report. No inference or detector
rerun is performed.

The diagnostic asks whether false singleton seed rows can be distinguished from
useful singleton rows by conflict with a nearby, stronger hybrid row. It reports
nearest-row geometry without selecting a production threshold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _band_metrics(a: list[int], b: list[int]) -> dict[str, float]:
    a1, a2 = sorted((float(a[0]), float(a[1])))
    b1, b2 = sorted((float(b[0]), float(b[1])))
    ah = max(1.0, a2 - a1)
    bh = max(1.0, b2 - b1)
    inter = max(0.0, min(a2, b2) - max(a1, b1))
    union = max(1.0, max(a2, b2) - min(a1, b1))
    return {
        "overlap_px": inter,
        "overlap_over_singleton": inter / ah,
        "overlap_over_other": inter / bh,
        "vertical_iou": inter / union,
    }


def _fmt(row: dict[str, Any]) -> str:
    n = row["nearest_multi"]
    if n is None:
        return (
            f"{row['score']}/{row['page']} gt={row['row_gt_class']} "
            f"support={row['row_support_class']} band={row['band']} "
            f"generated={row['generated_count']} generated_gt={row['generated_distinct_gt_count']} "
            "nearest_multi=None"
        )
    return (
        f"{row['score']}/{row['page']} gt={row['row_gt_class']} "
        f"support={row['row_support_class']} band={row['band']} "
        f"generated={row['generated_count']} generated_gt={row['generated_distinct_gt_count']} "
        f"nearest_multi_seeds={n['seed_count']} gap={n['center_gap']:.1f} "
        f"overlap_single={n['overlap_over_singleton']:.3f} "
        f"overlap_other={n['overlap_over_other']:.3f} viou={n['vertical_iou']:.3f}"
    )


def run(report_path: Path) -> dict[str, Any]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "issue372.probe_seed_row_trust.v1":
        raise ValueError(f"Unexpected report schema: {payload.get('schema_version')!r}")

    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Report lacks rows")

    by_page: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["score"]), str(row["page"]))
        by_page.setdefault(key, []).append(row)

    out_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("row_shape") != "singleton":
            continue

        key = (str(row["score"]), str(row["page"]))
        competitors = [
            other
            for other in by_page[key]
            if other is not row and other.get("row_shape") == "multi"
        ]

        nearest = None
        if competitors:
            other = min(
                competitors,
                key=lambda item: abs(float(item["center"]) - float(row["center"])),
            )
            metrics = _band_metrics(list(row["band"]), list(other["band"]))
            nearest = {
                "row_index": other["row_index"],
                "center": other["center"],
                "band": other["band"],
                "seed_count": other["seed_count"],
                "row_support_class": other["row_support_class"],
                "row_gt_class": other["row_gt_class"],
                "center_gap": abs(float(other["center"]) - float(row["center"])),
                **metrics,
            }

        out_rows.append(
            {
                "score": row["score"],
                "page": row["page"],
                "row_index": row["row_index"],
                "row_support_class": row["row_support_class"],
                "row_gt_class": row["row_gt_class"],
                "center": row["center"],
                "band": row["band"],
                "seed_count": row["seed_count"],
                "generated_count": row["generated_count"],
                "generated_distinct_gt_count": row["generated_distinct_gt_count"],
                "members": row["members"],
                "nearest_multi": nearest,
            }
        )

    true_rows = [r for r in out_rows if r["row_gt_class"] == "gt_true"]
    false_rows = [r for r in out_rows if r["row_gt_class"] == "gt_false"]

    def overlapping(rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            r
            for r in rs
            if r["nearest_multi"] is not None
            and float(r["nearest_multi"]["overlap_px"]) > 0.0
        ]

    def useful(rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in rs if int(r["generated_distinct_gt_count"]) > 0]

    true_overlap = overlapping(true_rows)
    false_overlap = overlapping(false_rows)
    useful_true = useful(true_rows)
    useful_true_overlap = overlapping(useful_true)

    page021 = [
        r
        for r in out_rows
        if r["score"] == "Shostakovich-Sym5-Va"
        and r["page"] == "page_021"
        and any(m.get("bbox") == [976, 753, 982, 845] for m in r["members"])
    ]

    result = {
        "schema_version": "issue372.probe_seed_competing_row.v1",
        "source_report": str(report_path.resolve()),
        "summary": {
            "singleton_rows": len(out_rows),
            "true_singletons": len(true_rows),
            "false_singletons": len(false_rows),
            "true_singletons_overlapping_multi": len(true_overlap),
            "false_singletons_overlapping_multi": len(false_overlap),
            "useful_true_singletons": len(useful_true),
            "useful_true_singletons_overlapping_multi": len(useful_true_overlap),
        },
        "page021_target": page021,
        "true_singletons": true_rows,
        "false_singletons": false_rows,
    }

    print("=== Issue #372 singleton competing-row diagnostic ===")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))

    print("\n=== page_021 target ===")
    for row in page021:
        print(_fmt(row))

    print("\n=== useful true singleton rows ===")
    for row in sorted(
        useful_true,
        key=lambda r: (-int(r["generated_distinct_gt_count"]), str(r["score"]), str(r["page"])),
    ):
        print(_fmt(row))

    print("\n=== false singleton rows overlapping a multi row ===")
    for row in sorted(
        false_overlap,
        key=lambda r: (
            -float(r["nearest_multi"]["overlap_over_singleton"]),
            -int(r["generated_count"]),
            str(r["score"]),
            str(r["page"]),
        ),
    ):
        print(_fmt(row))

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args.report.resolve())
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nOUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
