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
            entry["name"]
            old_rel = entry.get("numbering")
            if not old_rel:
                continue

            # Extract parts after potential project root
            # e.g. Shosrakovich-Sym5-Va / page_002 / numbering_initial.json
            parts = Path(old_rel).parts

            # Strategy: find the work name part by looking for 'page_XXX'
            work_name = None
            page_name = None
            for i, p in enumerate(parts):
                if p.startswith("page_"):
                    work_name = parts[i - 1]
                    page_name = p
                    core_subpath = Path(*parts[i - 1 :])
                    break

            if not core_subpath:
                continue

            # Paths in new/old roots
            # New root is batch_cnnv1
            # Old can be cache_dataset_gen or batch_verification...
            # We search for the file in both roots

            def find_file(root, subpath):
                # Try relative as given if it exists
                p = root / subpath
                if p.exists():
                    return p
                # Try numbering_initial if numbering_final missing
                if p.name == "numbering_final.json":
                    p2 = p.parent / "numbering_initial.json"
                    if p2.exists():
                        return p2
                # If there's an experiment dir in the middle, search more broadly
                for candidate in root.rglob(f"{work_name}/{page_name}/*.json"):
                    if candidate.name in ["numbering_initial.json", "numbering_final.json"]:
                        return candidate
                return None

            old_path = (
                Path(old_rel).resolve()
                if Path(old_rel).is_absolute()
                else (REPO_ROOT / old_rel).resolve()
            )
            # If it's a relative path starting with 'logs', resolve relative to project root
            if not old_path.exists():
                old_path = Path("/home/masaki_muramatsu/ws_PDFScoreBar_model_exp") / old_rel

            new_path = find_file(new_root, core_subpath)

            if old_path.exists() and new_path:
                try:
                    old_data = json.load(open(old_path))
                    new_data = json.load(open(new_path))

                    def count_m(data):
                        count = 0
                        p_data = data.get("pages", [data])[0]
                        for s in p_data.get("systems", []):
                            count += len(s.get("measures", []))
                        return count

                    c_old = count_m(old_data)
                    c_new = count_m(new_data)

                    if c_old != c_new:
                        all_results.append(
                            {
                                "Work": work_name,
                                "Page": page_name,
                                "Old": c_old,
                                "New": c_new,
                                "Diff": c_new - c_old,
                            }
                        )
                except Exception:
                    pass

    if all_results:
        print("| Work | Page | Old Count | New Count | Diff |")
        print("| --- | --- | --- | --- | --- |")
        for r in sorted(all_results, key=lambda x: (x["Work"], x["Page"])):
            print(f"| {r['Work']} | {r['Page']} | {r['Old']} | {r['New']} | {r['Diff']:+} |")
    else:
        print("No systemic structural differences found in the checked pages.")


if __name__ == "__main__":
    REPO_ROOT = Path("/home/masaki_muramatsu/ws_PDFScoreBar_model_exp")
    compare_batches(
        REPO_ROOT,  # Absolute paths in config will be used mostly
        REPO_ROOT / "logs/experiments/batch_cnnv1",
        ["data/evaluation2/rest_gt_config_all.json"],
    )
