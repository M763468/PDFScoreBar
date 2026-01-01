import json
import sys
import os

def analyze_band_y(page_dir):
    debug_path = os.path.join(page_dir, "endbar_debug.json")
    if not os.path.exists(debug_path):
        return

    with open(debug_path, 'r') as f:
        data = json.load(f)
        records = data.get("records", [])
        bands = data.get("bands", [])

    y_centers = []
    target_y = None
    
    for rec in records:
        status = rec.get("status")
        if status and ("accepted" in status or "rescued" in status):
            band = rec.get("band") 
            if band:
                cy = (band[0] + band[1]) / 2
                # Check if in Band 0
                if bands and bands[0][0] <= cy <= bands[0][1]:
                    y_centers.append(cy)
                    if rec.get("col") == 2473:
                        target_y = cy

    print(f"Band 0 Candidates: {len(y_centers)}")
    # print(f"Y Centers: {y_centers}")
    print(f"Target (2473) Y: {target_y}")
    
    if y_centers:
        print(f"Min: {min(y_centers)}, Max: {max(y_centers)}, Range: {max(y_centers)-min(y_centers)}")

if __name__ == "__main__":
    analyze_band_y("logs/gt_rebuild_hybrid_eval/20260102T_bypass_row_filter_fix_rescue/per_page/page_001")