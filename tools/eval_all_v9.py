import json
import sys
from pathlib import Path

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

# Import greedy_barline_match
try:
    from src.common.barline_evaluation import greedy_barline_match
except ImportError:
    # Fallback if path setup is tricky
    sys.path.append(str(REPO_ROOT / "src"))
    from common.barline_evaluation import greedy_barline_match

PDFS = [
    "Shostakovich-Festival_Overture_Va",
    "Shostakovich-Sym5-Va",
    "Sibelius-Violin_Concerto-Viola",
    "Va_Prokofiev_Symphony1",
    "Va__Prokofiev_Symphony5",
]

SCORED_ROOT = REPO_ROOT / "logs/full_pipeline_runs/sr_x2_test/eval2_v9_no_heuristics_v1"
GT_ROOT = REPO_ROOT / "data/evaluation2/annotations"


def eval_pdf(pdf_name):
    pdf_dir = SCORED_ROOT / pdf_name
    probe_scan_dir = pdf_dir / "intermediate/probe_scan"

    if not probe_scan_dir.exists():
        print(f"Skipping {pdf_name}: No probe_scan dir found at {probe_scan_dir}")
        return None

    stats = []

    # Folders are named like eval2_page_001_page_001
    for page_dir in sorted(probe_scan_dir.iterdir()):
        if not page_dir.is_dir():
            continue

        # Parse page number
        parts = page_dir.name.split("_")
        if "page" not in parts:
            continue
        # Find the first index of "page"
        page_idx = parts.index("page")
        page_num_str = parts[page_idx + 1]
        page_name = f"page_{page_num_str}"

        pred_path = page_dir / "pipeline2_no_peak_filtered_cnn.json"
        if not pred_path.exists():
            continue

        # GT path
        gt_dir = GT_ROOT / pdf_name / page_name
        gt_path = gt_dir / "boxes_sorted.json"

        if not gt_path.exists():
            # Try recursive glob for boxes_sorted*.json
            candidates = list(gt_dir.glob("boxes_sorted*.json"))
            if candidates:
                candidates.sort(reverse=True)
                gt_path = candidates[0]

        if not gt_path.exists():
            print(f"  GT not found for {pdf_name}/{page_name} at {gt_dir}")
            continue

        with open(pred_path, "r") as f:
            preds = json.load(f)
        with open(gt_path, "r") as f:
            gt_data = json.load(f)

        # Extract bboxes
        # The filtered_cnn.json is a list of lists [x1, y1, x2, y2]
        pred_bboxes = [tuple(p) for p in preds]
        gt_bboxes = []
        for x in gt_data:
            if isinstance(x, list):
                gt_bboxes.append(tuple(x[:4]))
            elif isinstance(x, dict):
                box = x.get("box") or x.get("barline_location")
                if box:
                    gt_bboxes.append(tuple(box))

        match_result = greedy_barline_match(
            pred_bboxes, gt_bboxes, rule_name="baseline_iou", iou_threshold=0.5
        )

        tp = len(match_result.matches)
        fp = len(match_result.false_positive_indices)
        fn = len(match_result.false_negative_indices)

        stats.append({"page": page_name, "tp": tp, "fp": fp, "fn": fn, "gt": len(gt_bboxes)})

    return stats


def main():
    overall = []
    for pdf in PDFS:
        print(f"Evaluating {pdf}...")
        stats = eval_pdf(pdf)
        if stats:
            pdf_tp = sum(s["tp"] for s in stats)
            pdf_fp = sum(s["fp"] for s in stats)
            pdf_fn = sum(s["fn"] for s in stats)
            pdf_gt = sum(s["gt"] for s in stats)
            recall = pdf_tp / pdf_gt if pdf_gt > 0 else 0
            prec = pdf_tp / (pdf_tp + pdf_fp) if (pdf_tp + pdf_fp) > 0 else 0
            print(
                f"  Result: TP={pdf_tp}, FP={pdf_fp}, FN={pdf_fn}, Recall={recall:.1%}, Prec={prec:.1%}"
            )
            overall.append({"name": pdf, "tp": pdf_tp, "fp": pdf_fp, "fn": pdf_fn, "gt": pdf_gt})

    if not overall:
        print("No results to display.")
        return

    print("\n" + "=" * 90)
    print(f"{'PDF':<45} | {'TP':<5} | {'FP':<5} | {'FN':<5} | {'Recall':<8} | {'Prec':<8}")
    print("-" * 90)
    total_tp, total_fp, total_fn, total_gt = 0, 0, 0, 0
    for o in overall:
        total_tp += o["tp"]
        total_fp += o["fp"]
        total_fn += o["fn"]
        total_gt += o["gt"]
        recall = o["tp"] / o["gt"] if o["gt"] > 0 else 0
        prec = o["tp"] / (o["tp"] + o["fp"]) if (o["tp"] + o["fp"]) > 0 else 0
        print(
            f"{o['name']:<45} | {o['tp']:<5} | {o['fp']:<5} | {o['fn']:<5} | {recall:>7.1%} | {prec:>7.1%}"
        )

    g_recall = total_tp / total_gt if total_gt > 0 else 0
    g_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    print("-" * 90)
    print(
        f"{'GLOBAL TOTAL':<45} | {total_tp:<5} | {total_fp:<5} | {total_fn:<5} | {g_recall:>7.2%} | {g_prec:>7.2%}"
    )


if __name__ == "__main__":
    main()
