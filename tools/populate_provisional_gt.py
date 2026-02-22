import json
import shutil
from pathlib import Path

# LEGACY: Historical helper for overwriting provisional GT from CNN-filtered
# outputs in `logs/hybrid_generalization`. Not part of the current evaluation2
# GT rebuild flow.


def main():
    print(
        "[LEGACY] populate_provisional_gt.py uses the older hybrid_generalization/CNN workflow. "
        "Use tools/gt_relabel_gui/prepare_rebuild_eval2.py for current evaluation2 GT rebuild."
    )
    config_path = "tools/gt_relabel_gui/evaluation2_config.json"
    with open(config_path, "r") as f:
        config = json.load(f)

    log_root = Path("logs/hybrid_generalization")

    pages = config.get("pages", [])
    copy_count = 0
    skip_count = 0

    # Target prefixes to overwrite
    TARGET_SCORES = [
        "Shosrakovich-Sym5-Va",
        "Shostakovich-Festival_Overture_Va",
        "Sibelius-Violin_Concerto-Viola",
        "prokofiev1",
        # NOT "Va_Prokofiev_Symphony1" (Existing GT)
        # NOT "prokofiev5" (Existing GT)
    ]

    for page in pages:
        name = page.get("name")  # "Score/Page"
        editable_path = Path(page.get("editable"))

        score_name = name.split("/")[0]
        if score_name not in TARGET_SCORES:
            # print(f"Skipping {name} (Not in target scores)")
            continue

        # Construct Source Path
        # name = "Score/Page_XXX" or "Score/page_XXX"
        # run_id usually "eval2_Score_page_XXX"
        # We need to handle the underscores correctly.
        # eval2_{score_name}_{page_part}

        parts = name.split("/")
        if len(parts) == 2:
            run_name = f"eval2_{parts[0]}_{parts[1]}"
        else:
            print(f"Skipping {name}: weird format")
            continue

        source_json = log_root / run_name / "pipeline2_no_peak_filtered_cnn.json"

        if not source_json.exists():
            print(f"  [SOURCE MISSING] {source_json}")
            skip_count += 1
            continue

        # Overwrite
        try:
            editable_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source_json, editable_path)
            print(f"  [UPDATED] {name} <- filtered_cnn")
            copy_count += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            skip_count += 1

    print("-" * 30)
    print(f"Updated: {copy_count}")
    print(f"Skipped/Missing: {skip_count}")


if __name__ == "__main__":
    main()
