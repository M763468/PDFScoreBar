
import sys
import json
import cv2
import numpy as np
from pathlib import Path

# Add project root
sys.path.append(".")

from src.measure_numbering.types import Staff, Barline, BBox
from src.measure_numbering.builder import SystemBuilder

def main():
    # Paths (Hardcoded for Page 3 expansion)
    img_path = "data/evaluation2/images/expansion/page_3.png"
    # Note: Using the mask to infer staves as usually done in pipeline, but here we can mock staves from `numbering_initial.json` or just use the mask directly?
    # The builder takes Staves and Barlines.
    # We can invoke the pipeline's staff extractor? 
    # Or cleaner: load the already generated 'numbering_initial.json' which IS the output of the pipeline, 
    # but that doesn't tell us WHY it merged.
    
    # Better: Use the same inputs as add_measure_numbers.py
    barlines_path = "/home/masaki_muramatsu/ws_PDFScoreBar_training/data/evaluation/annotations/page_003/boxes_sorted_v20260111.json"
    mask_path = "/home/masaki_muramatsu/ws_PDFScoreBar_training/logs/hybrid_generalization/sr_eval_smoke_page3/baseline/page_3/page_3/page_3_debug_3_staff.png"
    
    # Load Image
    img = cv2.imread(img_path)
    if img is None:
        print(f"Failed to load image: {img_path}")
        return

    # Load Barlines
    with open(barlines_path) as f:
        raw_bl = json.load(f)
    barlines = []
    # normalize logic copied from add_measure_numbers
    raw_list = []
    for item in raw_bl:
        if isinstance(item, list) and len(item) == 4: raw_list.append(item)
        elif isinstance(item, dict) and "barline_location" in item: raw_list.append(item["barline_location"])
    
    for b in raw_list:
        barlines.append(Barline(bbox=BBox(*b)))

    h, w = img.shape[:2]  # <--- DEFINED HERE

    # Load Staves (using correct StaffExtractor)
    from src.measure_numbering.pipeline import StaffExtractor
    extractor = StaffExtractor()
    
    print("Extracting staves...")
    # StaffExtractor uses paths, so we don't need to load cv2 mask manually if we pass path
    # But wait, extractor.extract takes Path object
    staves = extractor.extract(Path(mask_path), (w, h))
    print(f"Extracted {len(staves)} staves.")

    # Apply Builder with Debug Prints
    print("Running SystemBuilder...")
    builder = SystemBuilder()
    
    # We will Monkey Patch the `_check_aligned_connection` to print detailed info
    original_check = builder._check_aligned_connection
    
    def debug_check(s1, s2, aligned_pairs, image):
        res = original_check(s1, s2, aligned_pairs, image)
        
        # Calculate Gap
        gap = s2.bbox.y1 - s1.bbox.y2
        
        print(f"\nChecking Staves: Y={s1.bbox.y1}-{s1.bbox.y2} vs Y={s2.bbox.y1}-{s2.bbox.y2} (Gap: {gap})")
        print(f"  Aligned Pairs: {len(aligned_pairs)}")
        print(f"  Result: {res}")
        
        if res:
             print("  *** CONNECTED ***")
             # Save debug crop of the gap
             # Re-extract gap logic just for viz
             x1 = min(p[0].bbox.x1 for p in aligned_pairs)
             x2 = max(p[0].bbox.x2 for p in aligned_pairs)
             # Expand x range to cover all pairs
             
             # Visualize on copy
             viz = img.copy()
             cv2.rectangle(viz, (int(x1)-10, int(s1.bbox.y2)), (int(x2)+10, int(s2.bbox.y1)), (0, 0, 255), 2)
             cv2.imwrite(f"debug_connection_{s1.bbox.y1}_{s2.bbox.y1}.png", viz)
             
        return res

    builder._check_aligned_connection = debug_check
    
    systems = builder.build_systems(staves, barlines, image=img)
    print(f"\nTotal Systems Built: {len(systems)}")
    for i, sys in enumerate(systems):
        print(f"System {i+1}: {len(sys.staves)} staves")

if __name__ == "__main__":
    main()
