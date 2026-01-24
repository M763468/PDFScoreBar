import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports if needed
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

# Reuse the overlap logic from temp_analyze_overlap.py but make it robust
def compute_iou(boxA, boxB):
    # box: [x1, y1, x2, y2]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    # Avoid division by zero
    denominator = float(boxAArea + boxBArea - interArea)
    if denominator == 0:
        return 0.0

    iou = interArea / denominator
    return iou

def load_predictions(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Handle different formats if necessary
    # Format 1: List of dicts with 'barline_location' (Standard Hybrid Output)
    # Format 2: List of lists (Simple Box List)
    
    boxes = []
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], dict):
             if 'barline_location' in data[0]:
                 boxes = [item['barline_location'] for item in data]
             elif 'orig_bbox' in data[0]:
                 boxes = [item['orig_bbox'] for item in data]
             else:
                 print(f"Warning: Unknown dict format in {json_path}. Keys: {data[0].keys()}")
        elif isinstance(data[0], list):
            boxes = data
    else:
        print(f"Error: JSON root is not a list in {json_path}")
        return []
        
    return boxes

def main():
    parser = argparse.ArgumentParser(description="Compare two hybrid prediction JSON files.")
    parser.add_argument("baseline", help="Path to baseline JSON")
    parser.add_argument("target", help="Path to target (optimized) JSON")
    parser.add_argument("--iou", type=float, default=0.95, help="IoU threshold for strict matching")
    args = parser.parse_args()

    print(f"--- Comparing Hybrid Results ---")
    print(f"Baseline: {args.baseline}")
    print(f"Target:   {args.target}")

    base_boxes = load_predictions(args.baseline)
    target_boxes = load_predictions(args.target)

    print(f"\nBaseline Count: {len(base_boxes)}")
    print(f"Target Count:   {len(target_boxes)}")

    if len(base_boxes) == 0 and len(target_boxes) == 0:
        print("Both files are empty.")
        sys.exit(0)

    # Check matches (Target -> Baseline)
    matched_count = 0
    unmatched_indices = []
    
    # Simple greedy matching
    # Note: For strict regression testing, we want 1-to-1 matching, but for now coverage is key.
    
    for i, t_box in enumerate(target_boxes):
        found = False
        for b_box in base_boxes:
            if compute_iou(t_box, b_box) >= args.iou:
                found = True
                break
        if found:
            matched_count += 1
        else:
            unmatched_indices.append(i)

    match_rate = matched_count / len(target_boxes) if target_boxes else 0
    print(f"\nMatches (Target found in Baseline, IoU >= {args.iou}): {matched_count}/{len(target_boxes)} ({match_rate:.2%})")

    if unmatched_indices:
        print(f"Unmatched Target Indices: {unmatched_indices}")
        if len(unmatched_indices) < 5:
            for i in unmatched_indices:
                print(f"  Item {i}: {target_boxes[i]}")

    # Reverse check (Baseline -> Target) to see if we lost anything
    reverse_matched = 0
    lost_indices = []
    for i, b_box in enumerate(base_boxes):
        found = False
        for t_box in target_boxes:
            if compute_iou(b_box, t_box) >= args.iou:
                found = True
                break
        if found:
            reverse_matched += 1
        else:
            lost_indices.append(i)
            
    loss_rate = reverse_matched / len(base_boxes) if base_boxes else 0
    print(f"Retention (Baseline found in Target, IoU >= {args.iou}): {reverse_matched}/{len(base_boxes)} ({loss_rate:.2%})")

    if lost_indices:
        print(f"Lost Baseline Indices: {lost_indices}")

    # Success Condition
    if len(base_boxes) == len(target_boxes) and matched_count == len(target_boxes):
        print("\nSUCCESS: Results are identical.")
        sys.exit(0)
    else:
        print("\nWARNING: Results differ.")
        sys.exit(1)

if __name__ == "__main__":
    main()
