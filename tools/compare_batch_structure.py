import json
from pathlib import Path


def compare_batches(old_root, new_root, config_paths):
    all_results = []

    for config_path in config_paths:
        if not Path(config_path).exists():
            continue
        config = json.load(open(config_path))
        pages = config.get("pages", config)

        for entry in pages:
            name = entry["name"]
            old_rel = entry.get("numbering")
            if not old_rel:
                continue

            parts = Path(old_rel).parts
            if len(parts) < 3:
                continue

            # Find the index of the work name (usually after batch dir)
            # logs/experiments/batch_verification_20260107_v5/work_name/page_name/...
            found_log = False
            for i, p in enumerate(parts):
                if p == "experiments":
                    found_log = True
                    core_parts = parts[i + 2 :]  # after batch_name
                    break

            if not found_log:
                continue

            old_path = old_root / "/".join(core_parts)
            new_path = new_root / "/".join(core_parts)

            # Check numbering_initial.json if numbering_final.json is missing
            if not new_path.exists():
                new_path = new_root / "/".join(core_parts[:-1]) / "numbering_initial.json"

            if old_path.exists() and new_path.exists():
                old_data = json.load(open(old_path))
                new_data = json.load(open(new_path))

                def count_m(data):
                    count = 0
                    p_data = data.get("pages", [data])[0]  # handle different formats
                    for s in p_data.get("systems", []):
                        count += len(s.get("measures", []))
                    return count

                c_old = count_m(old_data)
                c_new = count_m(new_data)

                if c_old != c_new:
                    all_results.append(
                        {"Name": name, "Old": c_old, "New": c_new, "Diff": c_new - c_old}
                    )

    if all_results:
        print("| Dataset | Page | Old Count | New Count | Diff |")
        print("| --- | --- | --- | --- | --- |")
        for r in all_results:
            print(
                f"| {r['Name'].split('_')[0]} | {r['Name']} | {r['Old']} | {r['New']} | {r['Diff']:+} |"
            )
    else:
        print("No systemic structural differences found in the checked pages.")


if __name__ == "__main__":
    compare_batches(
        Path("logs/experiments/batch_verification_20260107_v5"),
        Path("logs/experiments/batch_cnnv1"),
        [
            "data/evaluation2/rest_gt_config_prokofiev.json",
            "data/evaluation2/rest_gt_config_expansion.json",
            "data/evaluation2/rest_gt_config_all.json",
        ],
    )
