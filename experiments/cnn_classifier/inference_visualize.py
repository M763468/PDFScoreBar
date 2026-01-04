import argparse
import json
import torch
import cv2
import numpy as np
from pathlib import Path
from torchvision import transforms, models
from PIL import Image
from tqdm import tqdm
import yaml

# --- Config ---
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMG_SIZE = (256, 128) # H, W

class GPUNormalize(torch.nn.Module):
    def __init__(self, mean, std):
        super().__init__()
        self.register_buffer('mean', torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer('std', torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x):
        return (x - self.mean) / self.std

def get_model(model_path, model_name='resnet18'):
    if model_name == 'resnet18':
        model = models.resnet18(weights=None)
        in_features = model.fc.in_features
        model.fc = torch.nn.Linear(in_features, 1)
    elif model_name == 'mobilenet_v3_small':
        model = models.mobilenet_v3_small(weights=None)
        in_features = model.classifier[3].in_features
        model.classifier[3] = torch.nn.Linear(in_features, 1)
    else:
        raise ValueError(f"Unknown model: {model_name}")
    
    # Load state dict
    state_dict = torch.load(model_path, map_location=DEVICE)
    model.load_state_dict(state_dict)
    model.to(DEVICE)
    model.eval()
    return model

def crop_size_from_bbox(box, scale=3.0, aspect_ratio=0.5, min_h=48, max_h=256, min_w=16, max_w=128):
    x1, y1, x2, y2 = box
    bbox_h = max(1.0, abs(y2 - y1))
    crop_h = int(round(bbox_h * scale))
    crop_h = max(min_h, min(max_h, crop_h))
    crop_w = int(round(crop_h * aspect_ratio))
    crop_w = max(min_w, min(max_w, crop_w))
    return crop_w, crop_h

def center_crop(img, cx, cy, crop_w, crop_h):
    # img is OpenCV BGR (H, W, C)
    w_half = crop_w // 2
    h_half = crop_h // 2
    cy1 = max(0, cy - h_half)
    cy2 = min(img.shape[0], cy + h_half)
    cx1 = max(0, cx - w_half)
    cx2 = min(img.shape[1], cx + w_half)
    
    crop = img[cy1:cy2, cx1:cx2]
    
    # Padding if necessary
    if crop.shape[0] < crop_h or crop.shape[1] < crop_w:
        pad_y1 = h_half - (cy - cy1)
        pad_y2 = h_half - (cy2 - cy)
        pad_x1 = w_half - (cx - cx1)
        pad_x2 = w_half - (cx2 - cx)
        crop = cv2.copyMakeBorder(
            crop,
            pad_y1,
            pad_y2,
            pad_x1,
            pad_x2,
            cv2.BORDER_CONSTANT,
            value=[255, 255, 255],
        )
    return crop

def process_page(image_path, candidates, model, transform, gpu_norm, threshold=0.5):
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Failed to load {image_path}")
        return None

    results = []
    
    batch_tensors = []
    batch_indices = []
    
    for i, box in enumerate(candidates):
        x1, y1, x2, y2 = box
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        
        crop_w, crop_h = crop_size_from_bbox(box)
        crop_bgr = center_crop(img, cx, cy, crop_w, crop_h)
        
        # Convert to PIL RGB
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)
        
        # Transform (Resize + ToTensor)
        tensor = transform(pil_img)
        batch_tensors.append(tensor)
        batch_indices.append(i)

    # Batch Inference
    if not batch_tensors:
        return results

    batch_stack = torch.stack(batch_tensors).to(DEVICE)
    batch_stack = gpu_norm(batch_stack) # Normalize on GPU

    with torch.no_grad():
        with torch.amp.autocast('cuda'):
            outputs = model(batch_stack)
            probs = torch.sigmoid(outputs).cpu().numpy().flatten()

    for idx, prob in zip(batch_indices, probs):
        results.append({
            "bbox": candidates[idx],
            "score": float(prob),
            "label": "barline" if prob > threshold else "fp"
        })
        
    return results

def visualize(image_path, results, output_path, threshold=0.5, mode="filtered"):
    img = cv2.imread(str(image_path))
    if img is None:
        return
    overlay = img.copy()
    
    # Draw boxes
    for res in results:
        x1, y1, x2, y2 = map(int, res["bbox"])
        score = res["score"]
        
        if mode == "filtered":
            if score > threshold:
                color = (0, 255, 0) # Green (BGR)
                thickness = 3
            else:
                color = (0, 0, 255) # Red (BGR)
                thickness = 2
        else:
            # All candidates mode
            color = (255, 0, 0) # Blue (BGR)
            thickness = 2
        
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, thickness)
        
        # Add score label for all boxes in filtered mode, and just score in all mode
        label = f"{score:.2f}"
        cv2.putText(overlay, label, (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
    cv2.imwrite(str(output_path), overlay)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-root", required=True, help="Root directory containing images (recursive search)")
    parser.add_argument("--json-root", required=True, help="Root directory containing hybrid_predictions.json files")
    parser.add_argument("--output-root", required=True, help="Output directory for overlays")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--config", default="experiments/cnn_classifier/config.yaml")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--run-prefix", default="eval2", help="Only process run directories starting with this prefix")
    parser.add_argument("--skip-existing", action="store_true", help="Skip processing if output file already exists")
    parser.add_argument("--candidates-file", default="hybrid_predictions.json", help="Filename of candidate JSON in run dir")
    args = parser.parse_args()

    # Load Config for Model Params (optional, but good for consistency)
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    model_name = config.get("model_name", "resnet18")
    
    # Init Model
    model = get_model(args.model_path, model_name)
    
    # Init Transforms
    cpu_transform = transforms.Compose([
        transforms.Resize(IMG_SIZE), 
        transforms.ToTensor(),
    ])
    
    gpu_norm = GPUNormalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]).to(DEVICE)

    # Find JSONs
    # We search for the specific candidate file instead of hybrid_predictions.json
    json_files = list(Path(args.json_root).rglob(args.candidates_file))
    print(f"Found {len(json_files)} candidate files ({args.candidates_file}) total.")

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    for json_path in tqdm(json_files):
        run_id = json_path.parent.name
        
        # Filter by prefix
        if not run_id.startswith(args.run_prefix):
            continue
            
        vis_path = output_root / f"{run_id}_overlay.png"
        all_vis_path = output_root / f"{run_id}_all_candidates.png"
        
        # Even if skipping existing, we check both if skip-existing is on
        if args.skip_existing and vis_path.exists() and all_vis_path.exists():
            continue

        # Parse run_id
        parts = run_id.split('_')
        try:
            page_idx = parts.index("page")
        except ValueError:
            print(f"Skipping format without 'page': {run_id}")
            continue

        if len(parts) >= 4 and parts[0] == "eval2":
            subdir = "_".join(parts[1:page_idx])
            page_name = "_".join(parts[page_idx:])
            
            image_rel = Path(subdir) / f"{page_name}.png"
            image_path = Path(args.image_root) / image_rel
        else:
            print(f"Skipping unknown run_id format: {run_id}")
            continue
            
        if not image_path.exists():
            print(f"Image not found: {image_path}")
            continue
            
        with open(json_path, 'r') as f:
            candidates = json.load(f)
            
        results = process_page(image_path, candidates, model, cpu_transform, gpu_norm, args.threshold)
        
        if results:
            # 1. Filtered Visualization (Green/Red)
            visualize(image_path, results, vis_path, args.threshold, mode="filtered")
            
            # 2. All Candidates Visualization (Blue)
            visualize(image_path, results, all_vis_path, args.threshold, mode="all")
            
            # Save JSON results too
            out_json = output_root / f"{run_id}_scored.json"
            with open(out_json, 'w') as f:
                json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
