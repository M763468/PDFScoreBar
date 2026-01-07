
import json
import os
import shutil
from pathlib import Path

def main():
    config_path = "tools/gt_relabel_gui/evaluation2_config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)

    log_root = Path("logs/hybrid_generalization")
    
    pages = config.get("pages", [])
    copy_count = 0
    fail_count = 0

    for page in pages:
        name = page.get("name") # "Score/Page"
        editable_path = Path(page.get("editable"))
        
        # Check if needs population
        if editable_path.exists() and editable_path.stat().st_size > 0:
            continue
            
        print(f"Populating {name}...")
        
        # Construct Source Path
        # name = "Score/Page_XXX" -> run_id = "eval2_Score_Page_XXX"
        score, page_sub = name.split('/')
        run_name = f"eval2_{score}_{page_sub}"
        
        source_json = log_root / run_name / "pipeline2_no_peak_candidates.json"
        
        if not source_json.exists():
            print(f"  [SOURCE MISSING] {source_json}")
            fail_count += 1
            # Try alternative? maybe underscores/hyphens differ?
            # Let's try flexible matching if needed, but for now exact match.
            continue
            
        # Copy
        try:
            editable_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source_json, editable_path)
            print(f"  [COPIED] -> {editable_path}")
            copy_count += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            fail_count += 1

    print("-" * 30)
    print(f"Populated: {copy_count}")
    print(f"Failed: {fail_count}")

if __name__ == "__main__":
    main()
