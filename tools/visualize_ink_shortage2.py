import csv
import ast
from pathlib import Path
import cv2
import numpy as np

csv_path = Path("logs/issue120_final_residuals/residual_trace.csv")
out_dir = Path("logs/issue120_final_residuals/ink_analysis")
out_dir.mkdir(exist_ok=True, parents=True)

with open(csv_path, newline='') as f:
    reader = csv.DictReader(f)
    rows = [r for r in reader if r['type'] == 'FN' and r['reason'] == 'seed_miss_or_probe_reject']

examples = []
low_ink = []
high_ink = []

for row in rows:
    score = row['score']
    page = row['page']
    bbox = ast.literal_eval(row['bbox'])
    gt_id = row['id']
    
    img_path = f"data/evaluation2/images/{score}/{page}.png"
    img = cv2.imread(img_path)
    if img is None:
        continue
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ink = (gray < 180).astype(np.uint8) * 255
    
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1]-1, x2), min(img.shape[0]-1, y2)
    
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    area = box_w * box_h
    
    ink_pixels = np.sum(ink[y1:y2, x1:x2] == 255)
    ink_ratio = ink_pixels / area
    
    # Store for visualization
    record = {
        'row': row, 'img': img, 'ink': ink, 
        'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 
        'ink_ratio': ink_ratio, 'box_w': box_w, 'box_h': box_h
    }
    
    if ink_ratio < 0.7 and len(low_ink) < 3:
        low_ink.append(record)
    elif ink_ratio > 0.9 and len(high_ink) < 3:
        high_ink.append(record)
        
    if len(low_ink) == 3 and len(high_ink) == 3:
        break

for item in low_ink + high_ink:
    row = item['row']
    img, ink = item['img'], item['ink']
    x1, y1, x2, y2 = item['x1'], item['y1'], item['x2'], item['y2']
    ink_ratio = item['ink_ratio']
    box_w, box_h = item['box_w'], item['box_h']
    
    pad = 20
    cx, cy = (x1+x2)//2, (y1+y2)//2
    crop_w, crop_h = box_w + pad*2, box_h + pad*2
    cx1 = max(0, cx - crop_w//2)
    cx2 = min(img.shape[1]-1, cx + crop_w//2)
    cy1 = max(0, cy - crop_h//2)
    cy2 = min(img.shape[0]-1, cy + crop_h//2)
    
    crop_orig = img[cy1:cy2, cx1:cx2].copy()
    crop_ink = cv2.cvtColor(ink[cy1:cy2, cx1:cx2], cv2.COLOR_GRAY2BGR)
    
    bx1, by1 = x1 - cx1, y1 - cy1
    bx2, by2 = x2 - cx1, y2 - cy1
    
    cv2.rectangle(crop_orig, (bx1, by1), (bx2, by2), (0, 0, 255), 1)
    cv2.rectangle(crop_ink, (bx1, by1), (bx2, by2), (0, 0, 255), 1)
    
    text = f"Ink: {ink_ratio:.2f}"
    cv2.putText(crop_orig, text, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    cv2.putText(crop_ink, text, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    
    combined = np.hstack((crop_orig, crop_ink))
    
    prefix = "low_ink" if ink_ratio < 0.7 else "high_ink"
    out_name = out_dir / f"{prefix}_{row['score']}_{row['page']}_gt{row['id']}.png"
    cv2.imwrite(str(out_name), combined)
    print(f"Saved {out_name} - Ratio: {ink_ratio:.2f}")

