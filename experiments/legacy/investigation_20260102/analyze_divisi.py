import json
import os


def analyze_divisi(page_dir):
    debug_path = os.path.join(page_dir, "endbar_debug.json")
    if not os.path.exists(debug_path):
        return

    with open(debug_path, "r") as f:
        data = json.load(f)
        records = data.get("records", [])
        bands = data.get("bands", [])
        divisi_map = data.get("divisi_map", {})

    print(f"--- Divisi Analysis for {os.path.basename(page_dir)} ---")

    # Find band for col 1423
    target_col = 1423
    for rec in records:
        if rec.get("col") == target_col and "accepted" in rec.get("status"):
            band = rec.get("band")
            if band:
                cy = (band[0] + band[1]) / 2
                best_idx = -1
                for idx, (by1, by2) in enumerate(bands):
                    if by1 <= cy <= by2:
                        best_idx = idx
                        break

                print(f"Found Candidate at Col {target_col}: Band Index {best_idx}")
                print(f"  Band: {bands[best_idx]}")

                # Check Divisi Map
                if str(best_idx) in divisi_map:
                    info = divisi_map[str(best_idx)]
                    print(f"  Divisi Info: {info}")

                    # Check linked band
                    if info.get("has_top"):
                        print(f"  Has Top Link. Top Band: {bands[best_idx - 1]}")
                        # Check candidates in top band at 1423
                        top_cands = []
                        for r in records:
                            if (
                                r.get("band")
                                and r["band"][0] >= bands[best_idx - 1][0]
                                and r["band"][1] <= bands[best_idx - 1][1]
                            ):
                                if abs(r.get("col", -999) - target_col) < 20:
                                    top_cands.append(r)
                        print(f"  Top Candidates near {target_col}: {top_cands}")


if __name__ == "__main__":
    analyze_divisi(
        "logs/gt_rebuild_hybrid_eval/20260102T_bypass_row_filter_fix_rescue_dedup/per_page/page_004"
    )
