
from ultralytics import YOLO
import cv2
import json
import torch

# Define paths
model_path = 'external/omr_dln/models/public_models/YOLOv8x_Symbols.pt'
image_path = 'data/evaluation/images/page_3.png'
output_json_path = 'logs/model_experiments/omr_dln/predictions.json'
output_image_path = 'logs/model_experiments/omr_dln/page_3_overlay.png'

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
barline_detections = []
image = cv2.imread(image_path)
height, width, _ = image.shape

for result in results:
    boxes = result.boxes
    for box in boxes:
        class_id = int(box.cls[0])
        
        # Filter for barlines (class ID 155)
        if class_id == 155:
            x1, y1, x2, y2 = box.xyxy[0]
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            detection = {
                'box_2d': [x1, y1, x2, y2],
                'score': float(box.conf[0])
            }
            barline_detections.append(detection)
            
            # Draw bounding box on the image
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

# Save detections to JSON
print(f"Saving {len(barline_detections)} barline detections to {output_json_path}...")
with open(output_json_path, 'w') as f:
    json.dump(barline_detections, f, indent=4)

# Save the visualized image
print(f"Saving visualized image to {output_image_path}...")
cv2.imwrite(output_image_path, image)

print("Evaluation script finished.")
