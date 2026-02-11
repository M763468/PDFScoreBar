#!/usr/bin/env python3
"""Apply candidate drop suggestions across inventory pages and write filtered candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.verification.gt_preparation.suggest_candidate_drops import suggest_candidate_drops


def _resolve_clef_mask_path(rec: dict[str, Any]) -> Path | None:
    explicit = rec.get("clef_mask")
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p

    staff_mask_raw = rec.get("staff_mask")
    if staff_mask_raw:
        staff_mask = Path(staff_mask_raw)
        candidates = [
            Path(
                str(staff_mask).replace("_proxy_debug_3_staff.png", "_proxy_debug_7_clefs_keys.png")
            ),
            Path(str(staff_mask).replace("_debug_3_staff.png", "_debug_7_clefs_keys.png")),
        ]
        for p in candidates:
            if p.exists():
                return p

    run_dir_raw = rec.get("run_dir")
    if run_dir_raw:
        run_dir = Path(run_dir_raw)
        found = sorted(run_dir.rglob("*_debug_7_clefs_keys.png"))
        if found:
            page = str(rec.get("page", ""))
            for p in found:
                if page and page in p.name:
                    return p
            return found[0]

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, required=True)
    parser.add_argument("--candidates-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--suggestions-root", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--left-margin-ratio", type=float, default=0.12)
    parser.add_argument("--clef-left-ratio", type=float, default=0.25)
    parser.add_argument("--min-height-median-ratio", type=float, default=0.6)
    parser.add_argument("--ink-threshold", type=int, default=180)
    parser.add_argument("--min-ink-ratio", type=float, default=0.18)
    parser.add_argument("--paper-threshold", type=int, default=200)
    parser.add_argument("--min-paper-overlap-ratio", type=float, default=0.6)
    parser.add_argument("--min-staff-overlap-ratio", type=float, default=0.01)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text())
    records = inventory.get("records", [])
    if not isinstance(records, list):
        raise ValueError("Invalid inventory: records must be list")

    exclude_obj = json.loads(args.exclude.read_text())
    excluded = {
        (x["score"], x["page"]) for x in exclude_obj.get("excluded_pages", []) if "score" in x
    }

    processed = 0
    skipped = 0
    errors = 0
    reason_counts: dict[str, int] = {}
    per_page: list[dict[str, Any]] = []

    for rec in records:
        score = str(rec["score"])
        page = str(rec["page"])
        key = (score, page)
        if key in excluded:
            skipped += 1
            continue

        image = Path(rec["image"])
        existing = Path(rec["hybrid_predictions"])
        staff_mask = Path(rec["staff_mask"]) if rec.get("staff_mask") else None
        clef_mask = _resolve_clef_mask_path(rec)
        candidates = args.candidates_root / score / page / "pipeline2_no_peak_candidates.json"

        try:
            sugg = suggest_candidate_drops(
                image_path=image,
                candidates_path=candidates,
                existing_path=existing,
                staff_mask_path=staff_mask,
                clef_mask_path=clef_mask,
                left_margin_ratio=args.left_margin_ratio,
                clef_left_ratio=args.clef_left_ratio,
                min_height_median_ratio=args.min_height_median_ratio,
                ink_threshold=args.ink_threshold,
                min_ink_ratio=args.min_ink_ratio,
                paper_threshold=args.paper_threshold,
                min_paper_overlap_ratio=args.min_paper_overlap_ratio,
                min_staff_overlap_ratio=args.min_staff_overlap_ratio,
            )

            keep_boxes = [item["bbox"] for item in sugg["keep"]]
            out_dir = args.output_root / score / page
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "pipeline2_no_peak_candidates.json").write_text(
                json.dumps(keep_boxes, indent=2)
            )

            sdir = args.suggestions_root / score
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / f"{page}_suggestion.json").write_text(json.dumps(sugg, indent=2))

            for d in sugg["drop_suggested"]:
                for reason in d.get("reasons", []):
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1

            per_page.append(
                {
                    "score": score,
                    "page": page,
                    "candidates": sugg["counts"]["candidates"],
                    "keep": sugg["counts"]["keep"],
                    "drop_suggested": sugg["counts"]["drop_suggested"],
                    "filtered_candidates_path": str(out_dir / "pipeline2_no_peak_candidates.json"),
                }
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001
            per_page.append({"score": score, "page": page, "error": str(exc)})
            errors += 1

    summary = {
        "inventory": str(args.inventory),
        "exclude": str(args.exclude),
        "candidates_root": str(args.candidates_root),
        "output_root": str(args.output_root),
        "suggestions_root": str(args.suggestions_root),
        "rules": {
            "left_margin_ratio": args.left_margin_ratio,
            "clef_left_ratio": args.clef_left_ratio,
            "min_height_median_ratio": args.min_height_median_ratio,
            "ink_threshold": args.ink_threshold,
            "min_ink_ratio": args.min_ink_ratio,
            "paper_threshold": args.paper_threshold,
            "min_paper_overlap_ratio": args.min_paper_overlap_ratio,
            "min_staff_overlap_ratio": args.min_staff_overlap_ratio,
        },
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "reason_counts": reason_counts,
        "per_page": per_page,
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2))
    print(json.dumps({"processed": processed, "skipped": skipped, "errors": errors}))


if __name__ == "__main__":
    main()
