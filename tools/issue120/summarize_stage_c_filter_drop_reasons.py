#!/usr/bin/env python3
"""Summarize filter_probe_candidates drop reasons for Stage-C seed regeneration.

This #147 diagnostic replays the final filtering step from
`tools/repro_accuracy/reproduce_clean_seed_v12.py` against already-generated raw
probe candidates and reports why candidates were dropped.

It does not rerun probe scan, CNN scoring, or evaluation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import cv2
except ImportError as exc:  # pragma: no cover
    raise SystemExit("summarize_stage_c_filter_drop_reasons.py requires opencv-python") from exc

from src.pipeline.steps.candidate_filters import filter_probe_candidates  # noqa: E402
from src.pipeline.steps.hybrid_consensus import load_json_boxes  # noqa: E402
from tools.issue120.eval_full68_from_intermediates import iter_manifest  # noqa: E402


DEFAULT_REGEN_ROOT = Path("logs/issue120_e2e_recovery/stage_d_issue36_repro")
DEFAULT_OUTPUT_DIR = Path("logs/issue120_e2e_recovery/stage_d_issue36_filter_drop_reasons")
DEFAULT_INVENTORY = Path("logs/issue36_prep/20260208_bench_inventory.json")


@dataclass(frozen=True)
class PageFilterReasonRow:
    score: str
    page: str
    raw_count: int
    kept_count: int
    dropped_count: int
    top_reasons: str
    reason_counts: str
    combo_counts: str
    image_path: str | None
    staff_mask_path: str | None
    raw_path: str | None


def load_inventory(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    return {(str(rec["score"]), str(rec["page"])): rec for rec in records}


def make_rules(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "left_margin_ratio": args.left_margin_ratio,
        "clef_left_ratio": args.clef_left_ratio,
        "min_height_median_ratio": args.min_height_median_ratio,
        "ink_threshold": args.ink_threshold,
        "min_ink_ratio": args.min_ink_ratio,
        "paper_threshold": args.paper_threshold,
        "min_paper_overlap_ratio": args.min_paper_overlap_ratio,
        "min_staff_overlap_ratio": args.min_staff_overlap_ratio,
    }


def replay_page(
    *,
    score: str,
    page: str,
    rec: dict[str, Any] | None,
    regen_root: Path,
    rules: dict[str, Any],
) -> PageFilterReasonRow:
    page_dir = regen_root / score / page
    raw_path = page_dir / f"eval2_{score}_{page}" / "pipeline2_no_peak_candidates.json"
    raw_candidates = load_json_boxes(raw_path) if raw_path.exists() else []

    image_path = PROJECT_ROOT / rec["image"] if rec and "image" in rec else None
    staff_mask_path = PROJECT_ROOT / rec["staff_mask"] if rec and "staff_mask" in rec else None
    img = cv2.imread(str(image_path)) if image_path is not None else None
    staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE) if staff_mask_path else None

    if img is None:
        return PageFilterReasonRow(
            score=score,
            page=page,
            raw_count=len(raw_candidates),
            kept_count=0,
            dropped_count=len(raw_candidates),
            top_reasons="image_load_failed",
            reason_counts=json.dumps({"image_load_failed": len(raw_candidates)}, sort_keys=True),
            combo_counts=json.dumps({"image_load_failed": len(raw_candidates)}, sort_keys=True),
            image_path=str(image_path) if image_path else None,
            staff_mask_path=str(staff_mask_path) if staff_mask_path else None,
            raw_path=str(raw_path) if raw_path.exists() else None,
        )

    if staff_mask is not None and staff_mask.shape[:2] != img.shape[:2]:
        staff_mask = cv2.resize(staff_mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)

    kept, dropped = filter_probe_candidates(
        candidates=raw_candidates,
        image=img,
        existing_boxes=[],
        staff_mask=staff_mask,
        **rules,
    )

    reason_counts: Counter[str] = Counter()
    combo_counts: Counter[str] = Counter()
    for item in dropped:
        reasons = [str(reason) for reason in item.get("reasons", [])]
        reason_counts.update(reasons)
        combo_counts["+".join(sorted(reasons)) if reasons else "<none>"] += 1

    top_reasons = ", ".join(f"{key}:{value}" for key, value in reason_counts.most_common(5))
    return PageFilterReasonRow(
        score=score,
        page=page,
        raw_count=len(raw_candidates),
        kept_count=len(kept),
        dropped_count=len(dropped),
        top_reasons=top_reasons,
        reason_counts=json.dumps(dict(sorted(reason_counts.items())), sort_keys=True),
        combo_counts=json.dumps(dict(combo_counts.most_common(20)), sort_keys=True),
        image_path=str(image_path) if image_path else None,
        staff_mask_path=str(staff_mask_path) if staff_mask_path else None,
        raw_path=str(raw_path) if raw_path.exists() else None,
    )


def write_csv(rows: list[PageFilterReasonRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def render_markdown(rows: list[PageFilterReasonRow], args: argparse.Namespace) -> str:
    total_raw = sum(row.raw_count for row in rows)
    total_kept = sum(row.kept_count for row in rows)
    total_dropped = sum(row.dropped_count for row in rows)
    global_reasons: Counter[str] = Counter()
    global_combos: Counter[str] = Counter()
    for row in rows:
        global_reasons.update(json.loads(row.reason_counts))
        global_combos.update(json.loads(row.combo_counts))

    by_kept_ratio = sorted(
        rows,
        key=lambda row: (row.kept_count / row.raw_count) if row.raw_count else 0.0,
    )[: args.limit]

    lines = [
        "# Issue 120 Stage-C filter drop reason summary",
        "",
        f"Regeneration root: `{args.regen_root}`",
        f"Inventory: `{args.inventory}`",
        "",
        "## Rules replayed",
        "",
        "```json",
        json.dumps(make_rules(args), indent=2, sort_keys=True),
        "```",
        "",
        "## Totals",
        "",
        "```text",
        f"pages={len(rows)}",
        f"raw_total={total_raw}",
        f"kept_total={total_kept}",
        f"dropped_total={total_dropped}",
        f"kept_ratio={total_kept / total_raw if total_raw else 0.0:.6f}",
        "```",
        "",
        "## Global reason counts",
        "",
        "| reason | count |",
        "| --- | ---: |",
    ]
    for reason, count in global_reasons.most_common():
        lines.append(f"| {reason} | {count} |")

    lines.extend(
        [
            "",
            "## Global reason-combination counts",
            "",
            "| reasons | count |",
            "| --- | ---: |",
        ]
    )
    for combo, count in global_combos.most_common(20):
        lines.append(f"| {combo} | {count} |")

    lines.extend(
        [
            "",
            "## Lowest kept-ratio pages",
            "",
            "| score | page | raw | kept | dropped | kept/raw | top reasons |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in by_kept_ratio:
        ratio = row.kept_count / row.raw_count if row.raw_count else 0.0
        lines.append(
            f"| {row.score} | {row.page} | {row.raw_count} | {row.kept_count} | "
            f"{row.dropped_count} | {ratio:.6f} | {row.top_reasons} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation guide",
            "",
            "- Dominant `no_staff_overlap` indicates staff-mask alignment, mask content, or candidate coordinate-frame mismatch.",
            "- Dominant `low_ink_ratio` indicates candidate boxes are not centered on ink after current probe generation or image preprocessing drift.",
            "- Dominant `low_paper_overlap` / `outside_page_region` indicates page-mask or coordinate-frame mismatch.",
            "- Dominant `left_margin_zone` / `clef_mask_overlap` indicates clef/left-margin filtering is too aggressive for the regenerated candidate family.",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regen-root", type=Path, default=DEFAULT_REGEN_ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--left-margin-ratio", type=float, default=0.12)
    parser.add_argument("--clef-left-ratio", type=float, default=0.25)
    parser.add_argument("--min-height-median-ratio", type=float, default=0.4)
    parser.add_argument("--ink-threshold", type=int, default=180)
    parser.add_argument("--min-ink-ratio", type=float, default=0.18)
    parser.add_argument("--paper-threshold", type=int, default=200)
    parser.add_argument("--min-paper-overlap-ratio", type=float, default=0.6)
    parser.add_argument("--min-staff-overlap-ratio", type=float, default=0.02)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    inventory = load_inventory(args.inventory)
    rules = make_rules(args)
    rows: list[PageFilterReasonRow] = []
    for record in iter_manifest():
        rec = inventory.get((record.score, record.page))
        rows.append(
            replay_page(
                score=record.score,
                page=record.page,
                rec=rec,
                regen_root=args.regen_root,
                rules=rules,
            )
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "stage_c_filter_drop_reasons.csv")
    markdown = render_markdown(rows, args)
    (args.output_dir / "stage_c_filter_drop_reasons.md").write_text(markdown + "\n", encoding="utf-8")
    print(markdown)
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
