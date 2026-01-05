import json
from pathlib import Path
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Generate Config for GT Relabel GUI")
    parser.add_argument("--json-root", required=True, help="Root of provisional GT JSONs")
    parser.add_argument("--image-root", required=True, help="Root of images")
    parser.add_argument("--output-config", required=True, help="Output config path")
    parser.add_argument("--repo-root", default="/home/masaki_muramatsu/ws_PDFScoreBar_training", help="Absolute path to repo root")
    args = parser.parse_args()

    json_root = Path(args.json_root)
    image_root = Path(args.image_root)
    repo_root = Path(args.repo_root)

    pages = []

    # Iterate recursively over json_root
    for json_path in sorted(json_root.rglob("*.json")):
        if json_path.name.endswith("_sorted.json"):
            continue
            
        # Get relative path from json_root
        rel_path = json_path.relative_to(json_root)
        # Structure: subdir/page.json
        
        subdir = rel_path.parent.name
        page_name = rel_path.stem # e.g. "page_001"
        
        # 1. Exclude duplicates
        if subdir == "prokofiev1":
            print(f"Skipping duplicate: {rel_path}")
            continue
            
        # 2. Exclude pages with existing GT
        # Check data/evaluation2/annotations/{subdir}/{page_name}/boxes_sorted_*.json
        # We need to construct the check path.
        # Assuming args.json_root is "data/evaluation2/annotations_provisional"
        # Then annotations root is "data/evaluation2/annotations"
        
        # This is a bit heuristic, assuming folder structure.
        # Let's derive annotations_root from json_root.
        # ../annotations_provisional -> ../annotations
        annotations_root = json_root.parent / "annotations"
        gt_check_dir = annotations_root / subdir / page_name
        
        if gt_check_dir.exists():
            # Check for any file starting with boxes_sorted
            has_gt = any(gt_check_dir.glob("boxes_sorted_*.json"))
            if has_gt:
                 print(f"Skipping existing GT: {subdir}/{page_name}")
                 continue
        
        # Construct image path
        image_rel = rel_path.with_suffix(".png")
        image_path = image_root / image_rel
        
        if not image_path.exists():
            print(f"Warning: Image not found for {json_path}: {image_path}")
            continue
            
        # Construct absolute paths WITHOUT resolving symlinks to target
        # We want the path inside the repo.
        
        # image_path is relative to CWD (e.g. data/evaluation2/images/...)
        # We want absolute path: repo_root / image_path
        abs_image = (repo_root / image_path).absolute()
        abs_json = (repo_root / json_path).absolute()
        
        # Output sorted path
        abs_sorted = abs_json.with_name(abs_json.stem + "_sorted.json")

        page_entry = {
            "name": f"{rel_path.parent.name}/{rel_path.stem}",
            "image": str(abs_image),
            "output_raw": str(abs_json),
            "output_sorted": str(abs_sorted),
            "editable": str(abs_json), # Required by app_gt.js
            "y_threshold": 50
        }
        pages.append(page_entry)

    config = {"pages": pages}
    
    out_path = Path(args.output_config)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w') as f:
        json.dump(config, f, indent=2)
        
    print(f"Generated config with {len(pages)} pages at {out_path}")

if __name__ == "__main__":
    main()
