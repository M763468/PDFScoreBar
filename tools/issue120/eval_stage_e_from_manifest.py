#!/usr/bin/env python3
"""Fast Stage E evaluator that reads scored paths directly from the pipeline manifest.

Avoids directory traversal on large probe_scan directories by using the manifest
to locate each page's scored/candidates JSON files directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import greedy_barline_match, is_barline_match

# Canonical Issue #120 evaluation2 page set: 68 pages.
SCORES: dict[str, list[str]] = {
    "Shostakovich-Festival_Overture_Va": [f"page_{i:03d}" for i in range(1, 10)],
    "Shostakovich-Sym5-Va": [
        f"page_{i:03d}"
        for i in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 21, 22, 24, 25]
    ],
    "Sibelius-Violin_Concerto-Viola": [f"page_{i:03d}" for i in range(1, 11)],
    "Va_Prokofiev_Symphony1": [f"page_{i:03d}" for i in range(1, 7)],
    "Va__Prokofiev_Symphony5": [
        f"page_{i:03d}"
        for i in [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
    ],
}


def normalize_box(box):
    return tuple(int(round(float(v))) for v in box[:4])


def boxes_from_gt(payload):
    boxes = []
    for item in payload:
        if isinstance(item, list):
            boxes.append(normalize_box(item))
        elif isinstance(item, dict):
            for key in ("barline_location", "box", "bbox"):
                if key in item:
                    boxes.append(normalize_box(item[key]))
                    break
    return boxes


def boxes_from_scored(payload, score_threshold=0.1):
    boxes = []
    for item in payload:
        if isinstance(item, dict):
            if float(item.get("score", 0.0)) >= score_threshold and "bbox" in item:
                boxes.append(normalize_box(item["bbox"]))
        elif isinstance(item, list):
            boxes.append(normalize_box(item))
    return boxes


def boxes_from_candidates(payload):
    boxes = []
    for item in payload:
        if isinstance(item, dict) and "bbox" in item:
            boxes.append(normalize_box(item["bbox"]))
        elif isinstance(item, list):
            boxes.append(normalize_box(item))
    return boxes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Path to the pipeline manifest.json"
    )
    parser.add_argument("--gt-root", type=Path, default="data/evaluation2/annotations")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default="logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector",
    )
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--rule-name", default="center_anchor")
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    pages = manifest.get("pages", [])

    # Build mapping: image_stem -> pipeline page data
    # Image stems are like "Shostakovich-Festival_Overture_Va_page_001"
    page_map: dict[tuple[str, str], dict] = {}
    for p in pages:
        img_path = p.get("image_path", "")
        stem = Path(img_path).stem  # e.g. "Shostakovich-Festival_Overture_Va_page_001"
        # Split into score and page
        idx = stem.rfind("_page_")
        if idx < 0:
            continue
        score = stem[:idx]
        page = f"page_{stem[idx + 6 :]}"
        page_map[(score, page)] = p

    total_tp = total_fp = total_fn = 0
    total_gt = total_pred = 0
    total_fn_det = total_fn_cnn = 0
    has_candidates = True
    missing = []
    page_results = []

    for score, page_list in SCORES.items():
        for page in page_list:
            pdata = page_map.get((score, page))
            if pdata is None:
                missing.append({"score": score, "page": page, "reason": "not_in_manifest"})
                continue

            gt_path = args.gt_root / score / page / "boxes_sorted.json"
            if not gt_path.exists():
                missing.append({"score": score, "page": page, "reason": f"missing_gt:{gt_path}"})
                continue

            # Get barlines_json (scored) path from manifest
            barlines_path_str = pdata.get("barlines_json", "")
            if not barlines_path_str:
                missing.append({"score": score, "page": page, "reason": "no_barlines_json"})
                continue

            barlines_path = Path(barlines_path_str)
            # Use barlines_json directly (pipeline2_no_peak_filtered_cnn.json)
            # as the final detection output.
            scored_path = barlines_path  # filtered_cnn is the final output
            candidates_path = barlines_path.parent / "pipeline2_no_peak_candidates.json"

            if not scored_path.exists():
                missing.append(
                    {"score": score, "page": page, "reason": f"missing_scored:{scored_path}"}
                )
                continue

            gts = boxes_from_gt(json.loads(gt_path.read_text()))
            scored_data = json.loads(scored_path.read_text())
            # filtered_cnn is a list of plain bbox arrays (already filtered), not scored dicts
            preds = boxes_from_scored(scored_data, score_threshold=args.score_threshold)

            match_result = greedy_barline_match(
                preds,
                gts,
                rule_name=args.rule_name,
                vov_threshold=args.vov_threshold,
                xdist_threshold=args.xdist_threshold,
            )

            tp = len(match_result.matches)
            fp = len(match_result.false_positive_indices)
            fn = len(match_result.false_negative_indices)

            fn_det = fn_cnn = 0
            if candidates_path.exists():
                cand_boxes = boxes_from_candidates(json.loads(candidates_path.read_text()))
                for gt_idx in match_result.false_negative_indices:
                    gt = gts[gt_idx]
                    if any(
                        is_barline_match(
                            c,
                            gt,
                            rule_name=args.rule_name,
                            vov_threshold=args.vov_threshold,
                            xdist_threshold=args.xdist_threshold,
                        )
                        for c in cand_boxes
                    ):
                        fn_cnn += 1
                    else:
                        fn_det += 1
            else:
                has_candidates = False

            total_tp += tp
            total_fp += fp
            total_fn += fn
            total_fn_det += fn_det
            total_fn_cnn += fn_cnn
            total_gt += len(gts)
            total_pred += len(preds)

            page_results.append(
                {
                    "score": score,
                    "page": page,
                    "gt": len(gts),
                    "pred": len(preds),
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "fn_det": fn_det,
                    "fn_cnn": fn_cnn,
                }
            )

    # Output
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else None
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else None

    summary = {
        "page_count": len(page_results),
        "expected_page_count": sum(len(v) for v in SCORES.values()),
        "gt": total_gt,
        "pred": total_pred,
        "tp": total_tp,
        "fp": total_fp,
        "fn": total_fn,
        "fn_det": total_fn_det if has_candidates else None,
        "fn_cnn": total_fn_cnn if has_candidates else None,
        "precision": precision,
        "recall": recall,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "detector_metrics.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    if missing:
        (args.output_dir / "missing_pages.json").write_text(
            json.dumps(missing, indent=2), encoding="utf-8"
        )
    (args.output_dir / "page_results.json").write_text(
        json.dumps(page_results, indent=2), encoding="utf-8"
    )

    print("=" * 60)
    print("Stage E Full Pipeline - Detector Evaluation")
    print("=" * 60)
    print(f"Pages:     {summary['page_count']}/{summary['expected_page_count']}")
    print(f"GT:        {total_gt}")
    print(f"Pred:      {total_pred}")
    print(f"TP:        {total_tp}")
    print(f"FP:        {total_fp}")
    print(f"FN:        {total_fn}")
    if has_candidates:
        print(f"  FN_det:  {total_fn_det}")
        print(f"  FN_cnn:  {total_fn_cnn}")
    print(f"Precision: {precision:.6f}" if precision is not None else "Precision: n/a")
    print(f"Recall:    {recall:.6f}" if recall is not None else "Recall:    n/a")
    print("=" * 60)

    if missing:
        print(
            f"\nWARNING: {len(missing)} missing pages. See {args.output_dir / 'missing_pages.json'}"
        )
        sys.exit(1)

    # Canonical target check
    CANONICAL = {"tp": 3565, "fp": 3, "fn": 2}
    match = (
        total_tp == CANONICAL["tp"] and total_fp == CANONICAL["fp"] and total_fn == CANONICAL["fn"]
    )
    if match:
        print(
            "\n✅ CANONICAL TARGET MET: "
            f"TP={CANONICAL['tp']}, FP={CANONICAL['fp']}, FN={CANONICAL['fn']}"
        )
    else:
        print("\n❌ CANONICAL TARGET NOT MET.")
        print(f"   Expected: TP={CANONICAL['tp']} FP={CANONICAL['fp']} FN={CANONICAL['fn']}")
        print(f"   Got:      TP={total_tp} FP={total_fp} FN={total_fn}")


if __name__ == "__main__":
    main()
