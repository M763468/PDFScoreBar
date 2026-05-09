#!/usr/bin/env python3
"""Evaluate Issue #120 full-68 detector outputs from saved intermediates.

This tool intentionally does not run the full pipeline.  It evaluates an existing
intermediate result tree, validates that all canonical 68 pages are present, and
writes normalized metrics under an ignored output directory.

Default input layout matches the historical golden baseline tree:

    data/evaluation2/golden_baseline_eval2_bc23deb/
      eval2_<score>_<page>/pipeline2_no_peak_scored.json
      eval2_<score>_<page>/pipeline2_no_peak_candidates.json

Alternative common layouts are also accepted:

    <results-dir>/<score>/<page>/pipeline2_no_peak_scored.json
    <results-dir>/<score>/<page>/<scored-file>
    <results-dir>/eval2_<score>_<page>/<scored-file>
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import (  # noqa: E402
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)

# Canonical Issue #120 evaluation2 page set: 68 pages.
# This is the same page selection used by the previous full-restore config generator.
SCORES: dict[str, list[str]] = {
    "Shostakovich-Festival_Overture_Va": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
        "page_007",
        "page_008",
        "page_009",
    ],
    "Shostakovich-Sym5-Va": [
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
        "page_007",
        "page_008",
        "page_009",
        "page_010",
        "page_011",
        "page_012",
        "page_013",
        "page_014",
        "page_015",
        "page_016",
        "page_018",
        "page_019",
        "page_020",
        "page_021",
        "page_022",
        "page_024",
        "page_025",
    ],
    "Sibelius-Violin_Concerto-Viola": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
        "page_007",
        "page_008",
        "page_009",
        "page_010",
    ],
    "Va_Prokofiev_Symphony1": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
    ],
    "Va__Prokofiev_Symphony5": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_007",
        "page_008",
        "page_009",
        "page_010",
        "page_011",
        "page_013",
        "page_014",
        "page_015",
        "page_016",
        "page_017",
        "page_018",
        "page_019",
        "page_020",
        "page_021",
        "page_022",
        "page_023",
    ],
}


@dataclass(frozen=True)
class PageRecord:
    score: str
    page: str


@dataclass
class PageMetric:
    score: str
    page: str
    gt: int
    pred: int
    candidate_count: int | None
    tp: int
    fp: int
    fn: int
    fn_det: int | None
    fn_cnn: int | None
    precision: float | None
    recall: float | None
    scored_path: str
    candidates_path: str | None
    gt_path: str


@dataclass
class DetectorSummary:
    page_count: int
    expected_page_count: int
    gt: int
    pred: int
    candidate_count: int | None
    tp: int
    fp: int
    fn: int
    fn_det: int | None
    fn_cnn: int | None
    precision: float | None
    recall: float | None


@dataclass
class EvaluationContract:
    schema_version: str
    mode: str
    results_dir: str
    gt_root: str
    output_dir: str
    expected_pages: int
    evaluated_pages: int
    missing_pages: list[dict[str, str]]
    score_threshold: float
    rule_name: str
    vov_threshold: float
    xdist_threshold: float
    detector_summary: DetectorSummary
    measure_count_summary: dict[str, Any]


def iter_manifest() -> list[PageRecord]:
    return [PageRecord(score, page) for score, pages in SCORES.items() for page in pages]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_box(box: Sequence[Any]) -> tuple[int, int, int, int]:
    if len(box) < 4:
        raise ValueError(f"Invalid box: {box!r}")
    return tuple(int(round(float(v))) for v in box[:4])  # type: ignore[return-value]


def boxes_from_gt(payload: Any) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    if not isinstance(payload, list):
        raise ValueError("GT payload must be a list")
    for item in payload:
        if isinstance(item, list):
            boxes.append(normalize_box(item))
        elif isinstance(item, dict):
            if "barline_location" in item:
                boxes.append(normalize_box(item["barline_location"]))
            elif "box" in item:
                boxes.append(normalize_box(item["box"]))
            elif "bbox" in item:
                boxes.append(normalize_box(item["bbox"]))
    return boxes


def boxes_from_scored(payload: Any, *, score_threshold: float) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    if not isinstance(payload, list):
        raise ValueError("Scored payload must be a list")
    for item in payload:
        if isinstance(item, dict):
            if float(item.get("score", 0.0)) >= score_threshold and "bbox" in item:
                boxes.append(normalize_box(item["bbox"]))
        elif isinstance(item, list):
            # Filtered-CNN JSONs are sometimes plain box lists.  Treat them as already filtered.
            boxes.append(normalize_box(item))
    return boxes


def boxes_from_candidates(payload: Any) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    if not isinstance(payload, list):
        raise ValueError("Candidates payload must be a list")
    for item in payload:
        if isinstance(item, dict) and "bbox" in item:
            boxes.append(normalize_box(item["bbox"]))
        elif isinstance(item, list):
            boxes.append(normalize_box(item))
    return boxes


def find_page_file(
    root: Path,
    record: PageRecord,
    filename: str,
) -> Path | None:
    candidates = [
        root / f"eval2_{record.score}_{record.page}" / filename,
        root / record.score / record.page / filename,
        root / record.score / f"eval2_{record.score}_{record.page}" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def has_candidate_for_gt(
    candidates: Iterable[tuple[int, int, int, int]],
    gt: tuple[int, int, int, int],
    *,
    rule_name: str,
    vov_threshold: float,
    xdist_threshold: float,
) -> bool:
    return any(
        is_barline_match(
            cand,
            gt,
            rule_name=rule_name,
            vov_threshold=vov_threshold,
            xdist_threshold=xdist_threshold,
        )
        for cand in candidates
    )


def safe_div(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return num / den


def read_measure_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "status": "not_provided",
            "note": "Detector intermediate evaluation completed. Provide --measure-summary-json after a numbering run to attach downstream measure-count metrics.",
            "pred_measures": None,
            "gt_measures": None,
            "net_delta": None,
            "abs_delta_sum": None,
            "delta_pages": None,
            "precision": None,
            "recall": None,
        }
    if not path.exists():
        raise FileNotFoundError(f"Measure summary not found: {path}")
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Measure summary JSON must be an object")
    return {"status": "provided", "path": str(path), **payload}


def evaluate(args: argparse.Namespace) -> EvaluationContract:
    manifest = iter_manifest()
    results_dir = Path(args.results_dir)
    gt_root = Path(args.gt_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    page_metrics: list[PageMetric] = []
    missing_pages: list[dict[str, str]] = []

    for record in manifest:
        gt_path = gt_root / record.score / record.page / "boxes_sorted.json"
        scored_path = find_page_file(results_dir, record, args.scored_file)
        candidates_path = find_page_file(results_dir, record, args.candidates_file)

        missing_reasons: list[str] = []
        if not gt_path.exists():
            missing_reasons.append(f"missing_gt:{gt_path}")
        if scored_path is None:
            missing_reasons.append(f"missing_scored:{args.scored_file}")

        if missing_reasons:
            missing_pages.append(
                {"score": record.score, "page": record.page, "reason": ";".join(missing_reasons)}
            )
            continue

        assert scored_path is not None
        gts = boxes_from_gt(load_json(gt_path))
        preds = boxes_from_scored(load_json(scored_path), score_threshold=args.score_threshold)

        match_result = greedy_barline_match(
            preds,
            gts,
            rule_name=args.rule_name,
            vov_threshold=args.vov_threshold,
            xdist_threshold=args.xdist_threshold,
        )

        candidate_boxes: list[tuple[int, int, int, int]] | None = None
        fn_det: int | None = None
        fn_cnn: int | None = None
        if candidates_path is not None and candidates_path.exists():
            candidate_boxes = boxes_from_candidates(load_json(candidates_path))
            fn_det = 0
            fn_cnn = 0
            for gt_index in match_result.false_negative_indices:
                gt = gts[gt_index]
                if has_candidate_for_gt(
                    candidate_boxes,
                    gt,
                    rule_name=args.rule_name,
                    vov_threshold=args.vov_threshold,
                    xdist_threshold=args.xdist_threshold,
                ):
                    fn_cnn += 1
                else:
                    fn_det += 1

        tp = len(match_result.matches)
        fp = len(match_result.false_positive_indices)
        fn = len(match_result.false_negative_indices)
        page_metrics.append(
            PageMetric(
                score=record.score,
                page=record.page,
                gt=len(gts),
                pred=len(preds),
                candidate_count=len(candidate_boxes) if candidate_boxes is not None else None,
                tp=tp,
                fp=fp,
                fn=fn,
                fn_det=fn_det,
                fn_cnn=fn_cnn,
                precision=safe_div(tp, tp + fp),
                recall=safe_div(tp, tp + fn),
                scored_path=str(scored_path),
                candidates_path=str(candidates_path) if candidates_path else None,
                gt_path=str(gt_path),
            )
        )

    if missing_pages and not args.allow_partial:
        (output_dir / "missing_pages.json").write_text(
            json.dumps(missing_pages, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        raise SystemExit(
            f"Missing {len(missing_pages)} of {len(manifest)} canonical pages. See {output_dir / 'missing_pages.json'}"
        )

    total_gt = sum(m.gt for m in page_metrics)
    total_pred = sum(m.pred for m in page_metrics)
    total_candidates: int | None = None
    if all(m.candidate_count is not None for m in page_metrics):
        total_candidates = sum(int(m.candidate_count or 0) for m in page_metrics)
    total_tp = sum(m.tp for m in page_metrics)
    total_fp = sum(m.fp for m in page_metrics)
    total_fn = sum(m.fn for m in page_metrics)
    total_fn_det: int | None = None
    total_fn_cnn: int | None = None
    if all(m.fn_det is not None and m.fn_cnn is not None for m in page_metrics):
        total_fn_det = sum(int(m.fn_det or 0) for m in page_metrics)
        total_fn_cnn = sum(int(m.fn_cnn or 0) for m in page_metrics)

    detector_summary = DetectorSummary(
        page_count=len(page_metrics),
        expected_page_count=len(manifest),
        gt=total_gt,
        pred=total_pred,
        candidate_count=total_candidates,
        tp=total_tp,
        fp=total_fp,
        fn=total_fn,
        fn_det=total_fn_det,
        fn_cnn=total_fn_cnn,
        precision=safe_div(total_tp, total_tp + total_fp),
        recall=safe_div(total_tp, total_tp + total_fn),
    )

    contract = EvaluationContract(
        schema_version="issue120.full68.v1",
        mode="intermediate_detector_eval",
        results_dir=str(results_dir),
        gt_root=str(gt_root),
        output_dir=str(output_dir),
        expected_pages=len(manifest),
        evaluated_pages=len(page_metrics),
        missing_pages=missing_pages,
        score_threshold=args.score_threshold,
        rule_name=args.rule_name,
        vov_threshold=args.vov_threshold,
        xdist_threshold=args.xdist_threshold,
        detector_summary=detector_summary,
        measure_count_summary=read_measure_summary(args.measure_summary_json),
    )

    write_outputs(output_dir, manifest, page_metrics, contract)
    return contract


def write_outputs(
    output_dir: Path,
    manifest: list[PageRecord],
    page_metrics: list[PageMetric],
    contract: EvaluationContract,
) -> None:
    (output_dir / "manifest.json").write_text(
        json.dumps([asdict(item) for item in manifest], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "detector_metrics.json").write_text(
        json.dumps(asdict(contract.detector_summary), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "evaluation_contract.json").write_text(
        json.dumps(asdict(contract), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with (output_dir / "detector_page_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(page_metrics[0]).keys()) if page_metrics else [])
        if page_metrics:
            writer.writeheader()
            for row in page_metrics:
                writer.writerow(asdict(row))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        default="data/evaluation2/golden_baseline_eval2_bc23deb",
        help="Root directory containing saved scored/candidate intermediates.",
    )
    parser.add_argument(
        "--gt-root",
        default="data/evaluation2/annotations",
        help="Root directory containing evaluation2 GT annotations.",
    )
    parser.add_argument(
        "--output-dir",
        default="logs/issue120_e2e_recovery/latest_full_report",
        help="Ignored output directory for normalized metrics.",
    )
    parser.add_argument("--scored-file", default="pipeline2_no_peak_scored.json")
    parser.add_argument("--candidates-file", default="pipeline2_no_peak_candidates.json")
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--rule-name", default="center_anchor", choices=["center_anchor", "baseline_iou"])
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write partial metrics instead of failing when canonical pages are missing.",
    )
    parser.add_argument(
        "--measure-summary-json",
        type=Path,
        default=None,
        help="Optional downstream measure-count summary JSON to attach to the contract.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    contract = evaluate(args)
    summary = contract.detector_summary
    print("Issue #120 full-68 intermediate evaluation")
    print(f"Pages: {summary.page_count}/{summary.expected_page_count}")
    print(
        "Detector: "
        f"GT={summary.gt} Pred={summary.pred} TP={summary.tp} FP={summary.fp} FN={summary.fn} "
        f"FN_det={summary.fn_det} FN_cnn={summary.fn_cnn} "
        f"Precision={summary.precision:.6f if summary.precision is not None else 'n/a'} "
        f"Recall={summary.recall:.6f if summary.recall is not None else 'n/a'}"
    )
    print(f"Wrote: {contract.output_dir}")


if __name__ == "__main__":
    main()
