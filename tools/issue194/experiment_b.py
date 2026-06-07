import json
from pathlib import Path

SCORED_PATH = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/probe_scan/eval2_images_Va__Prokofiev_Symphony5_page_015/pipeline2_no_peak_scored.json")
FILTERED_PATH = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/probe_scan/eval2_images_Va__Prokofiev_Symphony5_page_015/pipeline2_no_peak_filtered_cnn.json")


def analyze_scores():
    if not SCORED_PATH.exists() or not FILTERED_PATH.exists():
        print("Warning: required issue194 log files are missing.")
        print(f"SCORED_PATH: {SCORED_PATH}")
        print(f"FILTERED_PATH: {FILTERED_PATH}")
        return

    with open(SCORED_PATH, "r") as f:
        scored_data = json.load(f)
    with open(FILTERED_PATH, "r") as f:
        json.load(f)
        
    sys10_filtered = [
        [580, 4005, 584, 4115],
        [1028, 4002, 1037, 4112],
        [1705, 4004, 1714, 4114],
        [2326, 4007, 2335, 4116],
        [2948, 4005, 2952, 4115],
        [3465, 4009, 3475, 4119]
    ]
    
    print("\n--- Search Sys 10 barlines in scored data ---")
    for target in sys10_filtered:
        found = False
        for item in scored_data:
            if isinstance(item, dict) and 'bbox' in item:
                bbox = item['bbox']
                score = item['score']
                if abs(bbox[0] - target[0]) <= 2 and abs(bbox[1] - target[1]) <= 2 and abs(bbox[2] - target[2]) <= 2 and abs(bbox[3] - target[3]) <= 2:
                    print(f"Target: {target} -> Found! BBox={bbox}, Score={score:.6f}")
                    found = True
                    break
        if not found:
            print(f"Target: {target} -> Not found in scored data")


if __name__ == "__main__":
    analyze_scores()
