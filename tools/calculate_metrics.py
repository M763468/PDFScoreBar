import argparse
import json
import sys
from pathlib import Path
from tqdm import tqdm

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match

def find_scored_file(scored_root, subdir, page_name):
    candidates = [
        Path(scored_root) / "eval2_v9_final" / subdir / "intermediate" / "probe_scan" / f"eval2_{page_name}_{page_name}" / "pipeline2_no_peak_scored.json",
        Path(scored_root) / "eval2_v9_final" / subdir / "intermediate" / "probe_scan" / f"eval2_{subdir}_{page_name}" / "pipeline2_no_peak_scored.json",
        Path(scored_root) / "eval2_v9_final" / subdir / "outputs" / page_name / "pipeline2_no_peak_scored.json",
        Path(scored_root) / subdir / page_name / "pipeline2_no_peak_scored.json",
        Path(scored_root) / f"eval2_{subdir}_{page_name}" / "pipeline2_no_peak_scored.json",
        Path(scored_root) / subdir / "intermediate" / "probe_scan" / f"eval2_{subdir}_{page_name}" / "pipeline2_no_peak_scored.json",
        Path(scored_root) / subdir / "intermediate" / "probe_scan" / f"eval2_{page_name}_{page_name}" / "pipeline2_no_peak_scored.json",
        Path(scored_root) / "intermediate" / "probe_scan" / f"eval2_{page_name}_{page_name}" / "pipeline2_no_peak_scored.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--eval-rule", default="center_anchor")
    args = parser.parse_args()

    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_gt = 0
    total_pred = 0

    if (Path(args.gt_root) / "page_001").exists():
        subdirs = [Path(args.gt_root).name]
        gt_parent = Path(args.gt_root).parent
    else:
        subdirs = sorted([d.name for d in Path(args.gt_root).iterdir() if d.is_dir()])
        gt_parent = Path(args.gt_root)

    for subdir in tqdm(subdirs, desc="Scores"):
        page_dirs = sorted([d for d in (gt_parent / subdir).iterdir() if d.is_dir()])
        
        score_tp = 0
        score_fp = 0
        score_fn = 0
        score_gt = 0
        score_pages = 0

        for page_dir in page_dirs:
            page_name = page_dir.name
            gt_candidates = sorted(list(page_dir.glob("boxes_sorted*.json")), reverse=True)
            if not gt_candidates:
                continue
            
            scored_path = find_scored_file(args.scored_root, subdir, page_name)
            if not scored_path:
                continue # Skip pages that were not processed yet
            
            gt_file = gt_candidates[0]
            with open(gt_file, "r") as f:
                gt_data = json.load(f)
                gt_boxes = [tuple(b["barline_location"]) for b in gt_data if "barline_location" in b]

            with open(scored_path, "r") as f:
                candidates = json.load(f)

            accepted_candidates = [tuple(c["bbox"]) for c in candidates if c["score"] >= args.threshold]

            res = greedy_barline_match(accepted_candidates, gt_boxes, rule_name=args.eval_rule)
            
            tp = len(res.matches)
            fp = len(res.false_positive_indices)
            fn = len(res.false_negative_indices)
            
            score_tp += tp
            score_fp += fp
            score_fn += fn
            score_gt += len(gt_boxes)
            score_pages += 1

        if score_pages > 0:
            precision = score_tp / (score_tp + score_fp) if (score_tp + score_fp) > 0 else 0
            recall = score_tp / (score_tp + score_fn) if (score_tp + score_fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            print(f"\nScore: {subdir}")
            print(f"  Pages: {score_pages}")
            print(f"  TP: {score_tp}, FP: {score_fp}, FN: {score_fn}, GT: {score_gt}")
            print(f"  Precision: {precision:.4f}, Recall: {recall:.4f}, F1: {f1:.4f}")
            
            total_tp += score_tp
            total_fp += score_fp
            total_fn += score_fn
            total_gt += score_gt

    if total_tp + total_fp + total_fn > 0:
        total_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        total_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        total_f1 = 2 * total_precision * total_recall / (total_precision + total_recall) if (total_precision + total_recall) > 0 else 0
        
        print("\n" + "="*30)
        print("AGGREGATE METRICS")
        print("="*30)
        print(f"Total TP: {total_tp}")
        print(f"Total FP: {total_fp}")
        print(f"Total FN: {total_fn}")
        print(f"Total GT: {total_gt}")
        print(f"Overall Precision: {total_precision:.4f}")
        print(f"Overall Recall: {total_recall:.4f}")
        print(f"Overall F1: {total_f1:.4f}")

if __name__ == "__main__":
    main()
