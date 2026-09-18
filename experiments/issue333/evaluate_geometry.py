#!/usr/bin/env python3
"""Evaluate the frozen Phase 1 geometry rule on development and holdout scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median


DEV_ROOT = Path("logs/issue333/fresh/runs")
HOLDOUT_ROOT = Path("logs/issue333/phase2/runs")
HOLDOUT = {"beethoven9", "toy_symphony"}


def artifact_path(score: str, page_id: str) -> Path:
    if score in HOLDOUT:
        root = HOLDOUT_ROOT / f"issue333_phase2_{score}"
    else:
        root = DEV_ROOT / score
    return root / "intermediate" / page_id / "numbering_base.json"


def locations(fixture: dict) -> tuple[set[tuple[str, str, int]], dict]:
    ground_truth = {
        (item["score"], item["page_id"], item["system"])
        for item in fixture["boundaries"]
    }
    pages = {}
    for source in fixture["sources"]:
        score = source["score"]
        for source_page in source["evaluated_pages"]:
            page_id = f"page_{source_page + 1:03d}"
            path = artifact_path(score, page_id)
            payload = json.loads(path.read_text(encoding="utf-8"))["pages"][0]
            pages[(score, page_id)] = payload
    return ground_truth, pages


def predict(pages: dict) -> tuple[set[tuple[str, str, int]], list[dict]]:
    predicted = set()
    evidence = []
    for (score, page_id), page in pages.items():
        boxes = [system["staves"][0]["bbox"] for system in page["systems"]]
        if not boxes:
            continue
        left_median = median(box[0] for box in boxes)
        gaps = [boxes[index][1] - boxes[index - 1][3] for index in range(1, len(boxes))]
        gap_median = median(gaps) if gaps else None
        for index, box in enumerate(boxes):
            indent_ratio = (box[0] - left_median) / page["width"]
            gap = gaps[index - 1] if index else None
            gap_ratio = gap / gap_median if gap is not None and gap_median else None
            signals = []
            if indent_ratio >= 0.02:
                signals.append("relative_indent")
            if gap_ratio is not None and gap_ratio >= 1.75:
                signals.append("whitespace_outlier")
            if signals:
                location = (score, page_id, index)
                predicted.add(location)
                evidence.append(
                    {
                        "score": score,
                        "page_id": page_id,
                        "system": index,
                        "signals": signals,
                        "indent_ratio": round(indent_ratio, 6),
                        "gap_ratio": round(gap_ratio, 6) if gap_ratio is not None else None,
                    }
                )
    return predicted, evidence


def metrics(predicted: set, truth: set, universe: set) -> dict:
    true_positive = predicted & truth
    false_reset = predicted - truth
    missed = truth - predicted
    return {
        "system_starts": len(universe),
        "true_boundaries": len(truth),
        "candidates": len(predicted),
        "true_positive": len(true_positive),
        "false_reset": len(false_reset),
        "missed_boundary": len(missed),
        "precision": round(len(true_positive) / len(predicted), 6) if predicted else None,
        "recall": round(len(true_positive) / len(truth), 6) if truth else None,
        "review_burden": round(len(predicted) / len(universe), 6),
        "false_reset_locations": sorted(false_reset),
        "missed_boundary_locations": sorted(missed),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    truth, pages = locations(fixture)
    predicted, evidence = predict(pages)
    universe = {
        (score, page_id, index)
        for (score, page_id), page in pages.items()
        for index in range(len(page["systems"]))
    }
    splits = {
        "development": set(universe) - {item for item in universe if item[0] in HOLDOUT},
        "holdout": {item for item in universe if item[0] in HOLDOUT},
        "all": set(universe),
    }
    report = {
        "schema_version": "issue333.experiment_result.v1",
        "experiment_id": "phase2-frozen-geometry-v1",
        "hypothesis": "The Phase 1 geometry rule generalizes as a high-recall, low-burden candidate generator.",
        "parameters": {
            "relative_indent_min_page_ratio": 0.02,
            "preceding_gap_min_page_median_ratio": 1.75,
            "selection_provenance": "Phase 1; unchanged before holdout evaluation",
        },
        "metrics": {
            name: metrics(predicted & subset, truth & subset, subset)
            for name, subset in splits.items()
        },
        "per_score": {
            score: metrics(
                {item for item in predicted if item[0] == score},
                {item for item in truth if item[0] == score},
                {item for item in universe if item[0] == score},
            )
            for score in sorted({item[0] for item in universe})
        },
        "evidence": evidence,
        "interpretation": None,
        "disposition": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
