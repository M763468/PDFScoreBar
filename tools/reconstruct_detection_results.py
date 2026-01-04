
import json
from pathlib import Path
from typing import List, Tuple

def load_json(path: Path):
    with open(path, 'r') as f:
        return json.load(f)

def bboxes_match(b1: List[int], b2: List[int], tol: int = 1) -> bool:
    return all(abs(v1 - v2) <= tol for v1, v2 in zip(b1, b2))

def reconstruct():
    base_dir = Path("logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10")
    
    # 1. Load candidates
    geom_kept = load_json(base_dir / "geom_kept.json")
    end_recovered = load_json(base_dir / "end_recovered.json")
    
    print(f"Loaded {len(geom_kept)} from geom_kept")
    print(f"Loaded {len(end_recovered)} from end_recovered")
    
    candidates = geom_kept + end_recovered
    print(f"Total candidates: {len(candidates)}")
    
    # 2. Identify rejected
    rejected = []
    
    # Clefs Keys Filter
    ck_filter = load_json(base_dir / "clefs_keys_filter.json")
    if "rejected" in ck_filter:
        print(f"Clefs/Keys rejected count: {len(ck_filter['rejected'])}")
        for item in ck_filter['rejected']:
            rejected.append(item['bbox'])
            
    # Barline Clefs Low Filter
    bcl_filter = load_json(base_dir / "barline_clefs_low_filter.json")
    if "rejected" in bcl_filter:
        print(f"Low Ratio rejected count: {len(bcl_filter['rejected'])}")
        for item in bcl_filter['rejected']:
            rejected.append(item['bbox'])
            
    # 3. Filter
    final_list = []
    rejected_count = 0
    
    for box in candidates:
        is_rejected = False
        for r_box in rejected:
            if bboxes_match(box, r_box):
                is_rejected = True
                break
        
        if is_rejected:
            rejected_count += 1
        else:
            final_list.append(box)
            
    print(f"Removed {rejected_count} rejected items.")
    print(f"Final count: {len(final_list)}")
    
    # 4. Save
    out_path = base_dir / "final_predictions.json"
    with open(out_path, 'w') as f:
        json.dump(final_list, f, indent=2)
    print(f"Saved to {out_path}")

if __name__ == "__main__":
    reconstruct()
