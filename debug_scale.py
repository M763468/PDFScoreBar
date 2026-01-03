
import json
import numpy as np
from pathlib import Path

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

gt_path = "data/evaluation/annotations/page_003/boxes_sorted.json"
pred_path = "logs/validation/20251227T_batch23_musicxml_system/page_3/page_3_preds.json"

with open(gt_path) as f:
    gt_data = json.load(f)
gt_boxes = [entry["barline_location"] for entry in gt_data]

with open(pred_path) as f:
    pred_data = json.load(f)
# Preds might be dict/list. Batch23 is list?
# Earlier cat showed dict? No, earlier cat showed {"num_omr_boxes"...}. Wait.
# Step 505 output showed `page_3_metrics.json` content? No `page_3_preds.json` content?
# Step 505: `cat logs/.../page_3_metrics.json`. Correct.
# Step 480: `head ... page_3_preds.json` -> `[[...]]`. So it IS a list.

if isinstance(pred_data, dict) and "scores" in pred_data:
    candidates = [x["bbox"] for x in pred_data["scores"]]
elif isinstance(pred_data, list):
    candidates = pred_data
else:
    print("Unknown format")
    candidates = []

print(f"GT: {len(gt_boxes)}, Candidates: {len(candidates)}")

scales = [0.2, 0.22, 0.23, 0.24, 0.25, 0.33, 0.5, 1.0, 2.0, 4.0]
for s in scales:
    matches = 0
    for c in candidates:
        s_box = [x * s for x in c]
        for g in gt_boxes:
            if barline_iou(g, s_box) > 0.1:
                matches += 1
                break
    print(f"Scale {s}: {matches} matches")
