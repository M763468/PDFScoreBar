#!/usr/bin/env python3
"""
Build config JSON for multi-measure rest GT GUI (prokofiev1 + prokofiev5).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def find_numbering_file(root: Path, work: str, page_str: str) -> Path | None:
    # Original search
    base_dir = root / work / page_str
    for name in (
        "numbering_final.json",
        "numbering_base.json",
        "numbering.json",
        "numbering_initial.json",
    ):
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
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/manifest.json"),
    )
    args = parser.parse_args()

    pages = []
    skipped = []

    # Try manifest mapping first if manifest exists
    if args.manifest.exists():
        print(f"Loading manifest mapping from {args.manifest}")
        try:
            with open(args.manifest, "r") as f:
                manifest_data = json.load(f)
            
            # Map page_id to work and page_str
            for p in manifest_data.get("pages", []):
                page_id = p.get("page_id")
                img_path_str = p.get("image_path", "")
                if not page_id or not img_path_str:
                    continue
                
                # Extract work name and page stem
                # e.g., logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Sibelius-Violin_Concerto-Viola_page_001.png
                img_path = Path(img_path_str)
                img_name = img_path.name
                
                # Split work and page from Sibelius-Violin_Concerto-Viola_page_001.png
                # Or Va__Prokofiev_Symphony5_page_001.png
                # Try to extract the page token (e.g. page_001)
                match = re.search(r"(_page_\d+)\.png", img_name)
                if not match:
                    # Alternates
                    match = re.search(r"(page_\d+)", img_name)
                
                if match:
                    page_token = match.group(1).lstrip("_")
                    work_name = img_name.replace(f"_{page_token}.png", "").replace(f"{page_token}.png", "").rstrip("_")
                else:
                    page_token = page_id
                    work_name = "unknown"
                
                # Check for numbering in intermediate/page_xxx/numbering_base.json
                numbering_path = args.numbering_root / page_id / "numbering_base.json"
                if not numbering_path.exists():
                    # Fallback to direct search
                    numbering_path = find_numbering_file(args.numbering_root, work_name, page_token)
                
                # Try to resolve actual image source path from data/evaluation2/images
                resolved_img_path = args.images_root / work_name / f"{page_token}.png"
                if not resolved_img_path.exists():
                    # Try alternate path structures
                    resolved_img_path = Path(img_path_str)
                
                if numbering_path and numbering_path.exists():
                    output_path = args.rest_gt_root / work_name / page_token / "rest_gt.json"
                    pages.append(
                        {
                            "name": f"{work_name}_{page_token}",
                            "image": str(resolved_img_path),
                            "numbering": str(numbering_path),
                            "rest_gt": str(output_path),
                            "output": str(output_path),
                        }
                    )
                else:
                    skipped.append(f"{work_name}/{page_token}")
        except Exception as e:
            print(f"Error reading manifest: {e}")
            # Fall back to legacy scan logic below
            pages = []
            skipped = []

    # Fall back to legacy scanning if manifest mapping failed or was skipped
    if not pages:
        # Scan all subdirectories in images-root
        work_dirs = sorted([d for d in args.images_root.iterdir() if d.is_dir()])

        for work_dir in work_dirs:
            work = work_dir.name
            # Skip hidden folders
            if work.startswith("."):
                continue

            for image_path in sorted(work_dir.glob("*.png")):
                page_str = image_path.stem

                numbering_path = find_numbering_file(args.numbering_root, work, page_str)
                if not numbering_path:
                    numbering_path = find_numbering_file(
                        Path("logs/experiments/mmr_dataset_test_v2"), work, page_str
                    )
                if not numbering_path:
                    numbering_path = find_numbering_file(
                        Path("logs/experiments/mmr_dataset_test"), work, page_str
                    )
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
    import re
    main()
