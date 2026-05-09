import cv2
import json
import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from src.pipeline.probe_detector.bands import resolve_bands, BandSelectionConfig

out_dir = Path("logs/issue120_final_residuals/band_analysis")
out_dir.mkdir(exist_ok=True, parents=True)

examples = [
    {
        "type": "high_ink (Seed Miss & Tall Band Dilution)",
        "score": "Shostakovich-Festival_Overture_Va",
        "page": "page_008",
        "gt_box": [1045, 3669, 1049, 3786], # gt0
        "staff_mask_path": "logs/hybrid_generalization/verification_full_v12_restore/Shostakovich-Festival_Overture_Va/baseline/batch/page_008/page_008_staff_mask.png",
        "hybrid_json": "logs/full_pipeline_runs/issue120_final_v1/Shostakovich-Festival_Overture_Va/intermediate/probe_scan/page_008/hybrid_results/page_008_hybrid.json"
    },
    {
        "type": "low_ink (Severe Fading)",
        "score": "Va_Prokofiev_Symphony1",
        "page": "page_001",
        "gt_box": [1688, 3816, 1693, 3968], # gt35
        "staff_mask_path": "logs/hybrid_generalization/verification_full_v12_restore/Va_Prokofiev_Symphony1/baseline/batch/page_001/page_001_staff_mask.png",
        "hybrid_json": "logs/full_pipeline_runs/issue120_final_v1/Va_Prokofiev_Symphony1/intermediate/probe_scan/page_001/hybrid_results/page_001_hybrid.json"
    }
]

for ex in examples:
    img_path = Path(f"data/evaluation2/images/{ex['score']}/{ex['page']}.png")
    base_img = cv2.imread(str(img_path))
    if base_img is None:
        print(f"Failed to load {img_path}")
        continue
        
    staff_mask = cv2.imread(ex['staff_mask_path'], cv2.IMREAD_GRAYSCALE)
    if staff_mask is None:
        print(f"Failed to load mask {ex['staff_mask_path']}")
        continue

    hybrid_path = Path(ex['hybrid_json'])
    existing_boxes = []
    if hybrid_path.exists():
        with open(hybrid_path) as f:
            existing_boxes = json.load(f)

    band_selection = BandSelectionConfig(band_source="hybrid_staff_mask", band_cluster_max_dist=None, band_min_row_count=3)
    bands = resolve_bands(staff_mask=staff_mask, existing_boxes=existing_boxes, row_stats=None, config=band_selection)

    gt_box = ex['gt_box']
    gt_cy = (gt_box[1] + gt_box[3]) / 2.0
    
    target_band = None
    for y1, y2 in bands:
        if y1 <= gt_cy <= y2:
            target_band = (y1, y2)
            break
            
    if target_band is None:
        target_band = min(bands, key=lambda b: min(abs(b[0] - gt_cy), abs(b[1] - gt_cy)))
        
    by1, by2 = target_band
    
    # Calculate crop region
    # We want to show the band and a bit of margin
    margin_y = 100
    margin_x = 100
    crop_y1 = max(0, min(by1, gt_box[1]) - margin_y)
    crop_y2 = min(base_img.shape[0]-1, max(by2, gt_box[3]) + margin_y)
    crop_x1 = max(0, gt_box[0] - margin_x)
    crop_x2 = min(base_img.shape[1]-1, gt_box[2] + margin_x)
    
    crop = base_img[crop_y1:crop_y2, crop_x1:crop_x2].copy()
    
    # Coordinates relative to crop
    c_by1 = by1 - crop_y1
    c_by2 = by2 - crop_y1
    c_gx1 = gt_box[0] - crop_x1
    c_gy1 = gt_box[1] - crop_y1
    c_gx2 = gt_box[2] - crop_x1
    c_gy2 = gt_box[3] - crop_y1
    
    # Draw Band (Blue, semi-transparent overlay)
    overlay = crop.copy()
    cv2.rectangle(overlay, (0, c_by1), (crop.shape[1]-1, c_by2), (255, 0, 0), -1)
    cv2.addWeighted(overlay, 0.2, crop, 0.8, 0, crop)
    
    # Draw Band boundaries
    cv2.line(crop, (0, c_by1), (crop.shape[1]-1, c_by1), (255, 0, 0), 2)
    cv2.line(crop, (0, c_by2), (crop.shape[1]-1, c_by2), (255, 0, 0), 2)
    cv2.putText(crop, f"Band Height: {by2 - by1}", (5, c_by1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
    
    # Draw GT Box (Red)
    cv2.rectangle(crop, (c_gx1, c_gy1), (c_gx2, c_gy2), (0, 0, 255), 2)
    cv2.putText(crop, f"GT Height: {gt_box[3] - gt_box[1]}", (c_gx2 + 10, c_gy1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    
    out_name = out_dir / f"{ex['type'].split(' ')[0]}_{ex['score']}_{ex['page']}.png"
    cv2.imwrite(str(out_name), crop)
    print(f"Saved {out_name}")
