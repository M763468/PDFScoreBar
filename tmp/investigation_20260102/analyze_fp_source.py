
import json
import os
import sys

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    if boxAArea + boxBArea - interArea == 0: return 0
    return interArea / float(boxAArea + boxBArea - interArea)

def check_source(page_dir):
    fp_path = os.path.join(page_dir, "fp_boxes.json")
    recovered_path = os.path.join(page_dir, "end_recovered_geom.json") # Probe results (geom filtered)

    if not os.path.exists(fp_path):
        print(f"FP path not found: {fp_path}")
        return

    with open(fp_path, 'r') as f:
        fp_boxes = json.load(f)

    recovered_boxes = []
    if os.path.exists(recovered_path):
        with open(recovered_path, 'r') as f:
            recovered_boxes = json.load(f)

    print(f"--- Source Analysis for {os.path.basename(page_dir)} ---")
    print(f"Total FPs: {len(fp_boxes)}")

    for i, fp in enumerate(fp_boxes):
        is_probe = False
        for rec in recovered_boxes:
            # Check exact match or high IOU
            if fp == rec or iou(fp, rec) > 0.9:
                is_probe = True
                break

        source = "PROBE" if is_probe else "BASELINE (OMR/Union)"
        print(f"FP #{i} {fp}: {source}")

if __name__ == "__main__":
    root_dir = "logs/gt_rebuild_hybrid_eval/20260102T_bypass_row_filter_fix_rescue/per_page"
    for page in ["page_001", "page_004", "page_3", "page_10", "page_15"]:
        check_source(os.path.join(root_dir, page))
