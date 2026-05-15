#!/usr/bin/env python3
"""Compare two filtered candidate trees for Issue #120 Stage D filter recovery.

The intended use is to compare the historical Issue #36 filtered candidate root
against a reproduced filtered root created from byte-identical raw candidates.
It reports per-page count/hash-like set deltas and optional suggestion reason
counts when filter suggestion JSONs are available.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue120.eval_full68_from_intermediates import (  # noqa: E402
    find_page_file,
    iter_manifest,
)

Box = tuple[int, int, int, int]


def load_boxes(path: Path | None) -> list[Box] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text())
    records: Any = payload.get("predictions", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return None
    boxes: list[Box] = []
    for item in records:
        bbox = item.get("bbox", item.get("pred_bbox")) if isinstance(item, dict) else item
        if isinstance(bbox, list) and len(bbox) >= 4:
            boxes.append(tuple(int(round(float(v))) for v in bbox[:4]))
    return boxes


def suggestion_path(root: Path | None, score: str, page: str) -> Path | None:
    if root is None:
        return None
    candidates = [
        root / score / f"{page}_suggestion.json",
        root / score / page / "suggestion.json",
        root / f"eval2_{score}_{page}" / "suggestion.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_suggestion_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": str(path) if path else None,
            "exists": False,
            "counts": None,
            "reason_counts": {},
        }
    payload = json.loads(path.read_text())
    reason_counts: Counter[str] = Counter()
    for item in payload.get("drop_suggested", []):
        if not isinstance(item, dict):
            continue
        for reason in item.get("reasons", []):
            reason_counts[str(reason)] += 1
    return {
        "path": str(path),
        "exists": True,
        "counts": payload.get("counts"),
        "rules": payload.get("rules"),
        "input": payload.get("input"),
        "reason_counts": dict(reason_counts),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-dir", type=Path, required=True)
    parser.add_argument("--repro-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-file", default="pipeline2_no_peak_candidates.json")
    parser.add_argument("--historical-suggestions-root", type=Path, default=None)
    parser.add_argument("--repro-suggestions-root", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    total_historical = 0
    total_repro = 0
    total_extra_in_repro = 0
    total_missing_from_repro = 0
    missing_historical_pages = 0
    missing_repro_pages = 0
    mismatch_pages = 0
    repro_reason_counts: Counter[str] = Counter()
    historical_reason_counts: Counter[str] = Counter()

    for record in iter_manifest():
        historical_path = find_page_file(args.historical_dir, record, args.candidate_file)
        repro_path = find_page_file(args.repro_dir, record, args.candidate_file)
        historical_boxes = load_boxes(historical_path)
        repro_boxes = load_boxes(repro_path)

        if historical_boxes is None:
            missing_historical_pages += 1
            historical_set: set[Box] = set()
        else:
            historical_set = set(historical_boxes)
        if repro_boxes is None:
            missing_repro_pages += 1
            repro_set: set[Box] = set()
        else:
            repro_set = set(repro_boxes)

        extra_in_repro = sorted(repro_set - historical_set)
        missing_from_repro = sorted(historical_set - repro_set)
        if extra_in_repro or missing_from_repro:
            mismatch_pages += 1

        historical_count = len(historical_boxes or [])
        repro_count = len(repro_boxes or [])
        total_historical += historical_count
        total_repro += repro_count
        total_extra_in_repro += len(extra_in_repro)
        total_missing_from_repro += len(missing_from_repro)

        hist_sugg = load_suggestion_summary(
            suggestion_path(args.historical_suggestions_root, record.score, record.page)
        )
        repro_sugg = load_suggestion_summary(
            suggestion_path(args.repro_suggestions_root, record.score, record.page)
        )
        historical_reason_counts.update(hist_sugg.get("reason_counts", {}))
        repro_reason_counts.update(repro_sugg.get("reason_counts", {}))

        rows.append(
            {
                "score": record.score,
                "page": record.page,
                "historical_count": historical_count,
                "repro_count": repro_count,
                "delta_count": repro_count - historical_count,
                "extra_in_repro": len(extra_in_repro),
                "missing_from_repro": len(missing_from_repro),
                "historical_path": str(historical_path) if historical_path else None,
                "repro_path": str(repro_path) if repro_path else None,
                "historical_suggestion_path": hist_sugg.get("path"),
                "repro_suggestion_path": repro_sugg.get("path"),
                "historical_reason_counts": hist_sugg.get("reason_counts", {}),
                "repro_reason_counts": repro_sugg.get("reason_counts", {}),
                "extra_in_repro_sample": [list(b) for b in extra_in_repro[:10]],
                "missing_from_repro_sample": [list(b) for b in missing_from_repro[:10]],
            }
        )

    worst_by_extra = sorted(rows, key=lambda r: int(r["extra_in_repro"]), reverse=True)[
        : args.top_k
    ]
    worst_by_missing = sorted(rows, key=lambda r: int(r["missing_from_repro"]), reverse=True)[
        : args.top_k
    ]
    worst_by_abs_delta = sorted(rows, key=lambda r: abs(int(r["delta_count"])), reverse=True)[
        : args.top_k
    ]

    summary = {
        "schema_version": "issue120.stage_d.filter_delta.v1",
        "historical_dir": str(args.historical_dir),
        "repro_dir": str(args.repro_dir),
        "candidate_file": args.candidate_file,
        "pages": len(rows),
        "missing_historical_pages": missing_historical_pages,
        "missing_repro_pages": missing_repro_pages,
        "mismatch_pages": mismatch_pages,
        "historical_total": total_historical,
        "repro_total": total_repro,
        "total_delta": total_repro - total_historical,
        "total_extra_in_repro": total_extra_in_repro,
        "total_missing_from_repro": total_missing_from_repro,
        "historical_reason_counts": dict(historical_reason_counts),
        "repro_reason_counts": dict(repro_reason_counts),
        "worst_by_extra_in_repro": worst_by_extra,
        "worst_by_missing_from_repro": worst_by_missing,
        "worst_by_abs_delta": worst_by_abs_delta,
    }

    (args.output_dir / "filter_candidate_delta_summary.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with (args.output_dir / "filter_candidate_delta_rows.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        fieldnames = [
            "score",
            "page",
            "historical_count",
            "repro_count",
            "delta_count",
            "extra_in_repro",
            "missing_from_repro",
            "historical_path",
            "repro_path",
            "historical_suggestion_path",
            "repro_suggestion_path",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})

    print("Filter candidate delta comparison")
    print(f"Pages: {len(rows)}")
    print(f"Historical total: {total_historical}")
    print(f"Repro total: {total_repro}")
    print(f"Total delta: {total_repro - total_historical}")
    print(f"Mismatch pages: {mismatch_pages}")
    print(f"Extra in repro: {total_extra_in_repro}")
    print(f"Missing from repro: {total_missing_from_repro}")
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
