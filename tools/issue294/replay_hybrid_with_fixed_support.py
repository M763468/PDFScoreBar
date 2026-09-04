#!/usr/bin/env python3
"""Replay Issue #294 A/B baselines against identical current-x4/OMR support.

The support tree must come from one retained production-compatible run. For each
page this tool loads the same current-x4 HOMR detections and OMR-DLN predictions,
then changes only the authoritative baseline source: A pinned Stage-E vs B
maintained original-image HOMR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from src.common.barline_evaluation import greedy_barline_match
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes

PROJECT_ROOT = Path(__file__).resolve().parents[2]

Box = tuple[int, int, int, int]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_box(raw: Sequence[Any]) -> Box:
    if len(raw) < 4:
        raise ValueError(f"Invalid bbox: {raw!r}")
    return tuple(int(round(float(value))) for value in raw[:4])  # type: ignore[return-value]


def gt_boxes(path: Path) -> list[Box]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"GT payload must be a list: {path}")
    boxes: list[Box] = []
    for item in payload:
        if isinstance(item, dict):
            raw = item.get("bbox") or item.get("box") or item.get("barline_location")
            if raw is not None:
                boxes.append(normalize_box(raw))
        elif isinstance(item, list):
            boxes.append(normalize_box(item))
    return boxes


def hybrid_metrics(pred: list[Box], gt: list[Box]) -> dict[str, Any]:
    result = greedy_barline_match(
        pred,
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
        "pred": len(pred),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def _support_paths(support_root: Path, score: str, stem: str) -> dict[str, Path]:
    page_root = support_root / score / stem
    result_path = page_root / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError(result_path)
    result = load_json(result_path)
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise ValueError(f"Incomplete support result: {result_path}")
    if result.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError(f"Support result uses historical artifacts: {result_path}")
    if result.get("connector_complete") is not True:
        raise ValueError(f"Support result lacks connector semantics: {result_path}")

    artifacts = page_root / "artifacts"
    derived = {
        "result": result_path,
        "current_x4_homr": (
            artifacts / "current_homr" / "batch" / stem / f"{stem}_detections.json"
        ),
        "omr_dln": artifacts / "omr_sr" / stem / "predictions.json",
    }
    missing = [
        str(path) for name, path in derived.items() if name != "result" and not path.is_file()
    ]
    if missing:
        raise FileNotFoundError("Fixed support artifacts missing: " + ", ".join(missing))
    return derived


def _page_identity(image_raw: object) -> tuple[str, str]:
    image = Path(str(image_raw))
    if not image.name or not image.parent.name:
        raise ValueError(f"Cannot derive page identity from {image_raw!r}")
    return image.parent.name, image.stem


def _multiset_delta(left: list[Box], right: list[Box]) -> dict[str, Any]:
    left_counter = Counter(left)
    right_counter = Counter(right)
    return {
        "exact_multiset_equal": left_counter == right_counter,
        "left_only_exact_count": sum((left_counter - right_counter).values()),
        "right_only_exact_count": sum((right_counter - left_counter).values()),
    }


def compare_page(page: dict[str, Any], support_root: Path, output_root: Path) -> dict[str, Any]:
    score, stem = _page_identity(page.get("image"))
    a = page.get("A_pinned")
    b = page.get("B_maintained")
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError(f"A/B payload missing for {score}/{stem}")
    a_artifacts = a.get("artifacts")
    b_worker = b.get("worker")
    if not isinstance(a_artifacts, dict) or not isinstance(b_worker, dict):
        raise ValueError(f"A/B artifacts missing for {score}/{stem}")
    b_artifacts = b_worker.get("artifacts")
    if not isinstance(b_artifacts, dict):
        raise ValueError(f"B artifacts missing for {score}/{stem}")

    a_detection = Path(str(a_artifacts["detections"])).resolve()
    b_detection = Path(str(b_artifacts["detections"])).resolve()
    for path in (a_detection, b_detection):
        if not path.is_file():
            raise FileNotFoundError(path)

    support = _support_paths(support_root, score, stem)
    a_boxes = [tuple(box) for box in load_json_boxes(a_detection)]
    b_boxes = [tuple(box) for box in load_json_boxes(b_detection)]
    x4_boxes = [tuple(box) for box in load_json_boxes(support["current_x4_homr"])]
    omr_boxes = [tuple(box) for box in load_json_boxes(support["omr_dln"])]

    a_hybrid = [
        tuple(box)
        for box in apply_hybrid_consensus_filter(
            baseline_boxes=a_boxes,
            sr_boxes=x4_boxes,
            omr_boxes=omr_boxes,
        )
    ]
    b_hybrid = [
        tuple(box)
        for box in apply_hybrid_consensus_filter(
            baseline_boxes=b_boxes,
            sr_boxes=x4_boxes,
            omr_boxes=omr_boxes,
        )
    ]

    page_output = output_root / score / stem
    page_output.mkdir(parents=True, exist_ok=False)
    a_hybrid_path = page_output / "A_pinned_hybrid.json"
    b_hybrid_path = page_output / "B_maintained_hybrid.json"
    a_hybrid_path.write_text(json.dumps(a_hybrid, indent=2) + "\n", encoding="utf-8")
    b_hybrid_path.write_text(json.dumps(b_hybrid, indent=2) + "\n", encoding="utf-8")

    ground_truth_path = (
        PROJECT_ROOT / "data/evaluation2/annotations" / score / stem / "boxes_sorted.json"
    )
    ground_truth = gt_boxes(ground_truth_path) if ground_truth_path.is_file() else None
    exact_delta = _multiset_delta(a_hybrid, b_hybrid)
    intervariant = greedy_barline_match(
        b_hybrid,
        a_hybrid,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    return {
        "score": score,
        "page": stem,
        "support": {
            "result": str(support["result"]),
            "current_x4_homr": str(support["current_x4_homr"]),
            "current_x4_homr_sha256": sha256(support["current_x4_homr"]),
            "omr_dln": str(support["omr_dln"]),
            "omr_dln_sha256": sha256(support["omr_dln"]),
            "shared_by_A_and_B": True,
        },
        "baseline_counts": {"A": len(a_boxes), "B": len(b_boxes)},
        "hybrid_counts": {"A": len(a_hybrid), "B": len(b_hybrid)},
        "hybrid_delta": {
            **exact_delta,
            "matched_center_anchor": len(intervariant.matches),
            "B_false_positive_vs_A": len(intervariant.false_positive_indices),
            "B_false_negative_vs_A": len(intervariant.false_negative_indices),
            "coordinate_review_required": not exact_delta["exact_multiset_equal"],
        },
        "gt": (
            {
                "path": str(ground_truth_path),
                "A": hybrid_metrics(a_hybrid, ground_truth),
                "B": hybrid_metrics(b_hybrid, ground_truth),
            }
            if ground_truth is not None
            else None
        ),
        "outputs": {
            "A_hybrid": str(a_hybrid_path),
            "B_hybrid": str(b_hybrid_path),
        },
    }


def _aggregate_metrics(pages: list[dict[str, Any]], variant: str) -> dict[str, Any] | None:
    metrics = [
        page["gt"][variant]
        for page in pages
        if isinstance(page.get("gt"), dict) and isinstance(page["gt"].get(variant), dict)
    ]
    if len(metrics) != len(pages):
        return None
    totals = {
        name: sum(int(item[name]) for item in metrics) for name in ("gt", "pred", "tp", "fp", "fn")
    }
    tp = totals["tp"]
    fp = totals["fp"]
    fn = totals["fn"]
    return {
        **totals,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def run(summary_path: Path, support_root: Path, output_root: Path) -> dict[str, Any]:
    summary_path = summary_path.resolve()
    support_root = support_root.resolve()
    output_root = output_root.resolve()
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)
    if not support_root.is_dir():
        raise FileNotFoundError(support_root)
    if output_root.exists():
        raise FileExistsError(output_root)

    summary = load_json(summary_path)
    if not isinstance(summary, dict) or summary.get("status") != "completed":
        raise ValueError(f"Invalid A/B summary: {summary_path}")
    raw_pages = summary.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError("A/B summary has no pages")

    output_root.mkdir(parents=True, exist_ok=False)
    pages = [
        compare_page(page, support_root, output_root)
        for page in raw_pages
        if isinstance(page, dict)
    ]
    if len(pages) != len(raw_pages):
        raise ValueError("A/B summary contains invalid page entries")

    report = {
        "schema_version": "issue294.fixed_support_hybrid_replay.v1",
        "status": "completed",
        "same_original_summary": str(summary_path),
        "support_root": str(support_root),
        "support_contract": "same_current_x4_homr_and_omr_dln_for_A_and_B",
        "pages": pages,
        "aggregate_gt": {
            "A": _aggregate_metrics(pages, "A"),
            "B": _aggregate_metrics(pages, "B"),
        },
        "gates": {
            "all_support_shared": all(page["support"]["shared_by_A_and_B"] for page in pages),
            "hybrid_multiset_exact_all_pages": all(
                page["hybrid_delta"]["exact_multiset_equal"] for page in pages
            ),
            "coordinate_review_pages": [
                f"{page['score']}/{page['page']}"
                for page in pages
                if page["hybrid_delta"]["coordinate_review_required"]
            ],
        },
    }
    report_path = output_root / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--support-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.summary, args.support_root, args.output_root)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str((args.output_root.resolve() / "report.json")),
                "gates": report["gates"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
