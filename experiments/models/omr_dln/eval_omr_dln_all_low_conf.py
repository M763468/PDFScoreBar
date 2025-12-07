
from ultralytics import YOLO
import cv2
import json
import torch
import pandas as pd

# Define paths
model_path = 'external/omr_dln/models/public_models/YOLOv8x_Symbols.pt'
image_path = 'data/evaluation/images/page_3.png'
output_json_path = 'logs/model_experiments/omr_dln/predictions_all_low_conf.json'
output_image_path = 'logs/model_experiments/omr_dln/page_3_overlay_all_low_conf.png'
labels_csv_path = 'external/omr_dln/yolo/new_labels.csv'

# Create output directory if it doesn't exist
import os
os.makedirs('logs/model_experiments/omr_dln', exist_ok=True)

# Load labels
raw_labels = pd.read_csv(labels_csv_path)
raw_labels['label'] -= 1
unique_labels = raw_labels[['label', 'name']].drop_duplicates(subset=['label']).sort_values(by=['label']).reset_index(drop=True)
class_names = dict(zip(unique_labels['label'], unique_labels['name']))


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
print(f"Running inference on {image_path} with low confidence threshold...")
results = model(image_path, conf=0.01)
print("Inference complete.")

# Process results
all_detections = []
image = cv2.imread(image_path)
height, width, _ = image.shape

detected_classes = set()

for result in results:
    boxes = result.boxes
    for box in boxes:
        class_id = int(box.cls[0])
        detected_classes.add(class_id)
        
        x1, y1, x2, y2 = box.xyxy[0]
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        
        detection = {
            'class_id': class_id,
            'class_name': class_names.get(class_id, 'Unknown'),
            'box_2d': [x1, y1, x2, y2],
            'score': float(box.conf[0])
        }
        all_detections.append(detection)
        
        # Draw bounding box on the image if confidence is high enough to be interesting
        if float(box.conf[0]) > 0.1:
            label = f"{class_names.get(class_id, 'Unknown')}: {box.conf[0]:.2f}"
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

# Save all detections to JSON
print(f"Saving {len(all_detections)} detections to {output_json_path}...")
with open(output_json_path, 'w') as f:
    json.dump(all_detections, f, indent=4)

# Save the visualized image
print(f"Saving visualized image to {output_image_path}...")
cv2.imwrite(output_image_path, image)

print("Detected class IDs:", sorted(list(detected_classes)))
for class_id in sorted(list(detected_classes)):
    print(f"Class ID: {class_id}, Name: {class_names.get(class_id, 'Unknown')}")

print("Evaluation script finished.")
