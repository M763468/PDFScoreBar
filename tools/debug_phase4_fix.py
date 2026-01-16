import json
import cv2
import sys
import os
from pathlib import Path
from rapidocr_onnxruntime import RapidOCR

# Add tools to path
sys.path.append('tools')
from generate_numbering_overrides import select_best_candidate

def debug_measure(img_path, target_coords, title):
    print(f"\n--- {title} ---")
    img = cv2.imread(img_path)
    if img is None:
        print(f"Error loading image: {img_path}")
        return
    
    x1, y1, x2, y2 = target_coords
    crop = img[max(0, y1-20):min(img.shape[0], y2+20), max(0, x1-20):min(img.shape[1], x2+20)]
    
    # RapidOCR
    ocr_engine = RapidOCR()
    
    ocr_res, _ = ocr_engine(crop)
    if not ocr_res:
        print("No OCR found")
        return

    print("Raw OCR:")
    for res in ocr_res:
        print(f"  {res[1]} (conf={res[2]:.2f})")
        
    val, score, debug = select_best_candidate(ocr_res, proc.shape[1], proc.shape[0])
    print(f"Result: {val} (Score: {score:.2f}, Debug: {debug})")

if __name__ == "__main__":
    # Case 3: Shostakovich P4 S4 M2 (poco animando, 5)
    # Bbox from investigation report: [733, 319, 853, 355]
    debug_measure(
        "data/evaluation2/images/Shosrakovich-Sym5-Va/page_004.png",
        [733, 319, 853, 355],
        "Shostakovich P4 S4 M2 (poco animando, 5)"
    )
