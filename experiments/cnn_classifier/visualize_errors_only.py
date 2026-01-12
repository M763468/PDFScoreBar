import argparse
import json
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm

def compute_iou(box1, box2):
    # box: [x1, y1, x2, y2]
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    
    union_area = box1_area + box2_area - inter_area
    if union_area == 0:
        return 0
    return inter_area / union_area

def find_gt_file(gt_root, subdir, page_name):
    # Try typical locations
    # data/evaluation2/annotations/subdir/page_name/boxes_sorted.json
    base_dir = Path(gt_root) / subdir / page_name
    
    # Try boxes_sorted.json
    f = base_dir / "boxes_sorted.json"
    if f.exists(): return f
    
    # Try looking for any boxes_sorted_v*.json and pick latest
    candidates = list(base_dir.glob("boxes_sorted*.json"))
    if candidates:
        candidates.sort() # sort by name (usually version has date)
        return candidates[-1]
        
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-root", required=True)
    parser.add_argument("--scored-root", required=True, help="Dir containing *_scored.json")
    parser.add_argument("--gt-root", required=True, help="data/evaluation2/annotations")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    scored_files = list(Path(args.scored_root).glob("*_scored.json"))
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"Found {len(scored_files)} scored files.")

    for json_path in tqdm(scored_files):
        # Filename format: eval2_SubDir_PageName_scored.json
        # Need to handle potential underscores in SubDir/PageName
        # Assumption: run_id is everything before "_scored.json"
        run_id = json_path.stem.replace("_scored", "")
        
        parts = run_id.split('_')
        # Parts: ["eval2", "Va", "Prokofiev", "Symphony1", "page", "004"]
        try:
            page_idx = parts.index("page")
        except ValueError:
            continue
            
        subdir = "_".join(parts[1:page_idx])
        page_name = "_".join(parts[page_idx:])
        
        # Debug
        print(f"RunID: {run_id}, Subdir: '{subdir}'")

        if subdir == "prokofiev1":
            continue
        
        # Load Image
        image_path = Path(args.image_root) / subdir / f"{page_name}.png"
        if not image_path.exists():
            # Try flat structure just in case? No, project follows structure.
            continue
            
        img = cv2.imread(str(image_path))
        if img is None: continue
        
        # Load Scored Candidates
        with open(json_path, 'r') as f:
            candidates = json.load(f)
            
        # Load GT
        gt_path = find_gt_file(args.gt_root, subdir, page_name)
        gt_boxes = []
        if gt_path:
            with open(gt_path, 'r') as f:
                gt_data = json.load(f)
                # GT format: list of [x1, y1, x2, y2, label] or dicts
                # Assuming list of lists based on project history
                for item in gt_data:
                    if isinstance(item, list):
                        gt_boxes.append(item[:4])
                    elif isinstance(item, dict):
                        if "box" in item:
                            gt_boxes.append(item["box"])
                        elif "barline_location" in item:
                            gt_boxes.append(item["barline_location"])
        
        print(f"  GT: {len(gt_boxes)} boxes from {gt_path}")
        
        # Matching
        # For each candidate, find best GT overlap
        
        fp_boxes = [] # Green (Model Yes, GT No)
        fn_cnn_boxes = [] # Red (Model No, GT Yes - via candidate)
        fn_det_boxes = [] # Yellow (No Candidate)
        
        # 1. Match Candidates to GT
        gt_matched = [False] * len(gt_boxes)
        
        for cand in candidates:
            box = cand["bbox"]
            score = cand["score"]
            
            # Find Best GT Match
            best_iou = 0
            best_gt_idx = -1
            
            for idx, gt in enumerate(gt_boxes):
                iou = compute_iou(box, gt)
                if iou > best_iou:
                    best_iou = iou
                    best_gt_idx = idx
            
            is_matched_gt = (best_iou > 0.5)
            is_accepted = (score > args.threshold)
            
            if is_matched_gt:
                # This candidate corresponds to a GT
                gt_matched[best_gt_idx] = True # Consumed by at least one candidate (regardless of score)
                
                if not is_accepted:
                    fn_cnn_boxes.append(cand) # Found by detector, rejected by CNN
            else:
                # No matching GT
                if is_accepted:
                    fp_boxes.append(cand) # FP (Hallucination)

        # 2. Identify Detector Misses (GT with NO matching candidate)
        for idx, is_covered in enumerate(gt_matched):
            if not is_covered:
                fn_det_boxes.append(gt_boxes[idx])
        
        # Draw
        overlay = img.copy()
        
        # Draw GT (Blue, thin) - Reference
        for gt in gt_boxes:
            x1, y1, x2, y2 = map(int, gt)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 0, 0), 1)
            
        # Draw Detector Misses (Yellow, thick)
        for box in fn_det_boxes:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2) # Yellow
            cv2.putText(overlay, "Miss", (x1, y1-2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # Draw CNN Misses (Red, thick)
        for item in fn_cnn_boxes:
            box = item["bbox"]
            score = item["score"]
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), 2) # Red
            cv2.putText(overlay, f"{score:.2f}", (x1, y1-2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

        # 3. Draw FP (Green, thick) - Classifier Hallucination (or Missing GT)
        for item in fp_boxes:
            box = item["bbox"]
            score = item["score"]
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2) # Green
            cv2.putText(overlay, f"{score:.2f}", (x1, y1-2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            
        # Save
        out_path = output_root / f"{run_id}_error_only.png"
        cv2.imwrite(str(out_path), overlay)
        
if __name__ == "__main__":
    main()
