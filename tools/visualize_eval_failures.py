import argparse
import json
import os
from pathlib import Path
import cv2
import numpy as np

def barline_iou(box1, box2):
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    inter_x1 = max(x1_1, x1_2)
    inter_y1 = max(y1_1, y1_2)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)
    if inter_x2 < inter_x1 or inter_y2 < inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1 + 1) * (inter_y2 - inter_y1 + 1)
    area1 = (x2_1 - x1_1 + 1) * (y2_1 - y1_1 + 1)
    area2 = (x2_2 - x1_2 + 1) * (y2_2 - y1_2 + 1)
    return inter_area / float(area1 + area2 - inter_area)

def is_match_center_anchor(gt_box, pred_box, x_dist_thresh=12, vov_thresh=0.5):
    gx1, gy1, gx2, gy2 = gt_box
    px1, py1, px2, py2 = pred_box
    
    # 1. Horizontal distance (center to center)
    g_cx = (gx1 + gx2) / 2.0
    p_cx = (px1 + px2) / 2.0
    if abs(g_cx - p_cx) > x_dist_thresh:
        return False
        
    # 2. Vertical Overlap (VoV)
    inter_y1 = max(gy1, py1)
    inter_y2 = min(gy2, py2)
    inter_h = max(0, inter_y2 - inter_y1)
    
    union_y1 = min(gy1, py1)
    union_y2 = max(gy2, py2)
    union_h = max(1, union_y2 - union_y1)
    
    vov = inter_h / float(union_h)
    return vov >= vov_thresh

def main():
    # ... (argparse remains same)
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("debug_outputs/fn_visualizations"))
    parser.add_argument("--threshold", type=float, default=0.1)
    args = parser.parse_args()

    # Clean up old visualizations
    if args.output_dir.exists():
        import shutil
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ... (loading remains same)
    scored_files = list(args.scored_root.rglob("*_scored.json"))
    for scored_path in scored_files:
        # ... (parse context)
        parts = scored_path.parent.name.split("_")
        if "page" not in parts: continue
        p_idx = parts.index("page")
        score_name = "_".join(parts[1:p_idx])
        page_name = "_".join(parts[p_idx:])

        # Load GT
        gt_dir = args.gt_root / score_name / page_name
        gt_path = list(gt_dir.glob("boxes_sorted*.json"))
        if not gt_path: continue
        with gt_path[0].open("r") as f:
            gt_data = json.load(f)
        gt_boxes = [b["barline_location"] for b in gt_data if "barline_location" in b]

        with scored_path.open("r") as f:
            preds = json.load(f)
        
        high_preds = [p for p in preds if p["score"] >= args.threshold]
        
        fn_boxes = []
        for gt_box in gt_boxes:
            matched = False
            for p in high_preds:
                if is_match_center_anchor(gt_box, p["bbox"]):
                    matched = True
                    break
            if not matched:
                fn_boxes.append(gt_box)

        if not fn_boxes:
            continue

        print(f"Page {score_name}/{page_name}: Found {len(fn_boxes)} FNs.")

        # Load Image
        img_path = args.images_root / score_name / f"{page_name}.png"
        img = cv2.imread(str(img_path))
        if img is None: continue

        for i, fn_box in enumerate(fn_boxes):
            x1, y1, x2, y2 = fn_box
            cx, cy = (x1+x2)//2, (y1+y2)//2
            
            # Crop around FN
            pad = 150
            cy1 = max(0, cy - pad*2)
            cy2 = min(img.shape[0], cy + pad*2)
            cx1 = max(0, cx - pad)
            cx2 = min(img.shape[1], cx + pad)
            
            crop = img[cy1:cy2, cx1:cx2].copy()
            
            # Draw GT (Red)
            cv2.rectangle(crop, (x1-cx1, y1-cy1), (x2-cx1, y2-cy1), (0, 0, 255), 2)
            cv2.putText(crop, "GT", (x1-cx1, y1-cy1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

            # Draw all nearby candidates (Blue/Cyan)
            for p in preds:
                px1, py1, px2, py2 = p["bbox"]
                if px2 < cx1 or px1 > cx2 or py2 < cy1 or py1 > cy2: continue
                
                color = (255, 0, 0) if p["score"] >= args.threshold else (255, 255, 0)
                cv2.rectangle(crop, (px1-cx1, py1-cy1), (px2-cx1, py2-cy1), color, 1)
                cv2.putText(crop, f"{p['score']:.3f}", (px1-cx1, py1-cy1+15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            out_path = args.output_dir / f"{score_name}_{page_name}_fn_{i:02d}.png"
            cv2.imwrite(str(out_path), crop)

if __name__ == "__main__":
    main()
