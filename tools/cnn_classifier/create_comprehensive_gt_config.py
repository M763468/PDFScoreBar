import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-config", default="tools/gt_relabel_gui/evaluation2_config.json")
    parser.add_argument("--image-root", default="data/evaluation2/images")
    parser.add_argument("--annotation-root", default="data/evaluation2/annotations")
    parser.add_argument("--candidate-root", default="logs/hybrid_generalization")
    args = parser.parse_args()

    repo_root = Path(os.getcwd())
    image_root = repo_root / args.image_root
    ann_root = repo_root / args.annotation_root
    cand_root = repo_root / args.candidate_root

    pages = []

    # 1. Add Existing GT (Prokofiev)
    # Recursively find boxes_sorted_v20260106.json or boxes_sorted.json
    gt_files = sorted(ann_root.rglob("boxes_sorted*.json"))

    # Filter to keep only the latest version if multiple exist
    # Map key (subdir, page) -> latest_file
    gt_map = {}
    for f in gt_files:
        subdir = f.parent.parent.name
        page = f.parent.name
        key = f"{subdir}/{page}"
        # Simple heuristic: longer filename usually means newer version (v2026...)
        if key not in gt_map or len(f.name) > len(gt_map[key].name):
            gt_map[key] = f

    for key, gt_path in gt_map.items():
        subdir, page = key.split("/")
        img_path = image_root / subdir / f"{page}.png"

        if not img_path.exists():
            print(f"Warning: Image not found for GT {key}: {img_path}")
            continue

        pages.append(
            {
                "name": key,
                "image": str(img_path),
                "output_raw": str(gt_path.parent / "output_raw.json"),  # Temp output
                "output_sorted": str(gt_path),  # Overwrite source? Or separate?
                # For fixing double bars, we probably want to edit the GT directly or a copy.
                # Let's define editable as the GT file.
                "editable": str(gt_path),
                "y_threshold": 50,
            }
        )

    # 2. Add Candidates (Shostakovich / Sibelius)
    # Look for subdirs in cand_root like eval2_<Subdir>_<Page>
    # We want to exclude Prokofiev since we have GT.

    cand_dirs = sorted(cand_root.glob("eval2_*"))
    for d in cand_dirs:
        # Parse dirname: eval2_ScoreName_page_XXX
        parts = d.name.replace("eval2_", "").split("_page_")
        if len(parts) != 2:
            continue
        score_name = parts[0]
        page_num = f"page_{parts[1]}"

        key = f"{score_name}/{page_num}"

        # Skip if we already have GT for this page
        if key in gt_map:
            continue

        img_path = image_root / score_name / f"{page_num}.png"
        cand_path = d / "pipeline1_baseline_filtered.json"

        if not img_path.exists():
            # Try finding image if name mismatch?
            # Usually score_name matches subdir in images
            pass

        if img_path.exists() and cand_path.exists():
            # We need a place to save the NEW GT.
            # Ideally data/evaluation2/annotations/<Score>/<Page>/boxes_sorted.json
            save_dir = ann_root / score_name / page_num
            save_dir.mkdir(parents=True, exist_ok=True)
            output_path = save_dir / "boxes_sorted.json"

            # If output already exists (partial work), use it as source?
            source_path = output_path if output_path.exists() else cand_path

            pages.append(
                {
                    "name": key,
                    "image": str(img_path),
                    "output_raw": str(save_dir / "raw_boxes.json"),
                    "output_sorted": str(output_path),
                    "editable": str(source_path),
                    "y_threshold": 50,
                }
            )

    # Sort pages by name
    pages.sort(key=lambda x: x["name"])

    config = {"pages": pages}

    out_path = repo_root / args.output_config
    with out_path.open("w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated config with {len(pages)} pages at {out_path}")


if __name__ == "__main__":
    main()
