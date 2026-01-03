
import cv2
import numpy as np
from pathlib import Path
import random

def visualize_crop_centers(dataset_root, output_dir, count=10):
    dataset_root = Path(dataset_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect all crops
    all_crops = []
    # Local TP/FP
    all_crops.extend(sorted((dataset_root / "local" / "tp").glob("*.png")))
    all_crops.extend(sorted((dataset_root / "local" / "fp").glob("*.png")))
    # DeepScores TP/FP
    all_crops.extend(sorted((dataset_root / "deepscores" / "tp").glob("*.png")))
    all_crops.extend(sorted((dataset_root / "deepscores" / "fp").glob("*.png")))
    
    if not all_crops:
        print("No crops found!")
        return
        
    random.seed(42)
    selected = random.sample(all_crops, min(len(all_crops), count))
    
    for crop_path in selected:
        img = cv2.imread(str(crop_path))
        if img is None:
            continue
            
        h, w = img.shape[:2]
        cx, cy = w // 2, h // 2
        
        # Draw Crosshair at Center
        # Red
        color = (0, 0, 255)
        # Horizontal line
        cv2.line(img, (cx - 10, cy), (cx + 10, cy), color, 1)
        # Vertical line
        cv2.line(img, (cx, cy - 10), (cx, cy + 10), color, 1)
        
        # Draw small box (3x3)
        # cv2.rectangle(img, (cx-1, cy-1), (cx+1, cy+1), color, -1)
        
        parts = crop_path.parts
        # e.g. .../v3/local/tp/filename.png
        source = parts[-3] # local/deepscores
        label = parts[-2] # tp/fp
        
        save_name = f"{source}_{label}_{crop_path.name}"
        save_path = output_dir / save_name
        cv2.imwrite(str(save_path), img)
        print(f"Saved {save_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    
    visualize_crop_centers(args.dataset_root, args.output_dir)
