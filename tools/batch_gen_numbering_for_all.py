import argparse
import subprocess
from pathlib import Path


def run_command(cmd, desc):
    # print(f"--- {desc} ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error in {desc}:")
        print(result.stderr)
        return False
    return True


def ensure_numbering_json(work_name, page_str, image_path, barline_path, mask_root, output_dir):
    """
    Gen numbering_initial.json.
    """
    initial_json = output_dir / "numbering_initial.json"
    if initial_json.exists():
        return initial_json

    # Construct mask paths
    # logs/hybrid_generalization/eval2_{work}_{page}/baseline/{page}/{page}/{page}_debug_...
    # NOTE: mask_root structure is brittle.
    # Pattern: eval2_{work}_{page}/baseline/{page}/{page}/{page}_debug_3_staff.png
    mask_dir = mask_root / f"eval2_{work_name}_{page_str}/baseline/{page_str}/{page_str}"
    staff_mask = mask_dir / f"{page_str}_debug_3_staff.png"

    if not staff_mask.exists():
        # Fallback for weird naming?
        # Sometimes work name in eval2_ is different?
        print(f"  [Skip] Masks not found: {mask_dir}")
        print(f"         Expected: {staff_mask}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        ".venv_omr_dln/bin/python",
        "tools/add_measure_numbers.py",
        "--barlines",
        str(barline_path),
        "--staff-mask",
        str(staff_mask),
        "--image",
        str(image_path),
        "--output-json",
        str(initial_json),
    ]

    if run_command(cmd, f"Gen Numbering {work_name}/{page_str}"):
        pass
        # print(f"Generated {initial_json}")
    else:
        print(f"Failed {work_name}/{page_str}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument(
        "--annotations-root", type=Path, default=Path("data/evaluation2/annotations")
    )
    parser.add_argument("--mask-root", type=Path, default=Path("logs/hybrid_generalization"))
    parser.add_argument("--output-root", type=Path, default=Path("logs/cache_dataset_gen"))
    args = parser.parse_args()

    work_dirs = sorted([d for d in args.images_root.iterdir() if d.is_dir()])

    for work_dir in work_dirs:
        work = work_dir.name
        if work.startswith("."):
            continue

        print(f"Scanning {work}...")
        for image_path in sorted(work_dir.glob("*.png")):
            page_str = image_path.stem

            gt_dir = args.annotations_root / work / page_str
            # Try timestamped first
            barlines = sorted(list(gt_dir.glob("boxes_sorted_*.json")))
            if not barlines:
                # Try plain
                barlines = sorted(list(gt_dir.glob("boxes_sorted.json")))

            if not barlines:
                print(f"  [Skip] No barlines for {work}/{page_str}")
                continue
            barline_path = barlines[-1]

            out_dir = args.output_root / work / page_str
            ensure_numbering_json(work, page_str, image_path, barline_path, args.mask_root, out_dir)


if __name__ == "__main__":
    main()
