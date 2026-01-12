
import argparse
import json
import torch
import cv2
import numpy as np
from pathlib import Path
from torchvision import transforms, models
from PIL import Image
from tqdm import tqdm
import os

# --- Config ---
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMG_SIZE = (256, 128) # H, W
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

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
    else:
        raise ValueError(f"Unknown model: {model_name}")
    
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
    w_half = crop_w // 2
    h_half = crop_h // 2
    cy1 = max(0, cy - h_half)
    cy2 = min(img.shape[0], cy + h_half)
    cx1 = max(0, cx - w_half)
    cx2 = min(img.shape[1], cx + w_half)
    
    crop = img[cy1:cy2, cx1:cx2]
    
    if crop.shape[0] < crop_h or crop.shape[1] < crop_w:
        pad_y1 = h_half - (cy - cy1)
        pad_y2 = h_half - (cy2 - cy)
        pad_x1 = w_half - (cx - cx1)
        pad_x2 = w_half - (cx2 - cx)
        crop = cv2.copyMakeBorder(
            crop, pad_y1, pad_y2, pad_x1, pad_x2,
            cv2.BORDER_CONSTANT, value=[255, 255, 255]
        )
    return crop

def process_dir(log_dir, model, gpu_norm, threshold=0.5):
    scored_json_path = log_dir / "pipeline2_no_peak_scored.json"
    if scored_json_path.exists():
        return True # Already processed

    candidates_path = log_dir / "pipeline2_no_peak_candidates.json"
    if not candidates_path.exists():
        print(f"DEBUG: Candidates path missing: {candidates_path}")
        return False

    # Check if inputs needed are present
    # We need the image! Image path is not in JSON directly usually.
    # But usually log_dir is named eval2_Score_page_XXX.
    # We can perform a robust search or rely on data/evaluation2/images structure
    
    parts = log_dir.name.split('_') # eval2, ScoreName, page, XXX
    # Assuming standard format: eval2_{RunID} where RunID = Score_page_XXX
    # This might be tricky if ScoreName has underscores.
    # However, in run_eval2_batch.py, we know the image paths.
    
    # Try to find the image in data/evaluation2/images
    # Reconstruct relative path from parts?
    # Better: Inspect run_eval2_batch logic or just search.
    # Let's search recursively in data/evaluation2/images for the matching page name.
    
    # Attempt to parse: The end is always page_XXX.
    try:
        page_idx = parts.index("page")
        score_name = "_".join(parts[1:page_idx])
        page_num = "_".join(parts[page_idx:]) # page_002
    except ValueError:
        # Fallback for weird names
        print(f"Skipping {log_dir.name}: parsing failed components={parts}")
        return False
        
    image_path = Path(f"data/evaluation2/images/{score_name}/{page_num}.png")
    if not image_path.exists():
        print(f"DEBUG: Default path failed: {image_path}. Trying fallback search...")
        found = list(Path("data/evaluation2/images").rglob(f"{page_num}.png"))
        if found:
            # Prefer path containing score_name
            for fpath in found:
                if score_name in str(fpath):
                    image_path = fpath
                    print(f"DEBUG: Resolved to {image_path} via rglob+score_name")
                    break
            else:
                image_path = found[0]
                print(f"DEBUG: Resolved to {image_path} via rglob (first match)")
        else:
            print(f"Error: Image not found for {log_dir.name} ({score_name}/{page_num})")
            return False

    with open(candidates_path, 'r') as f:
        candidates = json.load(f)
    
    print(f"DEBUG: Processing {log_dir.name}: {len(candidates)} candidates")
        
    if not candidates:
        return True # Processed (empty)

    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Failed to load image: {image_path}")
        return False
        
    # Prepare batch
    batch_tensors = []
    
    for box in candidates:
        if len(box) != 4: continue
        x1, y1, x2, y2 = box
        cx, cy = int((x1+x2)/2), int((y1+y2)/2)
        cw, ch = crop_size_from_bbox(box)
        crop = center_crop(img, cx, cy, cw, ch)
        crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        # PIL resize expects (Width, Height). IMG_SIZE is (Height, Width).
        # So we pass (IMG_SIZE[1], IMG_SIZE[0])
        tensor = transforms.ToTensor()(crop_pil.resize((IMG_SIZE[1], IMG_SIZE[0]), Image.BILINEAR))
        batch_tensors.append(tensor)
        
    if not batch_tensors:
        # Save empty results to allow evaluation to proceed
        with open(log_dir / "pipeline2_no_peak_scored.json", 'w') as f:
            json.dump([], f, indent=2)
        with open(log_dir / "pipeline2_no_peak_filtered_cnn.json", 'w') as f:
            json.dump([], f, indent=2)
        return True

    # Prepare batch and run inference in smaller chunks
    scores_list = []
    batch_size = 64
    
    for i in range(0, len(batch_tensors), batch_size):
        chunk = batch_tensors[i : i + batch_size]
        batch_t = torch.stack(chunk).to(DEVICE)
        batch_t = gpu_norm(batch_t)
        
        with torch.no_grad():
            logits = model(batch_t)
            chunk_scores = torch.sigmoid(logits).cpu().numpy().flatten()
            scores_list.append(chunk_scores)
            
    scores = np.concatenate(scores_list)
        
    scored_results = []
    filtered_boxes = []
    
    for i, box in enumerate(candidates):
        score = float(scores[i])
        scored_results.append({
            "bbox": box,
            "score": score
        })
        if score > threshold:
            filtered_boxes.append(box)
            
    # Save
    with open(log_dir / "pipeline2_no_peak_scored.json", 'w') as f:
        json.dump(scored_results, f, indent=2)
        
    with open(log_dir / "pipeline2_no_peak_filtered_cnn.json", 'w') as f:
        json.dump(filtered_boxes, f, indent=2)
        
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", default="logs/hybrid_generalization")
    parser.add_argument("--model", default="experiments/cnn_classifier/checkpoints/best_model.pth") # Adjust path if needed
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    
    # Verify model path. Usually in experiments/cnn_classifier/checkpoints/
    # Or current best might be elsewhere. User used `cnn_classifier_best.pth` conceptually.
    # Looking at `train.py` might reveal where it saves.
    # Taking a guess at `experiments/cnn_classifier/checkpoints/best_model.pth` or similar.
    
    if not os.path.exists(args.model):
        # Fallback search
        candidates = list(Path("experiments/cnn_classifier").rglob("best_model.pth"))
        if candidates:
            args.model = str(candidates[0])
            print(f"Resolved model to {args.model}")
        else:
            print("Model not found!")
            return

    model = get_model(args.model)
    gpu_norm = GPUNormalize(MEAN, STD).to(DEVICE)
    
    log_root = Path(args.logs)
    subdirs = sorted([d for d in log_root.iterdir() if d.is_dir()])
    
    print(f"Processing {len(subdirs)} directories...")
    
    count = 0
    for d in tqdm(subdirs):
        if process_dir(d, model, gpu_norm, args.threshold):
            count += 1
            
    print(f"Completed {count} pages.")

if __name__ == "__main__":
    main()
