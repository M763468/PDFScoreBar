import json
from pathlib import Path


def main():
    root = Path("logs/repro_v12_recovery/probe_candidates_filtered_v12")
    out_root = Path("logs/repro_v12_recovery/seeds_v12_clean")

    if not root.exists():
        print(f"Error: {root} not found.")
        return

    out_root.mkdir(parents=True, exist_ok=True)

    # Identify score names from subdirectories of root (skip seeds_v12_clean itself)
    scores = [
        d.name
        for d in root.iterdir()
        if d.is_dir() and d.name != "seeds_v12_clean" and d.name != "verify_final"
    ]

    count = 0
    for score in scores:
        score_dir = root / score
        # Search for candidates in subfolders
        candidates = list(score_dir.glob("**/pipeline2_no_peak_candidates.json"))
        if not candidates:
            candidates = list(score_dir.glob("**/predictions.json"))

        for cand_file in candidates:
            # The parent of the candidate file is the evaluate subfolder.
            # Its parent is the page subfolder.
            # e.g., Shostakovich... / page_001 / eval2... / pipeline...json
            # Let's find the page folder name.
            parts = cand_file.parts
            page_name = None
            for i in range(len(parts) - 1, 0, -1):
                if parts[i].startswith("page_"):
                    page_name = parts[i]
                    break

            if not page_name:
                # Alternative: try finding it in the stem of the evaluate folder
                for part in parts:
                    if "page_" in part:
                        page_name = "page_" + part.split("page_")[-1].split(".")[0][:3]
                        break

            if not page_name:
                continue

            target_dir = out_root / score / page_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "pipeline2_no_peak_candidates.json"

            # Load and Clean
            with open(cand_file, "r") as f:
                data = json.load(f)

            # Format as clean [ {bbox: ...}, ... ]
            clean_data = []
            for item in data:
                if "bbox" in item:
                    clean_data.append({"bbox": item["bbox"]})
                elif isinstance(item, list):
                    clean_data.append({"bbox": item[:4]})

            with open(target_file, "w") as f:
                json.dump(clean_data, f, indent=4)

            count += 1

    print(f"REORGANIZATION COMPLETE. Saved {count} clean predictions.json to {out_root}")


if __name__ == "__main__":
    main()
