import sys
from pathlib import Path
import json
import cv2
import numpy as np

# Import the filter logic
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.pipeline.steps.candidate_filters import _box_mask_overlap_ratio, filter_probe_candidates
from src.pipeline.steps.probe_scan import trim_box_to_ink

def main():
    mask_path = "logs/hybrid_generalization/verify_fixed_v10/20260330_080333/baseline/batch/page_001/page_001_staff_mask.png"
    img_path = "logs/full_pipeline_runs/20260330_080333/inputs/images/page_001.png"
    sr_img_path = "logs/hybrid_generalization/verify_fixed_v10/20260330_080333/sr/batch/page_001/page_001.png"
    
    mask_img = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    sr_img = cv2.imread(sr_img_path)
    
    h_img_sr, w_img_sr = sr_img.shape[:2]
    mask_img_resized = cv2.resize(mask_img, (w_img_sr, h_img_sr), interpolation=cv2.INTER_NEAREST)
    
    # Let's say we have an untrimmed candidate
    # Box from FP: (280, 3517, 281, 3588). Untrimmed might be full height: (280, 0, 281, h_img_sr)
    box_untrimmed = (280, 0, 281, h_img_sr)
    
    # 1. Old Logic (Filter then Trim)
    print("=== OLD LOGIC ===")
    keep, dropped = filter_probe_candidates(
        [box_untrimmed], sr_img, [], staff_mask=mask_img_resized, min_staff_overlap_ratio=0.05
    )
    if keep:
        print(f"Candidate kept by filter: {keep[0]}")
        trimmed = trim_box_to_ink(sr_img, keep[0], ink_threshold=180)
        print(f"Then trimmed to: {trimmed}")
    else:
        print(f"Dropped: {dropped}")
        
    print("\n=== NEW LOGIC ===")
    trimmed2 = trim_box_to_ink(sr_img, box_untrimmed, ink_threshold=180)
    print(f"Trimmed first: {trimmed2}")
    keep2, dropped2 = filter_probe_candidates(
        [trimmed2], sr_img, [], staff_mask=mask_img_resized, min_staff_overlap_ratio=0.05
    )
    if keep2:
        print(f"Candidate kept: {keep2[0]}")
    else:
        print(f"Dropped by filter: {dropped2}")

if __name__ == "__main__":
    main()
