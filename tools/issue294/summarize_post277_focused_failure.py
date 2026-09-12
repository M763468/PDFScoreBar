#!/usr/bin/env python3
"""Summarize the latest Issue #294 post-#277 focused MMR failure.

This is an experiment-only diagnostic helper. It reads an already-produced focused
JSON artifact and prints only the evidence needed to distinguish candidate regressions
from scoring/rebase or harness problems. It does not execute inference or post to GitHub.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = ROOT / "logs/issue294"


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _latest() -> Path:
    candidates = list(LOG_ROOT.glob("issue294_post277_focused_*.json"))
    if not candidates:
        raise FileNotFoundError("No issue294_post277_focused_*.json artifact found")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _by_page(variant: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    pages = variant.get("pages")
    if not isinstance(pages, list):
        return {}
    return {
        str(page.get("page_id")): page
        for page in pages
        if isinstance(page, Mapping) and page.get("page_id") is not None
    }


def _counts(page: Mapping[str, Any]) -> dict[str, int]:
    scoring = page.get("scoring")
    if not isinstance(scoring, Mapping):
        return {}
    counts = scoring.get("counts")
    if not isinstance(counts, Mapping):
        return {}
    keys = ("expected", "detected", "matched_tp", "missed_fn", "skip_mismatch", "unexpected_fp")
    return {key: int(counts.get(key, 0)) for key in keys}


def _errors(counts: Mapping[str, int]) -> int:
    return int(counts.get("missed_fn", 0)) + int(counts.get("skip_mismatch", 0)) + int(
        counts.get("unexpected_fp", 0)
    )


def _not_worse(a: Mapping[str, int], candidate: Mapping[str, int]) -> bool:
    return bool(
        int(candidate.get("unexpected_fp", 0)) <= int(a.get("unexpected_fp", 0))
        and _errors(candidate) <= _errors(a)
        and int(candidate.get("matched_tp", 0)) >= int(a.get("matched_tp", 0))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", nargs="?", type=Path)
    args = parser.parse_args()

    path = (args.artifact or _latest()).resolve()
    payload = _load(path)
    variants = payload.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("Focused artifact lacks variants")

    a = variants["A_production"]
    b = variants["B_b377_mapping_guarded"]
    c = variants["C_latest_mapping_guarded"]
    a_pages = _by_page(a)
    b_pages = _by_page(b)
    c_pages = _by_page(c)

    failed_gates = [
        key
        for key, value in dict(payload.get("gates") or {}).items()
        if value is False
    ]

    degraded_pages: list[dict[str, Any]] = []
    for page_id in payload.get("selected_pages") or []:
        a_counts = _counts(a_pages[page_id])
        b_counts = _counts(b_pages[page_id])
        c_counts = _counts(c_pages[page_id])
        if not _not_worse(a_counts, b_counts) or not _not_worse(a_counts, c_counts):
            degraded_pages.append(
                {
                    "page_id": page_id,
                    "A": a_counts,
                    "B": b_counts,
                    "C": c_counts,
                    "A_row_start_equal": a_pages[page_id].get("row_start_semantic_equal"),
                    "B_row_start_equal": b_pages[page_id].get("row_start_semantic_equal"),
                    "C_row_start_equal": c_pages[page_id].get("row_start_semantic_equal"),
                    "A_numbering_shape": a_pages[page_id].get("numbering_shape"),
                    "B_numbering_shape": b_pages[page_id].get("numbering_shape"),
                    "C_numbering_shape": c_pages[page_id].get("numbering_shape"),
                    "A_expected": a_pages[page_id].get("expected"),
                    "A_actual": a_pages[page_id].get("actual"),
                    "B_expected": b_pages[page_id].get("expected"),
                    "B_actual": b_pages[page_id].get("actual"),
                    "C_expected": c_pages[page_id].get("expected"),
                    "C_actual": c_pages[page_id].get("actual"),
                }
            )

    page_042 = {
        label: {
            "counts": _counts(pages.get("page_042", {})),
            "row_start_semantic_equal": pages.get("page_042", {}).get("row_start_semantic_equal"),
            "numbering_shape": pages.get("page_042", {}).get("numbering_shape"),
            "expected": pages.get("page_042", {}).get("expected"),
            "actual": pages.get("page_042", {}).get("actual"),
        }
        for label, pages in (("A", a_pages), ("B", b_pages), ("C", c_pages))
    }

    summary = {
        "artifact": str(path),
        "artifact_git": payload.get("git"),
        "mode": payload.get("mode"),
        "selected_page_count": len(payload.get("selected_pages") or []),
        "all_gates_pass": payload.get("all_gates_pass"),
        "failed_gates": failed_gates,
        "totals": {
            "A": a.get("totals"),
            "B": b.get("totals"),
            "C": c.get("totals"),
        },
        "variant_gates": {
            "A": a.get("gates"),
            "B": b.get("gates"),
            "C": c.get("gates"),
        },
        "page_042": page_042,
        "degraded_pages_vs_A": degraded_pages,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
