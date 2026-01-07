
import json
import os
import re

def main():
    config_path = "tools/gt_relabel_gui/evaluation2_config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)

    pages = config.get("pages", [])
    updated_count = 0

    for page in pages:
        name = page.get("name") # e.g. "Shosrakovich-Sym5-Va/page_002"
        editable = page.get("editable")
        
        # Check if editable path is flattened (e.g. .../Shosrakovich-Sym5-Va_page_002/...)
        # We want nested (e.g. .../Shosrakovich-Sym5-Va/page_002/...)
        # The 'name' field already has the correct structure "Score/Page".
        # We can construct the expected path based on the repo root and name.
        
        # Assuming repo root is /home/masaki_muramatsu/ws_PDFScoreBar_training/
        # And target is data/evaluation2/annotations/{name}/boxes_sorted.json
        
        expected_suffix = f"data/evaluation2/annotations/{name}/boxes_sorted.json"
        
        # We need the full path. Let's take the prefix from the existing string or hardcode repo root.
        # existing: /home/masaki_muramatsu/ws_PDFScoreBar_training/data/evaluation2/annotations/Shosrakovich-Sym5-Va_page_002/boxes_sorted.json
        
        repo_root = "/home/masaki_muramatsu/ws_PDFScoreBar_training"
        expected_full = os.path.join(repo_root, expected_suffix)
        
        if editable != expected_full:
            # specifically targeting the flattened ones or just enforcing consistency
            # valid ones like 'Va_Prokofiev_Symphony1' might have 'boxes_sorted_v20260106.json'
            # We should preserve the filename if it's already special versioned, 
            # but for the missing ones they are just "boxes_sorted.json".
            
            # Let's only fix if it looks like the specific flattened pattern "Score_page_XXX"
            if "_page_" in editable and f"/{name}/" not in editable:
                 print(f"Fixing path for {name}")
                 page["editable"] = expected_full
                 # Also fix output_sorted/raw just in case? 
                 # In file content, output_sorted looked nested correctly.
                 updated_count += 1

    if updated_count > 0:
        print(f"Updated {updated_count} paths. Saving...")
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    else:
        print("No paths needed update.")

if __name__ == "__main__":
    main()
