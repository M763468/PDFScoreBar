import argparse
import json
import cv2
import sys
import shutil
from pathlib import Path
import subprocess

def run_command(cmd, desc):
    # print(f"--- {desc} ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error in {desc}:")
        print(result.stderr)
        return False
    return True

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

def ensure_numbering_json(work_name, page_str, image_path, barline_path, mask_root, output_dir):
    """
    Ensures numbering_initial.json exists. If not, runs add_measure_numbers.py.
    """
    initial_json = output_dir / "numbering_initial.json"
    if initial_json.exists():
        return initial_json

    # Construct mask paths
    # logs/hybrid_generalization/eval2_{work}_{page}/baseline/{page}/{page}/{page}_debug_...
    mask_dir = mask_root / f"eval2_{work_name}_{page_str}/baseline/{page_str}/{page_str}"
    staff_mask = mask_dir / f"{page_str}_debug_3_staff.png"
    
    if not staff_mask.exists():
        print(f"  [Skip] Masks not found: {mask_dir}")
        return None
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        ".venv_omr_dln/bin/python", "tools/add_measure_numbers.py",
        "--barlines", str(barline_path),
        "--staff-mask", str(staff_mask),
        "--image", str(image_path),
        "--output-json", str(initial_json)
    ]
    
    if run_command(cmd, f"Generate Numbering {work_name}/{page_str}"):
        return initial_json
    else:
        return None

def create_dataset(gt_root, images_root, annotations_root, mask_root, output_root):
    """
    Iterates GT, extracts crops, saves to train/0 and train/1.
    """
    
    # Setup Output
    train_0 = output_root / "train" / "0" # Normal
    train_1 = output_root / "train" / "1" # Rest
    train_0.mkdir(parents=True, exist_ok=True)
    train_1.mkdir(parents=True, exist_ok=True)
    
    # Iterate GT files
    gt_files = sorted(list(gt_root.glob("**/rest_gt.json")))
    print(f"Found {len(gt_files)} Ground Truth files.")
    
    count_0 = 0
    count_1 = 0
    
    for gt_path in gt_files:
        # Path: .../rest_gt/<work>/<page>/rest_gt.json
        parts = gt_path.parts
        page_name = parts[-2] # e.g. page_001
        work_name = parts[-3] # e.g. prokofiev5
        
        print(f"Processing {work_name} / {page_name}...")
        
        # Load GT
        with open(gt_path, 'r') as f:
            gt_data = json.load(f)
            overrides = gt_data.get("overrides", [])
            
        rest_indices = {item['measure_index']: item['rest_count'] for item in overrides}
        
        # Locate Resources
        image_path = images_root / work_name / f"{page_name}.png"
        if not image_path.exists():
            print(f"  [Skip] Image not found: {image_path}")
            continue
            
        gt_dir = annotations_root / work_name / page_name
        # Find latest sorted boxes
        barlines = sorted(list(gt_dir.glob("boxes_sorted_*.json")))
        if not barlines:
             barlines = sorted(list(gt_dir.glob("boxes_sorted.json")))
             
        if not barlines:
            print(f"  [Skip] Barlines not found in: {gt_dir}")
            continue
        barline_path = barlines[-1]
        
        # Ensure Numbering (Measure BBoxes)
        # Use a temporary or cache dir for these intermediate jsons
        # We can use logs/cache_dataset_gen
        cache_dir = Path("logs/cache_dataset_gen") / work_name / page_name
        
        numbering_json_path = ensure_numbering_json(
            work_name, page_name, image_path, barline_path, mask_root, cache_dir
        )
        
        if not numbering_json_path:
            continue
            
        with open(numbering_json_path, 'r') as f:
            numbering_data = json.load(f)
            
        bboxes = map_global_index_to_bbox(numbering_data)
        
        # Load Image
        img = cv2.imread(str(image_path))
        if img is None:
            print(f"  [Error] Could not read image: {image_path}")
            continue
            
        h_img, w_img = img.shape[:2]
        
        # Process Measures
        for idx, bbox in enumerate(bboxes):
            x1, y1, x2, y2 = bbox
            
            # Label
            label = 1 if idx in rest_indices else 0
            
            # Crop (with margin?)
            # Add margin to capture context and avoid cut-off numbers
            margin = 20
            cx1 = max(0, x1 - margin)
            cy1 = max(0, y1 - margin)
            cx2 = min(w_img, x2 + margin)
            cy2 = min(h_img, y2 + margin)
            
            crop = img[cy1:cy2, cx1:cx2]
            
            if crop.size == 0: continue
            
            # Filter extremely small crops (noise)
            # Threshold needs to handle the padding 
            if crop.shape[0] < 10 or crop.shape[1] < 10: continue
            
            # Save
            filename = f"{work_name}_{page_name}_{idx:04d}.jpg"
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
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/rest_gt"))
    parser.add_argument("--images-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--annotations-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--mask-root", type=Path, default=Path("logs/hybrid_generalization"))
    parser.add_argument("--output-root", type=Path, required=True)
    
    args = parser.parse_args()
    
    create_dataset(
        args.gt_root,
        args.images_root,
        args.annotations_root,
        args.mask_root,
        args.output_root
    )
