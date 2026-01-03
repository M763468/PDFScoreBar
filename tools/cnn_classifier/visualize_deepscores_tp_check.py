
import cv2
import numpy as np
import json
from pathlib import Path
from PIL import Image

def load_palette_index(seg_path: Path) -> np.ndarray:
    seg_img = Image.open(seg_path)
    if seg_img.mode != "P":
        seg_img = seg_img.convert("P")
    return np.array(seg_img)

def find_components(mask: np.ndarray):
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    comps = []
    for idx in range(1, num):
        x, y, w, h, area = stats[idx].tolist()
        comps.append(
            {
                "label": idx,
                "bbox": [x, y, x + w - 1, y + h - 1],
                "w": w,
                "h": h,
                "area": area,
            }
        )
    return comps

def visualize_deepscores_tp(ds_root, output_dir, count=5):
    ds_root = Path(ds_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    seg_root = ds_root / "segmentation"
    img_root = ds_root / "images"
    
    seg_files = sorted(seg_root.glob("*_seg.png"))[:count]
    
    # Relaxed Filters
    palette_index = 3
    min_area = 10
    min_height = 5
    
    for seg_path in seg_files:
        print(f"Processing {seg_path.name}...")
        image_name = seg_path.name.replace("_seg.png", ".png")
        image_path = img_root / image_name
        
        if not image_path.exists():
            print(f"Image not found: {image_path}")
            continue
            
        img = cv2.imread(str(image_path))
        vis_img = img.copy()
        
        # Load Segmentation
        seg_np = load_palette_index(seg_path)
        mask = (seg_np == palette_index).astype(np.uint8) * 255
        comps = find_components(mask)
        
        valid_count = 0
        for comp in comps:
            if comp["area"] < min_area:
                continue
            if comp["h"] < min_height:
                continue
            
            # Draw valid TP
            x1, y1, x2, y2 = comp["bbox"]
            # Green, Thickness 2
            cv2.rectangle(vis_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            valid_count += 1
            
        save_path = output_dir / f"vis_tp_{image_name}"
        cv2.imwrite(str(save_path), vis_img)
        print(f"Saved {save_path} with {valid_count} TPs.")

if __name__ == "__main__":
    visualize_deepscores_tp(
        "/mnt/d/datasets/DeepScoresV2/ds2_dense",
        "logs/cnn_classifier/deepscores_tp_check"
    )
