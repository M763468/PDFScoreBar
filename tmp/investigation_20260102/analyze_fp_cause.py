
import json
import os
import sys

def center_dist(boxA, boxB):
    cA = ((boxA[0]+boxA[2])/2, (boxA[1]+boxA[3])/2)
    cB = ((boxB[0]+boxB[2])/2, (boxB[1]+boxB[3])/2)
    return ((cA[0]-cB[0])**2 + (cA[1]-cB[1])**2)**0.5

def analyze_fp(page_dir):
    fp_path = os.path.join(page_dir, "fp_boxes.json")
    debug_path = os.path.join(page_dir, "endbar_debug.json")

    if not os.path.exists(fp_path) or not os.path.exists(debug_path):
        print(f"Files not found in {page_dir}")
        return

    with open(fp_path, 'r') as f:
        fp_boxes = json.load(f)

    with open(debug_path, 'r') as f:
        debug_data = json.load(f)
        records = debug_data.get("records", [])

    print(f"--- Analysis for {os.path.basename(page_dir)} ---")
    print(f"Total FP boxes: {len(fp_boxes)}")

    for i, fp_box in enumerate(fp_boxes):
        print(f"\nFP #{i}: {fp_box}")

        best_match = None
        min_dist = float('inf')

        for rec in records:
            if 'col' in rec and 'band' in rec:
                col = rec['col']
                y1, y2 = rec['band']
                # probe_width assumed 2
                rec_box = [col, y1, col+2, y2]
            else:
                continue

            dist = center_dist(fp_box, rec_box)
            if dist < 20:
                if dist < min_dist:
                    min_dist = dist
                    best_match = rec

        if best_match:
            print(f"  Matched Candidate: Status={best_match.get('status')}")
            print(f"  Reject Reason: {best_match.get('reject_reason')}")
            print(f"  Col: {best_match.get('col')}")
            print(f"  Ratios: Peak={best_match.get('peak_ratio')}, Top={best_match.get('top_ratio')}, Bottom={best_match.get('bottom_ratio')}")
            print(f"  Extend Ratios: Top={best_match.get('extended_top_max_ratio')}, Bottom={best_match.get('extended_bottom_max_ratio')}")
            divisi = best_match.get('divisi_info')
            if divisi:
                print(f"  Divisi: {divisi}")
        else:
            print("  No matching candidate found in debug records")

if __name__ == "__main__":
    root_dir = "logs/gt_rebuild_hybrid_eval/20260102T_bypass_row_filter_fix_rescue/per_page"
    analyze_fp(os.path.join(root_dir, "page_004"))
    analyze_fp(os.path.join(root_dir, "page_3"))
    analyze_fp(os.path.join(root_dir, "page_15"))
