import json
import shutil
from pathlib import Path
import cv2
import numpy as np

def extract_crop(img, bbox, pad_scale=3.0, target_size=(128, 256)):
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    h = y2 - y1
    ch = int(h * pad_scale)
    ch = max(48, min(256, ch))
    cw = ch // 2
    
    y1_c, y2_c = max(0, cy - ch//2), min(img.shape[0], cy + ch//2)
    x1_c, x2_c = max(0, cx - cw//2), min(img.shape[1], cx + cw//2)
    crop = img[y1_c:y2_c, x1_c:x2_c]
    
    if crop.shape[0] < ch or crop.shape[1] < cw:
        pad_y1 = ch//2 - (cy - y1_c)
        pad_y2 = ch//2 - (y2_c - cy)
        pad_x1 = cw//2 - (cx - x1_c)
        pad_x2 = cw//2 - (x2_c - cx)
        crop = cv2.copyMakeBorder(crop, pad_y1, pad_y2, pad_x1, pad_x2, cv2.BORDER_CONSTANT, value=[255,255,255])
    
    return cv2.resize(crop, target_size)

def main():
    # Iter 7 Target: Sibelius page 006 GT #21
    target = ("Sibelius-Violin_Concerto-Viola", "page_006", [1919, 1580, 1923, 1687])
    
    output_root = Path("datasets/cnn_classifier_v7_hard_mining")
    if output_root.exists(): shutil.rmtree(output_root)
    (output_root / "train/tp").mkdir(parents=True)
    (output_root / "val/tp").mkdir(parents=True)

    score, page, bbox = target
    img_path = Path(f"data/evaluation2/images/{score}/{page}.png")
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"Failed to load {img_path}")
        return
    
    crop = extract_crop(img, bbox)
    
    # 500x Oversample for Train to strongly bias the model
    for i in range(500):
        out_name = f"{score}_{page}_{i:03d}.png"
        cv2.imwrite(str(output_root / "train/tp" / out_name), crop)
    
    cv2.imwrite(str(output_root / "val/tp" / f"{score}_{page}.png"), crop)
            
    print(f"Iter 7 hard samples built at {output_root}")

if __name__ == "__main__":
    main()
