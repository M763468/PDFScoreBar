
import argparse
import json
import sys
import shutil
from pathlib import Path
import numpy as np
import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

# Drawing util
from tools.run_gt_rebuild_hybrid_eval import load_preds

def draw_boxes(img, boxes, color, thickness=2):
    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

def process_run(run_dir: Path, img_root: Path):
    run_id = run_dir.name
    # Parse run_id: eval2_<pdf_stem>_<page_name>
    parts = run_id.split('_')
    try:
        page_idx = parts.index("page")
        pdf_stem = "_".join(parts[1:page_idx])
        page_name = "_".join(parts[page_idx:])
        img_path = img_root / pdf_stem / f"{page_name}.png"
    except ValueError:
        return

    if not img_path.exists():
        return

    img = cv2.imread(str(img_path))
    if img is None:
        return
    
    # 1. Pipeline 1: Baseline + Filtered
    p1_json = run_dir / "pipeline1_baseline_filtered.json"
    if p1_json.exists():
        boxes = load_preds(p1_json)
        overlay = img.copy()
        draw_boxes(overlay, boxes, (0, 255, 0), 2)
        out_path = run_dir / "overlay_pipeline1_baseline_filtered.png"
        cv2.imwrite(str(out_path), overlay)
        print(f"Saved {out_path}")

    # 2. Pipeline 2: No Peak
    p2_json = run_dir / "pipeline2_no_peak_candidates.json"
    if p2_json.exists():
        boxes = load_preds(p2_json)
        overlay = img.copy()
        draw_boxes(overlay, boxes, (0, 0, 255), 2) # Red for No Peak
        out_path = run_dir / "overlay_pipeline2_no_peak.png"
        cv2.imwrite(str(out_path), overlay)
        print(f"Saved {out_path}")

def main():
    log_root = Path("logs/hybrid_generalization")
    img_root = Path("data/evaluation2/images")
    
    for run_dir in sorted(log_root.glob("eval2_*")):
        process_run(run_dir, img_root)

if __name__ == "__main__":
    main()
