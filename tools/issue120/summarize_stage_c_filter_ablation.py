#!/usr/bin/env python3
"""Run Stage-C seed final-filter ablations for Issue #120 #147.

This diagnostic replays `filter_probe_candidates` against already-generated raw
probe candidates using several rule profiles.  It is intended to identify which
heuristic gate causes the v12 seed-regeneration collapse.

It does not rerun probe scan, CNN scoring, or evaluation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import cv2
except ImportError as exc:  # pragma: no cover
    raise SystemExit("summarize_stage_c_filter_ablation.py requires opencv-python") from exc

from src.pipeline.steps.candidate_filters import filter_probe_candidates  # noqa: E402
from src.pipeline.steps.hybrid_consensus import load_json_boxes  # noqa: E402
from tools.issue120.eval_full68_from_intermediates import iter_manifest  # noqa: E402

DEFAULT_REGEN_ROOT = Path("logs/issue120_e2e_recovery/stage_d_issue36_repro")
DEFAULT_OUTPUT_DIR = Path("logs/issue120_e2e_recovery/stage_d_issue36_filter_ablation")
DEFAULT_INVENTORY = Path("logs/issue36_prep/20260208_bench_inventory.json")
DEFAULT_HISTORICAL_ROOT = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
)

BASE_RULES: dict[str, Any] = {
    "left_margin_ratio": 0.12,
    "clef_left_ratio": 0.25,
    "min_height_median_ratio": 0.4,
    "ink_threshold": 180,
    "min_ink_ratio": 0.18,
    "paper_threshold": 200,
    "min_paper_overlap_ratio": 0.6,
    "min_staff_overlap_ratio": 0.02,
}

PROFILES: dict[str, dict[str, Any]] = {
    "current": {},
    "paper_overlap_0": {"min_paper_overlap_ratio": 0.0},
    "paper_overlap_0p1": {"min_paper_overlap_ratio": 0.1},
    "paper_overlap_0p3": {"min_paper_overlap_ratio": 0.3},
    "staff_overlap_0": {"min_staff_overlap_ratio": 0.0},
    "ink_ratio_0": {"min_ink_ratio": 0.0},
    "left_margin_0": {"left_margin_ratio": 0.0, "clef_left_ratio": 0.0},
    "paper_staff_0": {"min_paper_overlap_ratio": 0.0, "min_staff_overlap_ratio": 0.0},
    "paper_ink_0": {"min_paper_overlap_ratio": 0.0, "min_ink_ratio": 0.0},
    "paper_staff_ink_0": {
        "min_paper_overlap_ratio": 0.0,
        "min_staff_overlap_ratio": 0.0,
        "min_ink_ratio": 0.0,
    },
    "all_spatial_relaxed": {
        "min_paper_overlap_ratio": 0.0,
        "min_staff_overlap_ratio": 0.0,
        "min_ink_ratio": 0.0,
        "left_margin_ratio": 0.0,
        "clef_left_ratio": 0.0,
    },
}


@dataclass(frozen=True)
class ProfileSummaryRow:
    profile: str
    pages: int
    raw_total: int
    kept_total: int
    dropped_total: int
    kept_ratio: float
    empty_pages: int
    historical_total: int
    kept_minus_historical: int
    kept_to_historical_ratio: float | None
    overrides: str


@dataclass(frozen=True)
class PageAblationRow:
    profile: str
    score: str
    page: str
    historical_count: int
    raw_count: int
    kept_count: int
    kept_to_historical_ratio: float | None


def load_inventory(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    return {(str(rec["score"]), str(rec["page"])): rec for rec in records}


def load_count(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("predictions", "bars", "barlines", "items", "candidates"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def load_image_and_mask(rec: dict[str, Any]) -> tuple[Any, Any, Path, Path]:
    image_path = PROJECT_ROOT / rec["image"]
    staff_mask_path = PROJECT_ROOT / rec["staff_mask"]
    img = cv2.imread(str(image_path))
    if img is None:
        raise RuntimeError(f"Could not load image: {image_path}")
    staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
    if staff_mask is not None and staff_mask.shape[:2] != img.shape[:2]:
        staff_mask = cv2.resize(
            staff_mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST
        )
    return img, staff_mask, image_path, staff_mask_path


def rules_for_profile(profile: str) -> dict[str, Any]:
    rules = dict(BASE_RULES)
    rules.update(PROFILES[profile])
    return rules


def write_csv(rows: list[Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def run(args: argparse.Namespace) -> tuple[list[ProfileSummaryRow], list[PageAblationRow]]:
    inventory = load_inventory(args.inventory)
    profiles = args.profiles or list(PROFILES.keys())
    summary_rows: list[ProfileSummaryRow] = []
    page_rows: list[PageAblationRow] = []

    records = list(iter_manifest())
    raw_by_page: dict[tuple[str, str], list[Any]] = {}
    historical_count_by_page: dict[tuple[str, str], int] = {}
    images_by_page: dict[tuple[str, str], tuple[Any, Any]] = {}

    for record in records:
        key = (record.score, record.page)
        raw_path = (
            args.regen_root
            / record.score
            / record.page
            / f"eval2_{record.score}_{record.page}"
            / "pipeline2_no_peak_candidates.json"
        )
        raw_by_page[key] = load_json_boxes(raw_path) if raw_path.exists() else []
        historical_path = (
            args.historical_root / record.score / record.page / "pipeline2_no_peak_candidates.json"
        )
        historical_count_by_page[key] = load_count(historical_path)
        rec = inventory.get(key)
        if rec is None:
            raise RuntimeError(f"Missing inventory record for {record.score}/{record.page}")
        img, staff_mask, _, _ = load_image_and_mask(rec)
        images_by_page[key] = (img, staff_mask)

    historical_total = sum(historical_count_by_page.values())
    raw_total = sum(len(values) for values in raw_by_page.values())

    for profile in profiles:
        if profile not in PROFILES:
            raise SystemExit(f"Unknown profile: {profile}. Valid profiles: {', '.join(PROFILES)}")
        rules = rules_for_profile(profile)
        kept_total = 0
        dropped_total = 0
        empty_pages = 0
        for record in records:
            key = (record.score, record.page)
            img, staff_mask = images_by_page[key]
            kept, dropped = filter_probe_candidates(
                candidates=raw_by_page[key],
                image=img,
                existing_boxes=[],
                staff_mask=staff_mask,
                **rules,
            )
            kept_count = len(kept)
            dropped_count = len(dropped)
            kept_total += kept_count
            dropped_total += dropped_count
            if kept_count == 0:
                empty_pages += 1
            hist_count = historical_count_by_page[key]
            page_rows.append(
                PageAblationRow(
                    profile=profile,
                    score=record.score,
                    page=record.page,
                    historical_count=hist_count,
                    raw_count=len(raw_by_page[key]),
                    kept_count=kept_count,
                    kept_to_historical_ratio=(kept_count / hist_count) if hist_count else None,
                )
            )
        summary_rows.append(
            ProfileSummaryRow(
                profile=profile,
                pages=len(records),
                raw_total=raw_total,
                kept_total=kept_total,
                dropped_total=dropped_total,
                kept_ratio=kept_total / raw_total if raw_total else 0.0,
                empty_pages=empty_pages,
                historical_total=historical_total,
                kept_minus_historical=kept_total - historical_total,
                kept_to_historical_ratio=(kept_total / historical_total)
                if historical_total
                else None,
                overrides=json.dumps(PROFILES[profile], sort_keys=True),
            )
        )
    return summary_rows, page_rows


def render_markdown(
    summary_rows: list[ProfileSummaryRow],
    page_rows: list[PageAblationRow],
    args: argparse.Namespace,
) -> str:
    lines = [
        "# Issue 120 Stage-C filter ablation summary",
        "",
        f"Regeneration root: `{args.regen_root}`",
        f"Inventory: `{args.inventory}`",
        f"Historical root: `{args.historical_root}`",
        "",
        "## Profile totals",
        "",
        "| profile | raw total | kept total | historical total | kept/historical | empty pages | overrides |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in summary_rows:
        ratio = (
            "" if row.kept_to_historical_ratio is None else f"{row.kept_to_historical_ratio:.3f}"
        )
        lines.append(
            f"| {row.profile} | {row.raw_total} | {row.kept_total} | {row.historical_total} | "
            f"{ratio} | {row.empty_pages} | `{row.overrides}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation guide",
            "",
            "- If `paper_overlap_0` restores candidate volume, `low_paper_overlap` is the active regression gate.",
            "- If `paper_overlap_0` still stays low but `paper_staff_0` restores volume, staff overlap is the second blocking gate.",
            "- If only `all_spatial_relaxed` restores volume, multiple current filters are incompatible with the regenerated candidate family.",
            "- A restored count much larger than historical means the filter relaxation is diagnostic only, not a proposed repair.",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regen-root", type=Path, default=DEFAULT_REGEN_ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--historical-root", type=Path, default=DEFAULT_HISTORICAL_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--profiles", nargs="*", choices=sorted(PROFILES.keys()))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary_rows, page_rows = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(summary_rows, args.output_dir / "stage_c_filter_ablation_summary.csv")
    write_csv(page_rows, args.output_dir / "stage_c_filter_ablation_pages.csv")
    markdown = render_markdown(summary_rows, page_rows, args)
    (args.output_dir / "stage_c_filter_ablation_summary.md").write_text(
        markdown + "\n", encoding="utf-8"
    )
    print(markdown)
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
