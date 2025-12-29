from ultralytics import YOLO
import cv2
import json
import torch
import numpy as np

# Define paths
model_path = 'external/omr_dln/models/public_models/YOLOv8m_Measures.pt'
image_path = 'data/evaluation/images/page_3.png'
output_json_path = 'logs/model_experiments/omr_dln/predictions_barlines_from_measures.json'
output_image_path = 'logs/model_experiments/omr_dln/page_3_overlay_barlines_from_measures.png'
ground_truth_path = 'data/evaluation/annotations/page_003/boxes_sorted.json'

# Create output directory if it doesn't exist
import os
os.makedirs('logs/model_experiments/omr_dln', exist_ok=True)

# Load the model
print(f"Loading model from {model_path}...")
model = YOLO(model_path)
print("Model loaded.")

# Check if GPU is available and move model to GPU
if torch.cuda.is_available():
    print("GPU is available, moving model to GPU.")
    model.to('cuda')
else:
    print("GPU not available, running on CPU.")

# Run inference
print(f"Running inference on {image_path}...")
results = model(image_path)
print("Inference complete.")

# Process results
measure_boxes = []
for result in results:
    boxes = result.boxes
    for box in boxes:
        class_id = int(box.cls[0])
        # class 156 is systemMeasure
        if class_id == 156:
            measure_boxes.append(box.xyxy[0].tolist())

# Derive barlines from measure boxes
barline_x_coords = set()
all_y = []
for box in measure_boxes:
    x1, y1, x2, y2 = box
    barline_x_coords.add(int(x1))
    barline_x_coords.add(int(x2))
    all_y.extend([y1, y2])

# Determine the vertical extent of the barlines
min_y = int(min(all_y)) if all_y else 0
max_y = int(max(all_y)) if all_y else 0

# Create barline detections from x-coordinates
barline_detections = []
sorted_x_coords = sorted(list(barline_x_coords))

# Merge close x-coordinates
merged_x_coords = []
if sorted_x_coords:
    current_x = sorted_x_coords[0]
    for i in range(1, len(sorted_x_coords)):
        if sorted_x_coords[i] - current_x < 5:  # 5 pixel tolerance for merging
            pass # part of the same group, do nothing
        else:
            merged_x_coords.append(current_x)
            current_x = sorted_x_coords[i]
    merged_x_coords.append(current_x)

for x in merged_x_coords:
    # Create a 2px wide bounding box
    barline_detections.append({'box_2d': [x - 1, min_y, x + 1, max_y], 'score': 1.0})

# Save detections to JSON
print(f"Saving {len(barline_detections)} derived barline detections to {output_json_path}...")
with open(output_json_path, 'w') as f:
    json.dump(barline_detections, f, indent=4)

# Draw barlines on the image
image = cv2.imread(image_path)
for detection in barline_detections:
    x1, y1, x2, y2 = detection['box_2d']
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

# Save the visualized image
print(f"Saving visualized image to {output_image_path}...")
cv2.imwrite(output_image_path, image)


# --- Evaluation ---
def calculate_iou(boxA, boxB):
    # Determine the (x, y)-coordinates of the intersection rectangle
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    # Compute the area of intersection rectangle
    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)

    # Compute the area of both the prediction and ground-truth rectangles
    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

    # Compute the intersection over union
    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou

with open(ground_truth_path) as f:
    gt_boxes = json.load(f)

# Convert ground truth boxes to the same format
gt_formatted_boxes = [box['barline_location'] for box in gt_boxes]

print("\n--- Ground Truth Boxes (first 5) ---")
for i in range(min(5, len(gt_formatted_boxes))):
    print(gt_formatted_boxes[i])

print("\n--- Derived Barline Boxes (first 5) ---")
for i in range(min(5, len(barline_detections))):
    print(barline_detections[i]['box_2d'])


tp = 0
fp = 0
matched_gt_indices = set()

for pred_box in barline_detections:
    best_iou = 0
    best_gt_idx = -1
    for i, gt_box in enumerate(gt_formatted_boxes):
        iou = calculate_iou(pred_box['box_2d'], gt_box)
        if iou > best_iou:
            best_iou = iou
            best_gt_idx = i
    
    if best_iou > 0.5 and best_gt_idx not in matched_gt_indices:
        tp += 1
        matched_gt_indices.add(best_gt_idx)
    else:
        fp += 1

fn = len(gt_formatted_boxes) - len(matched_gt_indices)

precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

print("\n--- Evaluation Results ---")
print(f"True Positives (TP): {tp}")
print(f"False Positives (FP): {fp}")
print(f"False Negatives (FN): {fn}")
print(f"Precision: {precision:.3f}")
print(f"Recall: {recall:.3f}")
print(f"F1 Score: {f1_score:.3f}")

metrics = {
    'tp': tp,
    'fp': fp,
    'fn': fn,
    'precision': precision,
    'recall': recall,
    'f1_score': f1_score
}

with open('logs/model_experiments/omr_dln/metrics.json', 'w') as f:
    json.dump(metrics, f, indent=4)

print("\nEvaluation script finished.")