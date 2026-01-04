
# [EXPERIMENTAL] Utility to reconstruct final detector output from intermediate logs.
# Created on 2026-01-04 to simulate production input for numbering tests.

import json
from pathlib import Path
from typing import List, Tuple

def load_json(path: Path):
    with open(path, 'r') as f:
        return json.load(f)

def bboxes_match(b1: List[int], b2: List[int], tol: int = 1) -> bool:
    return all(abs(v1 - v2) <= tol for v1, v2 in zip(b1, b2))

import argparse
import json
from pathlib import Path
from typing import List, Tuple

def load_json(path: Path):
    with open(path, 'r') as f:
        return json.load(f)

def bboxes_match(b1: List[int], b2: List[int], tol: int = 1) -> bool:
    return all(abs(v1 - v2) <= tol for v1, v2 in zip(b1, b2))

def reconstruct(page_id: str):
    base_dir = Path(f"logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/{page_id}")
    if not base_dir.exists():
        print(f"Error: Directory not found: {base_dir}")
        return
    
    # 1. Load candidates
    geom_kept_path = base_dir / "geom_kept.json"
    end_recovered_path = base_dir / "end_recovered.json"
    
    geom_kept = load_json(geom_kept_path) if geom_kept_path.exists() else []
    end_recovered = load_json(end_recovered_path) if end_recovered_path.exists() else []
    
    print(f"[{page_id}] Loaded {len(geom_kept)} from geom_kept")
    print(f"[{page_id}] Loaded {len(end_recovered)} from end_recovered")
    
    candidates = geom_kept + end_recovered
    print(f"[{page_id}] Total candidates: {len(candidates)}")
    
    # 2. Identify rejected
    rejected = []
    
    # Clefs Keys Filter
    ck_filter_path = base_dir / "clefs_keys_filter.json"
    if ck_filter_path.exists():
        ck_filter = load_json(ck_filter_path)
        if "rejected" in ck_filter:
            print(f"[{page_id}] Clefs/Keys rejected count: {len(ck_filter['rejected'])}")
            for item in ck_filter['rejected']:
                rejected.append(item['bbox'])
            
    # Barline Clefs Low Filter
    bcl_filter_path = base_dir / "barline_clefs_low_filter.json"
    if bcl_filter_path.exists():
        bcl_filter = load_json(bcl_filter_path)
        if "rejected" in bcl_filter:
            print(f"[{page_id}] Low Ratio rejected count: {len(bcl_filter['rejected'])}")
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
            
    print(f"[{page_id}] Removed {rejected_count} rejected items.")
    print(f"[{page_id}] Final count: {len(final_list)}")
    
    # 4. Save
    out_path = base_dir / "final_predictions.json"
    with open(out_path, 'w') as f:
        json.dump(final_list, f, indent=2)
    print(f"[{page_id}] Saved to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=str, default="page_10")
    args = parser.parse_args()
    reconstruct(args.page)
