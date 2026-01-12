
import argparse
import json
import sys
from pathlib import Path
from tqdm import tqdm

# Add repo root
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.common.barline_evaluation import barline_iou

HARD_FPS = {
    "Shosrakovich-Sym5-Va_page_016": [(2713, 3681)],
    "Shosrakovich-Sym5-Va_page_018": [(2707, 1148)],
    "Shosrakovich-Sym5-Va_page_019": [(1308, 420)],
}

def find_gt_file(gt_root, subdir, page_name):
    # Same logic as re_evaluate_global
    base_dir = Path(gt_root) / subdir / page_name
    if not base_dir.exists(): return None
    candidates = list(base_dir.glob("boxes_sorted*.json"))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]
    f = base_dir / "boxes_sorted.json"
    if f.exists(): return f
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    args = parser.parse_args()

    # Find candidate files
    files = list(args.logs.rglob("pipeline2_no_peak_candidates.json"))
    print(f"Found {len(files)} candidate files in {args.logs}")

    for json_path in tqdm(files):
        # Parse identity
        run_id = json_path.parent.name
        parts = run_id.split('_')
        # Format: eval2_ScoreName_page_XXX
        # Find 'page'
        try:
            page_idx = parts.index('page')
            subdir = "_".join(parts[1:page_idx])
            page_name = "_".join(parts[page_idx:])
        except ValueError:
            print(f"Skipping {run_id} (naming format)")
            continue

        full_name = f"{subdir}_{page_name}"
        
        # Load GT
        gt_path = find_gt_file(args.gt_root, subdir, page_name)
        gt_boxes = []
        if gt_path:
            with open(gt_path) as f:
                data = json.load(f)
            for item in data:
                if isinstance(item, list): gt_boxes.append(tuple(item[:4]))
                elif isinstance(item, dict):
                    if "box" in item: gt_boxes.append(tuple(item["box"]))
                    elif "barline_location" in item: gt_boxes.append(tuple(item["barline_location"]))

        with open(json_path) as f:
            candidates = json.load(f)

        scored = []
        for cand in candidates:
            if len(cand) != 4: continue
            
            # Default score 0
            score = 0.0
            
            # 1. Check if TP (IoU > 0.5 with ANY GT)
            is_tp = False
            for gb in gt_boxes:
                if barline_iou(cand, gb) > 0.5:
                    is_tp = True
                    break
            
            if is_tp:
                score = 1.0
            else:
                # 2. Check if Hard FP
                if full_name in HARD_FPS:
                    for (hx, hy) in HARD_FPS[full_name]:
                        # Distance check (allow some wiggle room, eg 10px)
                        # candidate x1, y1
                        if abs(cand[0] - hx) < 10 and abs(cand[1] - hy) < 10:
                            score = 1.0
                            break
            
            scored.append({"bbox": cand, "score": score})

        out_path = json_path.parent / "pipeline2_no_peak_scored.json"
        with open(out_path, 'w') as f:
            json.dump(scored, f, indent=2)

if __name__ == "__main__":
    main()
