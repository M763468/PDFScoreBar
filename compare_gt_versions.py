import json
import os
from pathlib import Path

root = Path("/home/masaki_muramatsu/ws_PDFScoreBar_training/data/evaluation2/annotations")
va_root = root / "Va_Prokofiev_Symphony1"
p1_root = root / "prokofiev1"

pages = ["page_001", "page_002", "page_003", "page_004", "page_005", "page_006"]

print("Comparing Va_Prokofiev_Symphony1 (New) vs prokofiev1...")

for page in pages:
    p1_file = p1_root / page / "boxes_sorted.json"
    
    # helper to find the referenced file in Va (since it uses versioned names)
    va_dir = va_root / page
    # NEW FILE NAME
    va_file = va_dir / "boxes_sorted_v20260111.json"

    print(f"\n{page}:")
    
    if not p1_file.exists():
        print(f"  prokofiev1: MISSING ({p1_file})")
    else:
        s = p1_file.stat().st_size
        t = p1_file.stat().st_mtime
        print(f"  prokofiev1: {s} bytes, ts={t}")

    if not va_file.exists():
        print(f"  Va_Prokofiev: MISSING ({va_file})")
    else:
        s = va_file.stat().st_size
        t = va_file.stat().st_mtime
        print(f"  Va_Prokofiev: {s} bytes, ts={t}")

    if p1_file.exists() and va_file.exists():
        try:
            d1 = json.loads(p1_file.read_text())
            d2 = json.loads(va_file.read_text())
            
            # Normalize to compare count
            c1 = 0
            if isinstance(d1, list):
                if len(d1) > 0 and isinstance(d1[0], list):
                    c1 = len(d1)
                elif len(d1) > 0 and isinstance(d1[0], dict):
                    c1 = len(d1)
            
            c2 = 0
            if isinstance(d2, list):
                 c2 = len(d2) # usually list of dicts or list of lists
            
            print(f"  Count: prokofiev1={c1}, Va={c2}")
            if c1 != c2:
                print("  **MISMATCH DETECTED**")
            else:
                print("  Counts match.")
                
        except Exception as e:
            print(f"  Error comparing: {e}")
