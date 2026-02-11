import json
import shutil
from pathlib import Path


def prepare_eval2_rebuild():
    repo_root = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
    img_root = repo_root / "data/evaluation2/images"
    ann_root = repo_root / "data/evaluation2/annotations"
    logs_root = repo_root / "logs/hybrid_pipeline_bench"

    # 1. Map pages to their latest hybrid predictions
    # Pattern: eval2_{score}_{page}_{timestamp}
    page_to_latest_log = {}

    for log_dir in logs_root.glob("eval2_*"):
        if not log_dir.is_dir():
            continue

        # Split by '_' and try to extract score and page
        # Example: eval2_Shostakovich-Festival_Overture_Va_page_001_20260131_025459
        parts = log_dir.name.split("_")
        # Find index of "page"
        try:
            page_idx = parts.index("page")
            score = "_".join(parts[1:page_idx])
            page = "_".join(parts[page_idx : page_idx + 2])
            key = (score, page)

            timestamp = "_".join(parts[page_idx + 2 :])

            if key not in page_to_latest_log or timestamp > page_to_latest_log[key][1]:
                page_to_latest_log[key] = (log_dir, timestamp)
        except ValueError:
            continue

    print(f"Found {len(page_to_latest_log)} unique pages in logs.")

    config_pages = []

    # 2. Iterate over image directories
    for score_dir in img_root.iterdir():
        if not score_dir.is_dir():
            continue

        score_name = score_dir.name
        for img_path in sorted(score_dir.glob("*.png")):
            page_name = img_path.stem
            key = (score_name, page_name)

            dest_dir = ann_root / score_name / page_name
            dest_dir.mkdir(parents=True, exist_ok=True)

            editable_path = dest_dir / "boxes_provisional.json"
            output_sorted = dest_dir / "boxes_sorted.json"

            # Copy hybrid predictions if available
            if key in page_to_latest_log:
                src_log = page_to_latest_log[key][0]
                src_json = src_log / "hybrid_predictions.json"
                if src_json.exists():
                    shutil.copy2(src_json, editable_path)
                else:
                    # Try to find any other useful json?
                    pass

            if not editable_path.exists():
                # Create empty if not found
                with open(editable_path, "w") as f:
                    json.dump([], f)

            config_pages.append(
                {
                    "name": f"{score_name}/{page_name}",
                    "image": str(img_path.absolute()),
                    "editable": str(editable_path.absolute()),
                    "output_sorted": str(output_sorted.absolute()),
                    "y_threshold": 50,
                }
            )

    # 3. Write new config
    new_config = {"pages": config_pages}
    config_out = repo_root / "tools/gt_relabel_gui/evaluation2_config.json"
    with open(config_out, "w") as f:
        json.dump(new_config, f, indent=2)

    print(f"Prepared {len(config_pages)} pages. Config written to {config_out}")


if __name__ == "__main__":
    prepare_eval2_rebuild()
