
import json
import sys
import os

def analyze_band_count(page_dir):
    debug_path = os.path.join(page_dir, "endbar_debug.json")
    if not os.path.exists(debug_path):
        print("Not found")
        return

    with open(debug_path, 'r') as f:
        data = json.load(f)
        records = data.get("records", [])
        bands = data.get("bands", [])

    print(f"--- Band Analysis for {os.path.basename(page_dir)} ---")
    band_counts = {}
    
    for rec in records:
        status = rec.get("status")
        # accepted系 または scan_ratio_rel_low_rescued系 をカウント
        if status and ("accepted" in status or "rescued" in status):
            band = rec.get("band") # [y1, y2]
            if band:
                # band indexを探す、またはy座標でマッチング
                # endbar_debug.jsonには band_idx が直接含まれていない場合があるので
                # data['bands'] と照合する
                cy = (band[0] + band[1]) / 2
                best_idx = -1
                for idx, (by1, by2) in enumerate(bands):
                    if by1 <= cy <= by2:
                        best_idx = idx
                        break
                if best_idx != -1:
                    band_counts[best_idx] = band_counts.get(best_idx, 0) + 1

    # Check specific candidate
    target_col = 2473
    target_band_idx = -1
    for rec in records:
        if rec.get("col") == target_col:
            band = rec.get("band")
            if band:
                cy = (band[0] + band[1]) / 2
                for idx, (by1, by2) in enumerate(bands):
                    if by1 <= cy <= by2:
                        target_band_idx = idx
                        break
            print(f"Target Col {target_col}: Band Index {target_band_idx}, Count in this band: {band_counts.get(target_band_idx, 0)}")
            break

if __name__ == "__main__":
    analyze_band_count("logs/gt_rebuild_hybrid_eval/20260102T_bypass_row_filter_fix_rescue/per_page/page_001")
