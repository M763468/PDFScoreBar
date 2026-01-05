import json
import os
import re
from pathlib import Path
import argparse

def main():
    parser = argparse.ArgumentParser(description="Generate Provisional GT from Scored Candidates")
    parser.add_argument("--scored-root", required=True, help="Directory containing *_scored.json files")
    parser.add_argument("--output-root", required=True, help="Directory to save provisional GT")
    parser.add_argument("--threshold", type=float, default=0.5, help="Score threshold to accept as Barline")
    args = parser.parse_args()

    scored_root = Path(args.scored_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    # Regex to parse filename: eval2_{subdir}_page_{num}_scored.json
    # Note: subdir might contain underscores, so we need to be careful.
    # The convention in inference_visualize.py was:
    # parts = run_id.split('_')
    # page_idx = parts.index("page")
    # subdir = "_".join(parts[1:page_idx])
    # page_name = "_".join(parts[page_idx:])
    
    files = list(scored_root.glob("*_scored.json"))
    print(f"Found {len(files)} scored files.")

    count = 0
    for fpath in files:
        filename = fpath.name
        # Remove suffix
        run_id = filename.replace("_scored.json", "")
        
        parts = run_id.split('_')
        if "page" not in parts:
            print(f"Skipping {filename}: 'page' not found in name")
            continue
            
        try:
            page_idx = parts.index("page")
        except ValueError:
            continue

        if parts[0] != "eval2":
            print(f"Skipping {filename}: Does not start with eval2")
            continue

        subdir = "_".join(parts[1:page_idx])
        # page_name usually includes "page_xxx"
        # parts[page_idx:] gives ['page', '001'] etc.
        page_name = "_".join(parts[page_idx:])
        
        # Read scored candidates
        with open(fpath, 'r') as f:
            candidates = json.load(f)

        # Filter
        accepted_boxes = []
        for c in candidates:
            if c["score"] > args.threshold:
                # Ensure integer coordinates
                box = [int(v) for v in c["bbox"]]
                accepted_boxes.append(box)

        # Save
        out_dir = output_root / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as plain JSON list of boxes
        out_path = out_dir / f"{page_name}.json"
        
        # Also support the format expected by some tools: {"predictions": [{"orig_bbox": ...}]}
        # But simple list is usually fine. Let's stick to simple list for now, 
        # as load_boxes supports it.
        
        with open(out_path, 'w') as f:
            json.dump(accepted_boxes, f, indent=2)
            
        count += 1
        print(f"Saved {len(accepted_boxes)} boxes to {out_path}")

    print(f"Processed {count} files.")

if __name__ == "__main__":
    main()
