#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match

Box = Tuple[int, int, int, int]


def load_homr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    preds = []
    for entry in data.get("predictions", []):
        bbox = entry.get("orig_bbox") or entry.get("pred_bbox")
        if bbox and len(bbox) == 4:
            preds.append(tuple(map(int, bbox)))
    return preds


def load_omr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    return [tuple(map(int, box)) for box in data]


def load_gt_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    return [tuple(map(int, item["barline_location"])) for item in data]


def union_boxes(a: Sequence[Box], b: Sequence[Box]) -> List[Box]:
    seen = set(a)
    merged = list(a)
    for box in b:
        if box not in seen:
            merged.append(box)
            seen.add(box)
    return merged


def compute_metrics(preds: Sequence[Box], gt: Sequence[Box]) -> Dict[str, int]:
    match_result = greedy_barline_match(list(preds), list(gt))
    return {
        "tp": len(match_result.matches),
        "fp": len(match_result.false_positive_indices),
        "fn": len(match_result.false_negative_indices),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize OMR-DLN sweeps + homr union metrics.")
    parser.add_argument("--run-root", type=Path, required=True, help="Run root containing omr_dln outputs.")
    parser.add_argument(
        "--homr-root",
        type=Path,
        required=True,
        help="Homr run root containing <stem>_detections.json files.",
    )
    parser.add_argument(
        "--conf-values",
        nargs="+",
        required=True,
        help="Confidence values used for OMR-DLN sweep (e.g. 0.1 0.2 ...).",
    )
    parser.add_argument("--output-json", type=Path, required=True, help="Where to write summary JSON.")
    parser.add_argument("--output-md", type=Path, required=True, help="Where to write summary markdown table.")
    args = parser.parse_args()

    pages = [
        {
            "stem": "page_3",
            "gt": REPO_ROOT / "data/evaluation/annotations/page_003/boxes_sorted.json",
        },
        {
            "stem": "page_10",
            "gt": REPO_ROOT / "data/training/annotations/page_010/fn_only.json",
        },
        {
            "stem": "page_15",
            "gt": REPO_ROOT / "data/training/annotations/page_015/fn_only.json",
        },
        {
            "stem": "page_001",
            "gt": REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json",
        },
        {
            "stem": "page_004",
            "gt": REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json",
        },
    ]

    homr_predictions: Dict[str, List[Box]] = {}
    for page in pages:
        stem = page["stem"]
        homr_path = args.homr_root / stem / f"{stem}_detections.json"
        homr_predictions[stem] = load_homr_boxes(homr_path)

    summary: Dict[str, Dict[str, Dict[str, int]]] = {"omr_dln": {}, "union": {}}

    for conf in args.conf_values:
        conf_tag = conf.replace(".", "p")
        summary["omr_dln"][conf] = {}
        summary["union"][conf] = {}
        for page in pages:
            stem = page["stem"]
            gt = load_gt_boxes(page["gt"])
            omr_path = args.run_root / "omr_dln" / f"conf_{conf_tag}" / stem / "predictions.json"
            omr_preds = load_omr_boxes(omr_path)
            omr_metrics = compute_metrics(omr_preds, gt)
            summary["omr_dln"][conf][stem] = omr_metrics

            union_preds = union_boxes(homr_predictions[stem], omr_preds)
            union_metrics = compute_metrics(union_preds, gt)
            summary["union"][conf][stem] = union_metrics

    args.output_json.write_text(json.dumps(summary, indent=2))

    headers = [
        "Variant",
        "page_10 TP",
        "page_15 TP",
        "page_001 TP",
        "page_004 TP",
        "FN total",
        "page_3 FP",
        "Notes",
    ]

    def format_row(variant: str, metrics: Dict[str, Dict[str, int]]) -> List[str]:
        tp10 = metrics["page_10"]["tp"]
        tp15 = metrics["page_15"]["tp"]
        tp001 = metrics["page_001"]["tp"]
        tp004 = metrics["page_004"]["tp"]
        fn_total = (
            metrics["page_10"]["fn"]
            + metrics["page_15"]["fn"]
            + metrics["page_001"]["fn"]
            + metrics["page_004"]["fn"]
        )
        fp_page3 = metrics["page_3"]["fp"]
        return [
            variant,
            str(tp10),
            str(tp15),
            str(tp001),
            str(tp004),
            str(fn_total),
            str(fp_page3),
            "",
        ]

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for conf in args.conf_values:
        omr_row = format_row(f"omr-dln conf={conf}", summary["omr_dln"][conf])
        union_row = format_row(f"union(homr, omr-dln) conf={conf}", summary["union"][conf])
        lines.append("| " + " | ".join(omr_row) + " |")
        lines.append("| " + " | ".join(union_row) + " |")

    args.output_md.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
