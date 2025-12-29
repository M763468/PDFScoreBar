
import json
import os

gt_json_path = "data/evaluation/annotations/page_003/boxes_sorted.json"
output_json_path = "temp_omr_dln_fn_barlines.json" # Relative to current working directory
fn_indices = [4, 11, 18, 28, 40, 49, 58, 65, 79, 95, 108, 111, 121, 136, 141]

with open(gt_json_path, 'r') as f:
    gt_data = json.load(f)

fn_barlines = []
for index in fn_indices:
    if 0 <= index < len(gt_data):
        fn_barlines.append(gt_data[index]["barline_location"])

with open(output_json_path, 'w') as f:
    json.dump(fn_barlines, f, indent=4)

print(f"Filtered {len(fn_barlines)} FN barlines saved to {output_json_path}")
