import json
import logging
from pathlib import Path

VERIFY_ROOT = Path("logs/hybrid_generalization/verify_fixed_v10")
INVENTORY_PATH = Path("logs/issue36_prep/20260208_bench_inventory.json")

def find_mapping():
    if not INVENTORY_PATH.exists():
        print(f"Error: {INVENTORY_PATH} not found.")
        return

    inv_data = json.loads(INVENTORY_PATH.read_text())
    scores = sorted(list(set(rec["score"] for rec in inv_data.get("records", []))))
    
    score_to_pages = {}
    for score in scores:
        pages = [rec["page"] for rec in inv_data["records"] if rec["score"] == score]
        score_to_pages[score] = pages

    mapping = {}
    run_dirs = sorted([d for d in VERIFY_ROOT.iterdir() if d.is_dir() and d.name.startswith("202")])
    
    # 1. First pass: explicit run.sh or detection content
    for score in scores:
        for run_dir in reversed(run_dirs):
            run_sh = run_dir / "baseline" / "batch" / "run.sh"
            if run_sh.exists() and score in run_sh.read_text():
                mapping[score] = run_dir.name
                break
            
            p1_det = run_dir / "baseline" / "batch" / "page_001" / "page_001_detections.json"
            if p1_det.exists() and score in p1_det.read_text():
                mapping[score] = run_dir.name
                break

    # 2. Second pass: Page Count Fallback for remaining
    for score in scores:
        if score in mapping: continue
        
        target_pages = set(score_to_pages[score])
        print(f"Searching for {score} (Pages: {len(target_pages)})...")
        
        for run_dir in reversed(run_dirs):
            # Check baseline/batch directory count
            batch_root = run_dir / "baseline" / "batch"
            if not batch_root.exists(): continue
            
            run_pages = set([d.name for d in batch_root.iterdir() if d.is_dir() and d.name.startswith("page_")])
            
            # If the set of pages matches perfectly, it's highly likely the correct run
            if run_pages == target_pages:
                # Double check omr_sr exists for all
                omr_root = run_dir / "omr_sr"
                found_all_omr = True
                for p in target_pages:
                    if not (omr_root / p / "predictions.json").exists() and not (omr_root / "batch" / p).exists():
                        found_all_omr = False
                        break
                
                if found_all_omr:
                    mapping[score] = run_dir.name
                    print(f"  -> Found via page count and OMR existence: {run_dir.name}")
                    break

    print("\nFINAL MAPPING:")
    print(json.dumps(mapping, indent=2))
    
    # Validation summary
    for score, run_id in mapping.items():
        run_path = VERIFY_ROOT / run_id
        pages_in_inv = score_to_pages[score]
        missing = [p for p in pages_in_inv if not (run_path / "baseline" / "batch" / p).exists()]
        if missing:
            print(f"WARNING: {score} ({run_id}) missing baseline pages: {missing}")
        else:
            print(f"OK: {score} ({run_id}) complete.")

if __name__ == "__main__":
    find_mapping()
