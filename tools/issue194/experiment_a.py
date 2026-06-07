import json
from pathlib import Path
import numpy as np

PAGES = ["page_021", "page_022", "page_045", "page_053", "page_060"]
BASE_DIR = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate")

def load_numbering_base(page_id):
    path = BASE_DIR / page_id / "numbering_base.json"
    with open(path, "r") as f:
        return json.load(f)

def analyze_system_first_measure(page_id, data):
    results = []
    page = data["pages"][0]
    for sys_idx, system in enumerate(page["systems"]):
        staves = system.get("staves", [])
        measures = system.get("measures", [])
        if not staves or not measures:
            continue
        
        # Staff height (average if multiple)
        staff_heights = [s["bbox"][3] - s["bbox"][1] for s in staves]
        avg_staff_height = sum(staff_heights) / len(staff_heights)
        
        # Staff left edge (minimum x1)
        staff_left = min(s["bbox"][0] for s in staves)
        
        # Measure widths
        m_widths = [m["bbox"][2] - m["bbox"][0] for m in measures]
        median_width = np.median(m_widths)
        
        first_m = measures[0]
        first_width = first_m["bbox"][2] - first_m["bbox"][0]
        first_left = first_m["bbox"][0]
        
        # staff_left から first_bar (最初の measure の左端) までの距離
        # 実際には ghost_start が staff_left の位置にあるため、first_left はほぼ staff_left になる
        dist_to_first_bar = first_left - staff_left
        
        results.append({
            "sys_idx": sys_idx,
            "measure_count": len(measures),
            "first_bbox": first_m["bbox"],
            "first_width": first_width,
            "median_width": median_width,
            "avg_staff_height": avg_staff_height,
            "staff_left": staff_left,
            "ratio_to_median": first_width / median_width if median_width > 0 else 0,
            "ratio_to_staff_height": first_width / avg_staff_height if avg_staff_height > 0 else 0,
            "dist_to_first_bar": dist_to_first_bar
        })
    return results

def simulate_guards(results):
    print("--- Simulation Results ---")
    for page_id, sys_results in results.items():
        print(f"\nPage: {page_id}")
        for r in sys_results:
            sys_idx = r["sys_idx"]
            w = r["first_width"]
            med = r["median_width"]
            h = r["avg_staff_height"]
            
            # 判定ロジック
            # A1: width < 0.5 * median
            g1 = w < 0.5 * med
            # A2: width < 1.2 * staff_height (AGENTS.md で Deduplication Threshold が 1.2 * unit_size, unit_size は staff_height/4 程度？)
            # 五線の高さ staff_height に対して、小節幅が staff_height * 1.5 未満など
            g2 = w < 1.5 * h
            # A3: absolute width < 200px
            g3 = w < 200
            
            print(f"  Sys {sys_idx}: Width={w:.1f}, MedWidth={med:.1f}, StaffH={h:.1f}")
            print(f"    Guard A1 (w < 0.5*med): {'REJECT' if g1 else 'KEEP'} (ratio: {r['ratio_to_median']:.2f})")
            print(f"    Guard A2 (w < 1.5*h)  : {'REJECT' if g2 else 'KEEP'} (ratio: {r['ratio_to_staff_height']:.2f})")
            print(f"    Guard A3 (w < 200px)  : {'REJECT' if g3 else 'KEEP'}")

def main():
    all_results = {}
    for page_id in PAGES:
        data = load_numbering_base(page_id)
        all_results[page_id] = analyze_system_first_measure(page_id, data)
        
    simulate_guards(all_results)

if __name__ == "__main__":
    main()
