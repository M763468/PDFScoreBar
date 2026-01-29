import json


def compute_iou(boxA, boxB):
    # box: [x1, y1, x2, y2]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou


def check_coverage(source_boxes, target_boxes, iou_thresh=0.5):
    # How many of target_boxes are covered by source_boxes?
    covered_count = 0
    for t_box in target_boxes:
        matched = False
        for s_box in source_boxes:
            if compute_iou(s_box, t_box) > iou_thresh:
                matched = True
                break
        if matched:
            covered_count += 1
    return covered_count


# Get intersection (list of indices from source that match target)
def get_intersection_count(source_boxes, target_boxes, iou_thresh=0.5):
    count = 0
    for s_box in source_boxes:
        for t_box in target_boxes:
            if compute_iou(s_box, t_box) > iou_thresh:
                count += 1
                break
    return count


base_path = "logs/hybrid_pipeline_bench/page_10_bench_20260116_213356/baseline/page_10/page_10/page_10_detections.json"
sr_path = "logs/hybrid_pipeline_bench/page_10_bench_20260116_213356/sr/page_10/page_10/page_10_detections.json"
omr_path = "logs/hybrid_pipeline_bench/page_10_bench_20260116_213356/omr_sr/predictions.json"

with open(base_path) as f:
    base_data = json.load(f)
with open(sr_path) as f:
    sr_data = json.load(f)
with open(omr_path) as f:
    omr_boxes = json.load(f)

base_boxes = [x["orig_bbox"] for x in base_data["predictions"]]
sr_boxes = [x["orig_bbox"] for x in sr_data["predictions"]]

print(f"Baseline Count: {len(base_boxes)}")
print(f"SR Count:       {len(sr_boxes)}")
print(f"OMR Count:      {len(omr_boxes)}")

# Baseline vs SR
print("-" * 20)
sr_covered_by_base = check_coverage(base_boxes, sr_boxes)
print(
    f"SR items covered by Baseline: {sr_covered_by_base} / {len(sr_boxes)} ({sr_covered_by_base / len(sr_boxes):.2%})"
)

# Baseline vs OMR (Hypothetical No-SR Pipeline)
print("-" * 20)
base_supported_by_omr = get_intersection_count(
    base_boxes, omr_boxes, iou_thresh=0.1
)  # Loose threshold for line matching
print(f"Baseline supported by OMR: {base_supported_by_omr} / {len(base_boxes)}")

# SR vs OMR (Current Pipeline)
sr_supported_by_omr = get_intersection_count(sr_boxes, omr_boxes, iou_thresh=0.1)
print(f"SR supported by OMR:       {sr_supported_by_omr} / {len(sr_boxes)}")
