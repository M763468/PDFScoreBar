#!/usr/bin/env python3
"""Rescore retained final Stage-E accepted barlines against corrected Issue #291 GT.

This helper is retained-artifact only. It does not rerun HOMR, SR, OMR-DLN,
dense candidate generation/filtering, CNN, MMR, OCR, or numbering.

The Issue #284 full68 comparator intentionally reports ``hybrid_vs_gt`` before
dense reconstruction/probe rescue/CNN. This helper closes the separate final
Stage-E detector gate by reading the already-retained
``pipeline2_no_peak_filtered_cnn.json`` files and matching them against the
canonical GT currently present in the working tree.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import greedy_barline_match
from tools.issue120.eval_full68_from_intermediates import SCORES

Box = tuple[int, int, int, int]
EXPECTED_PAGE_COUNT = 68
EXPECTED_CORRECTED_GT = 3567
ACCEPTED_FILENAME = "pipeline2_no_peak_filtered_cnn.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_box(raw: Sequence[Any]) -> Box:
    if len(raw) < 4:
        raise ValueError(f"Invalid bbox: {raw!r}")
    return tuple(int(round(float(value))) for value in raw[:4])  # type: ignore[return-value]


def extract_box(item: Any) -> Box | None:
    if isinstance(item, (list, tuple)) and len(item) >= 4:
        return normalize_box(item)
    if not isinstance(item, Mapping):
        return None
    for key in ("orig_bbox", "bbox", "pred_bbox", "box", "barline_location"):
        value = item.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            return normalize_box(value)
    return None


def records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in ("predictions", "boxes", "detections"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def load_boxes(path: Path) -> list[Box]:
    boxes = [
        box
        for box in (extract_box(item) for item in records_from_payload(load_json(path)))
        if box is not None
    ]
    return boxes


def load_gt(path: Path) -> list[Box]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected GT list: {path}")
    boxes: list[Box] = []
    for row in payload:
        box = extract_box(row)
        if box is None:
            raise ValueError(f"GT row lacks a bbox in {path}: {row!r}")
        boxes.append(box)
    return boxes


def canonical_pages() -> list[tuple[str, str]]:
    return [(str(score), str(page)) for score, pages in SCORES.items() for page in pages]


def index_accepted_artifacts(root: Path) -> dict[str, Path]:
    """Index retained final accepted files by their eval2_<score>_<page> directory."""
    matches: dict[str, list[Path]] = {}
    for path in root.rglob(ACCEPTED_FILENAME):
        if path.parent.name.startswith("eval2_"):
            matches.setdefault(path.parent.name, []).append(path)

    index: dict[str, Path] = {}
    for score, page in canonical_pages():
        key = f"eval2_{score}_{page}"
        paths = sorted(matches.get(key, []))
        if len(paths) != 1:
            rendered = ", ".join(str(path) for path in paths) or "<none>"
            raise FileNotFoundError(
                f"Expected exactly one retained accepted artifact for {score}/{page} "
                f"under {root}; found {len(paths)}: {rendered}"
            )
        index[key] = paths[0]
    return index


def page_metrics(predictions: Sequence[Box], gt: Sequence[Box]) -> dict[str, Any]:
    result = greedy_barline_match(
        predictions,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    tp = len(result.matches)
    fp = len(result.false_positive_indices)
    fn = len(result.false_negative_indices)
    return {
        "gt": len(gt),
        "pred": len(predictions),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "soft_duplicate_or_repeat_like": len(result.soft_matches),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_negative_indices": list(result.false_negative_indices),
        "false_negative_boxes": [list(gt[index]) for index in result.false_negative_indices],
        "false_positive_indices": list(result.false_positive_indices),
        "false_positive_boxes": [
            list(predictions[index]) for index in result.false_positive_indices
        ],
    }


def aggregate(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    for row in rows:
        for key in ("gt", "pred", "tp", "fp", "fn", "soft_duplicate_or_repeat_like"):
            totals[key] += int(row[key])
    tp = totals["tp"]
    fp = totals["fp"]
    fn = totals["fn"]
    return {
        **dict(totals),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    control_root = args.control.resolve()
    candidate_root = args.candidate.resolve()
    control_index = index_accepted_artifacts(control_root)
    candidate_index = index_accepted_artifacts(candidate_root)

    pages = canonical_pages()
    if len(pages) != EXPECTED_PAGE_COUNT:
        raise RuntimeError(
            f"Canonical page inventory drifted: expected {EXPECTED_PAGE_COUNT}, got {len(pages)}"
        )

    rows: list[dict[str, Any]] = []
    control_metrics_rows: list[dict[str, Any]] = []
    candidate_metrics_rows: list[dict[str, Any]] = []

    for score, page in pages:
        key = f"eval2_{score}_{page}"
        gt_path = PROJECT_ROOT / "data/evaluation2/annotations" / score / page / "boxes_sorted.json"
        gt = load_gt(gt_path)
        control_path = control_index[key]
        candidate_path = candidate_index[key]
        control_boxes = load_boxes(control_path)
        candidate_boxes = load_boxes(candidate_path)
        control_metrics = page_metrics(control_boxes, gt)
        candidate_metrics = page_metrics(candidate_boxes, gt)
        control_metrics_rows.append(control_metrics)
        candidate_metrics_rows.append(candidate_metrics)

        rows.append(
            {
                "score": score,
                "page": page,
                "gt_path": str(gt_path),
                "control_accepted": str(control_path),
                "candidate_accepted": str(candidate_path),
                "accepted_multiset_exact": sorted(control_boxes) == sorted(candidate_boxes),
                "metrics_exact": control_metrics == candidate_metrics,
                "control": control_metrics,
                "candidate": candidate_metrics,
            }
        )

    control_aggregate = aggregate(control_metrics_rows)
    candidate_aggregate = aggregate(candidate_metrics_rows)
    accepted_multiset_exact_pages = sum(row["accepted_multiset_exact"] for row in rows)
    metric_exact_pages = sum(row["metrics_exact"] for row in rows)
    corrected_gt_total = sum(row["control"]["gt"] for row in rows)

    summary = {
        "schema_version": "issue291.corrected_gt_final_stage_e_rescore.v1",
        "execution_contract": {
            "retained_artifact_only": True,
            "reruns_inference": False,
            "stage": "final_stage_e_accepted_post_cnn",
            "matcher": {
                "rule_name": "center_anchor",
                "vov_threshold": 0.5,
                "xdist_threshold": 12.0,
            },
        },
        "control_root": str(control_root),
        "candidate_root": str(candidate_root),
        "page_count": len(rows),
        "corrected_gt_total": corrected_gt_total,
        "expected_corrected_gt_total": EXPECTED_CORRECTED_GT,
        "control": control_aggregate,
        "candidate": candidate_aggregate,
        "accepted_multiset_exact_pages": accepted_multiset_exact_pages,
        "metric_exact_pages": metric_exact_pages,
        "comparison_gate": {
            "all_68_pages": len(rows) == EXPECTED_PAGE_COUNT,
            "corrected_gt_total_is_3567": corrected_gt_total == EXPECTED_CORRECTED_GT,
            "accepted_outputs_exact_per_page": accepted_multiset_exact_pages == EXPECTED_PAGE_COUNT,
            "metrics_equal_per_page": metric_exact_pages == EXPECTED_PAGE_COUNT,
        },
        "pages_with_control_fn": [
            {"score": row["score"], "page": row["page"], "metrics": row["control"]}
            for row in rows
            if row["control"]["fn"]
        ],
        "pages_with_control_fp": [
            {"score": row["score"], "page": row["page"], "metrics": row["control"]}
            for row in rows
            if row["control"]["fp"]
        ],
        "pages": rows,
    }
    summary["comparison_gate"]["passed"] = all(summary["comparison_gate"].values())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    compact = {
        "page_count": summary["page_count"],
        "corrected_gt_total": summary["corrected_gt_total"],
        "control": control_aggregate,
        "candidate": candidate_aggregate,
        "accepted_multiset_exact_pages": accepted_multiset_exact_pages,
        "metric_exact_pages": metric_exact_pages,
        "comparison_gate": summary["comparison_gate"],
        "control_fn_pages": [
            f"{row['score']}/{row['page']}" for row in rows if row["control"]["fn"]
        ],
        "control_fp_pages": [
            f"{row['score']}/{row['page']}" for row in rows if row["control"]["fp"]
        ],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
