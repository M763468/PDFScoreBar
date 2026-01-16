import cv2
from rapidocr_onnxruntime import RapidOCR
from pathlib import Path
import sys
import numpy as np

def run_ocr(image_path: Path, engine: RapidOCR):
    img = cv2.imread(str(image_path))
    if img is None:
        return None, "Load Error"

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Preprocessing
    # 1. Simple Thresholding (Otsu)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 2. Invert back (Black text on white BG)
    binary_white_bg = cv2.bitwise_not(binary)

    # Denoising
    kernel = np.ones((2,2), np.uint8)
    opened = cv2.morphologyEx(binary_white_bg, cv2.MORPH_OPEN, kernel)
    
    # Add borders (padding) because OCR sometimes fails on edge-touching text
    padded = cv2.copyMakeBorder(opened, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

    results = {}
    
    # Run RapidOCR
    # It returns a list of results, where each result is [dt_boxes, rec_res, score]
    # rec_res is the text.
    try:
        ocr_result, _ = engine(padded)
        if ocr_result:
            # Join all detected texts
            texts = [res[1] for res in ocr_result]
            results["RapidOCR"] = " ".join(texts)
        else:
            results["RapidOCR"] = "(No text)"
            
    except Exception as e:
        results["RapidOCR"] = f"Error: {e}"
            
    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/experiment_rest_ocr.py <crops_dir>")
        sys.exit(1)
        
    crops_dir = Path(sys.argv[1])
    
    # Initialize engine once
    engine = RapidOCR()
    
    # Filter for png files
    files = sorted(list(crops_dir.glob("*.png")))
    
    print(f"Processing {len(files)} images in {crops_dir} with RapidOCR...")
    print("-" * 60)
    print(f"{'File':<30} | {'RapidOCR Result':<20}")
    print("-" * 60)
    
    for f in files:
        if "debug" in f.name: continue
        
        results = run_ocr(f, engine)
        if results is None:
            print(f"{f.name:<30} | Load Error")
            continue
            
        print(f"{f.name:<30} | {results['RapidOCR']:<20}")

if __name__ == "__main__":
    main()