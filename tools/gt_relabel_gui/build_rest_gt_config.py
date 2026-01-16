#!/usr/bin/env python3
"""
Build config JSON for multi-measure rest GT GUI (prokofiev1 + prokofiev5).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def find_numbering_file(root: Path, work: str, page_str: str) -> Path | None:
    base_dir = root / work / page_str
    for name in ("numbering_final.json", "numbering_base.json", "numbering.json", "numbering_initial.json"):
        path = base_dir / name
        if path.exists():
            return path
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--images-root",
        type=Path,
        default=Path("data/evaluation2/images"),
    )
    parser.add_argument(
        "--numbering-root",
        type=Path,
        default=Path("logs/experiments/batch_verification_20260107_v5"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/evaluation2/rest_gt_config_prokofiev.json"),
    )
    parser.add_argument(
        "--rest-gt-root",
        type=Path,
        default=Path("data/evaluation2/rest_gt"),
    )
    args = parser.parse_args()

    pages = []
    skipped = []
    # Scan all subdirectories in images-root
    work_dirs = sorted([d for d in args.images_root.iterdir() if d.is_dir()])
    
    for work_dir in work_dirs:
        work = work_dir.name
        # Skip hidden folders
        if work.startswith("."): continue
        
        for image_path in sorted(work_dir.glob("*.png")):
            page_str = image_path.stem
            
            # Look for numbering in sequential preference:
            # 1. args.numbering_root (Batch inference output)
            # 2. logs/cache_dataset_gen (Dataset generation cache)
            # 3. logs/hybrid_generalization (Maybe?) - No, usually doesn't have numbering.json
            
            numbering_path = find_numbering_file(args.numbering_root, work, page_str)
            if not numbering_path:
                 numbering_path = find_numbering_file(Path("logs/experiments/mmr_dataset_test_v2"), work, page_str)
            if not numbering_path:
                 numbering_path = find_numbering_file(Path("logs/experiments/mmr_dataset_test"), work, page_str)
            if not numbering_path:
                 numbering_path = find_numbering_file(Path("logs/cache_dataset_gen"), work, page_str)

            if numbering_path is None:
                skipped.append(f"{work}/{page_str}")
                continue
                
            output_path = args.rest_gt_root / work / page_str / "rest_gt.json"
            pages.append(
                {
                    "name": f"{work}_{page_str}",
                    "image": str(image_path),
                    "numbering": str(numbering_path),
                    "rest_gt": str(output_path),
                    "output": str(output_path),
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"pages": pages}, indent=2))
    print(f"Wrote {len(pages)} pages to {args.output}")
    if skipped:
        print("Skipped (missing numbering):")
        for item in skipped:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
