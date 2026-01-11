import argparse
import json
import cv2
import sys
import shutil
from pathlib import Path
import subprocess

def map_global_index_to_bbox(numbering_data):
    """
    Returns a list mapping global_index -> bbox [x1, y1, x2, y2]
    """
    mapping = []
    if "pages" in numbering_data:
        page = numbering_data["pages"][0]
        for system in page["systems"]:
            for measure in system["measures"]:
                mapping.append(measure['bbox'])
    return mapping

def create_dataset_from_configs(config_paths, output_root):
    """
    Iterates over pages defined in the provided config files and creates training data.
    """
    
    # Setup Output
    train_0 = output_root / "train" / "0" # Normal
    train_1 = output_root / "train" / "1" # Rest
    train_0.mkdir(parents=True, exist_ok=True)
    train_1.mkdir(parents=True, exist_ok=True)
    
    count_0 = 0
    count_1 = 0
    
    for config_path in config_paths:
        print(f"Loading config: {config_path}")
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        pages = config.get("pages", [])
        print(f"  Found {len(pages)} pages.")
        
        for page in pages:
            name = page["name"]
            print(f"Processing {name}...")
            
            # 1. Load Ground Truth (rest_gt)
            gt_path = Path(page["rest_gt"])
            if not gt_path.exists():
                print(f"  [Skip] GT not found: {gt_path}")
                continue
                
            with open(gt_path, 'r') as f:
                gt_data = json.load(f)
                overrides = gt_data.get("overrides", [])
            
            rest_indices = {item['measure_index']: item['rest_count'] for item in overrides}
            
            # 2. Load Numbering (for measure bounding boxes)
            if "numbering" not in page:
                 print(f"  [Skip] Numbering path not in config.")
                 continue
            
            numbering_path = Path(page["numbering"])
            if not numbering_path.exists():
                 print(f"  [Skip] Numbering file not found: {numbering_path}")
                 continue
                 
            with open(numbering_path, 'r') as f:
                numbering_data = json.load(f)
            
            bboxes = map_global_index_to_bbox(numbering_data)
            
            # 3. Load Image
            img_path = Path(page["image"])
            if not img_path.exists():
                print(f"  [Skip] Image not found: {img_path}")
                continue
                
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"  [Error] Could not read image: {img_path}")
                continue
            
            h_img, w_img = img.shape[:2]
            
            # 4. Process Measures
            for idx, bbox in enumerate(bboxes):
                x1, y1, x2, y2 = bbox
                
                # Label
                label = 1 if idx in rest_indices else 0
                
                # Crop (with margin)
                margin = 20
                cx1 = max(0, x1 - margin)
                cy1 = max(0, y1 - margin)
                cx2 = min(w_img, x2 + margin)
                cy2 = min(h_img, y2 + margin)
                
                crop = img[cy1:cy2, cx1:cx2]
                
                if crop.size == 0: continue
                
                # Filter extremely small crops
                if crop.shape[0] < 10 or crop.shape[1] < 10: continue
                
                # Save
                filename = f"{name}_{idx:04d}.jpg"
                target_dir = train_1 if label == 1 else train_0
                cv2.imwrite(str(target_dir / filename), crop)
                
                if label == 1:
                    count_1 += 1
                else:
                    count_0 += 1
                    
    print("\nDataset Generation Complete.")
    print(f"  Rest Samples (1): {count_1}")
    print(f"  Normal Samples (0): {count_0}")
    print(f"  Output: {output_root}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs='+', type=Path, required=True, help="List of rest_gt config JSON files")
    parser.add_argument("--output-root", type=Path, required=True)
    
    args = parser.parse_args()
    
    create_dataset_from_configs(
        args.configs,
        args.output_root
    )
