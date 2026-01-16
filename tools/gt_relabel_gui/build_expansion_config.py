
import os
import json
import subprocess
import shutil
from pathlib import Path

# Paths
TRAINING_WS = Path("/home/masaki_muramatsu/ws_PDFScoreBar_training")
CURRENT_WS = Path("/home/masaki_muramatsu/ws_PDFScoreBar_model_exp")
OUTPUT_CONFIG = CURRENT_WS / "data/evaluation2/rest_gt_config_expansion.json"
CACHE_DIR = CURRENT_WS / "logs/cache_expansion_gen"
LOCAL_IMG_DIR = CURRENT_WS / "data/evaluation2/images/expansion"

# Dataset Definitions
EXPANSION_PAGES = [
    {
        "name": "expansion_eval_page_003",
        "image": TRAINING_WS / "data/evaluation/images/page_3.png",
        "barlines": TRAINING_WS / "data/evaluation/annotations/page_003/boxes_sorted_v20260111.json",
        "mask": TRAINING_WS / "logs/hybrid_generalization/sr_eval_smoke_page3/baseline/page_3/page_3/page_3_debug_3_staff.png",
        "rest_gt_dir": CURRENT_WS / "data/evaluation2/rest_gt/expansion/page_003"
    },
    {
        "name": "expansion_train_page_010",
        "image": TRAINING_WS / "data/training/images/page_10.png",
        "barlines": TRAINING_WS / "data/training/annotations/page_010/boxes_sorted_v20260111.json",
        "mask": TRAINING_WS / "logs/hybrid_generalization/sr_eval_page10_check2/baseline/page_10/page_10/page_10_debug_3_staff.png",
        "rest_gt_dir": CURRENT_WS / "data/evaluation2/rest_gt/expansion/page_010"
    },
    {
        "name": "expansion_train_page_015",
        "image": TRAINING_WS / "data/training/images/page_15.png",
        "barlines": TRAINING_WS / "data/training/annotations/page_015/boxes_sorted_v20251229.json",
        "mask": TRAINING_WS / "logs/hybrid_generalization/sr_eval_page15_check2/baseline/page_15/page_15/page_15_debug_3_staff.png",
        "rest_gt_dir": CURRENT_WS / "data/evaluation2/rest_gt/expansion/page_015"
    }
]

def main():
    config_entries = []
    
    # Ensure local image dir exists
    LOCAL_IMG_DIR.mkdir(parents=True, exist_ok=True)
    
    for page in EXPANSION_PAGES:
        print(f"Processing {page['name']}...")
        
        # 0. Validate inputs
        if not page['image'].exists():
            print(f"  ERROR: Image not found: {page['image']}")
            continue
        if not page['barlines'].exists():
            print(f"  ERROR: Barlines not found: {page['barlines']}")
            continue
        if not page['mask'].exists():
            print(f"  ERROR: Mask not found: {page['mask']}")
            continue

        # 1. Prepare Output Dirs & Copy Image
        page_cache_dir = CACHE_DIR / page['name']
        page_cache_dir.mkdir(parents=True, exist_ok=True)
        
        page['rest_gt_dir'].mkdir(parents=True, exist_ok=True)
        rest_gt_file = page['rest_gt_dir'] / "rest_gt.json"
        
        # Copy image to local workspace to avoid 403 errors
        local_img_path = LOCAL_IMG_DIR / page['image'].name
        shutil.copy2(page['image'], local_img_path)
        print(f"  Copied image to {local_img_path}")
        
        # 2. Generate Numbering
        numbering_file = page_cache_dir / "numbering_initial.json"
        
        cmd = [
            ".venv_omr_dln/bin/python",
            "tools/add_measure_numbers.py",
            "--barlines", str(page['barlines']),
            "--staff-mask", str(page['mask']),
            "--image", str(local_img_path), # Use local image
            "--output-json", str(numbering_file),
            "--output-overlay", str(page_cache_dir / "debug_overlay.png"),
            "--force-single-system"
        ]
        
        print(f"  Running generation...")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(CURRENT_WS))
        
        if result.returncode != 0:
            print(f"  Generation FAILED: {result.stderr}")
            continue
        else:
            print(f"  Generation Success: {numbering_file}")
            
        # 3. Create Config Entry (Use relative paths for portability/server access)
        entry = {
            "name": page['name'],
            "image": str(local_img_path.relative_to(CURRENT_WS)),
            "numbering": str(numbering_file.relative_to(CURRENT_WS)),
            "rest_gt": str(rest_gt_file.relative_to(CURRENT_WS)),
            "output": str(rest_gt_file.relative_to(CURRENT_WS))
        }
        config_entries.append(entry)

    # 4. Write Config
    print(f"Writing config for {len(config_entries)} pages to {OUTPUT_CONFIG}")
    with open(OUTPUT_CONFIG, 'w') as f:
        json.dump({"pages": config_entries}, f, indent=2)

if __name__ == "__main__":
    main()
