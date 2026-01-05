import shutil
from pathlib import Path
import argparse
import datetime

def main():
    parser = argparse.ArgumentParser(description="Finalize GT from Provisional Sorted JSONs")
    parser.add_argument("--src-root", default="data/evaluation2/annotations_provisional", help="Source directory")
    parser.add_argument("--dst-root", default="data/evaluation2/annotations", help="Destination directory")
    parser.add_argument("--date-suffix", default=None, help="Date suffix for filename (e.g., 20260106)")
    args = parser.parse_args()

    src_root = Path(args.src_root)
    dst_root = Path(args.dst_root)

    if args.date_suffix:
        suffix = args.date_suffix
    else:
        suffix = datetime.datetime.now().strftime("%Y%m%d")

    print(f"Finalizing GT from {src_root} to {dst_root} with suffix v{suffix}")

    count = 0
    # Recursive search for *_sorted.json
    for src_path in sorted(src_root.rglob("*_sorted.json")):
        # Path structure: src_root / subdir / page_name_sorted.json
        rel_path = src_path.relative_to(src_root)
        subdir = rel_path.parent.name
        
        # Filename is like "page_001_sorted.json" -> page_name "page_001"
        fname = src_path.name
        if not fname.endswith("_sorted.json"):
            continue
        page_name = fname.replace("_sorted.json", "")
        
        # Destination: dst_root / subdir / page_name / boxes_sorted_vYYYYMMDD.json
        dest_dir = dst_root / subdir / page_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        dest_path = dest_dir / f"boxes_sorted_v{suffix}.json"
        
        shutil.copy2(src_path, dest_path)
        print(f"Copied {src_path} -> {dest_path}")
        count += 1

    print(f"Successfully finalized {count} GT files.")

if __name__ == "__main__":
    main()
