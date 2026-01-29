import argparse
import subprocess
from pathlib import Path


def run_command(cmd, desc):
    # print(f"CMD: {' '.join(str(x) for x in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error in {desc}:")
        print(result.stderr)
        return False
    return True


def process_page(work_name, page_num, image_path, barline_path, mask_root, output_root):
    page_str = f"page_{page_num:03d}"

    if work_name == "prokofiev1":
        work_key = "prokofiev1"
    else:
        work_key = "prokofiev5"

    mask_dir = mask_root / f"eval2_{work_key}_{page_str}/baseline/{page_str}/{page_str}"
    staff_mask = mask_dir / f"{page_str}_debug_3_staff.png"
    notehead_mask = mask_dir / f"{page_str}_debug_6_notehead.png"

    if not staff_mask.exists() or not notehead_mask.exists():
        # print(f"Skipping {work_name} {page_str}: Masks not found")
        return

    if not image_path.exists() or not barline_path.exists():
        # print(f"Skipping {work_name} {page_str}: Image/GT not found")
        return

    # Setup Output
    page_out_dir = output_root / work_name / page_str
    page_out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing {work_name} {page_str}...")

    # 1. Initial Numbering (Need this to get bboxes)
    # Reuse existing if possible? No, safer to regen to ensure consistency.
    initial_json = page_out_dir / "numbering_base.json"
    cmd_1 = [
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
    if not run_command(cmd_1, "Initial Numbering"):
        return

    # 2. Debug Visualization (Standard Threshold 50)
    out_std = page_out_dir / "debug_ocr_thresh50.png"
    cmd_std = [
        ".venv_omr_dln/bin/python",
        "tools/debug_ocr_candidates.py",
        "--numbering-json",
        str(initial_json),
        "--notehead-mask",
        str(notehead_mask),
        "--image",
        str(image_path),
        "--output-image",
        str(out_std),
        "--threshold",
        "50",
        "--vertical-margin",
        "80",
        "--erode-iter",
        "1",
    ]
    if not run_command(cmd_std, "Debug Vis (Std)"):
        return

    # 3. Debug Visualization (Relaxed Threshold 200)
    out_rel = page_out_dir / "debug_ocr_thresh200.png"
    cmd_rel = [
        ".venv_omr_dln/bin/python",
        "tools/debug_ocr_candidates.py",
        "--numbering-json",
        str(initial_json),
        "--notehead-mask",
        str(notehead_mask),
        "--image",
        str(image_path),
        "--output-image",
        str(out_rel),
        "--threshold",
        "200",
        "--vertical-margin",
        "80",
        "--erode-iter",
        "1",
    ]
    if not run_command(cmd_rel, "Debug Vis (Relaxed)"):
        return

    print(f"Saved debug images to {page_out_dir}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    mask_root = Path("logs/hybrid_generalization")

    # Prokofiev 1 (1-6)
    for i in range(1, 7):
        page_str = f"page_{i:03d}"
        img = Path(f"data/evaluation2/images/prokofiev1/{page_str}.png")
        gt_dir = Path(f"data/evaluation2/annotations/Va_Prokofiev_Symphony1/{page_str}")
        barlines = sorted(list(gt_dir.glob("boxes_sorted_*.json")))
        if barlines:
            process_page("prokofiev1", i, img, barlines[-1], mask_root, args.output_dir)

    # Prokofiev 5 (1-23)
    for i in range(1, 24):
        page_str = f"page_{i:03d}"
        img = Path(f"data/evaluation2/images/prokofiev5/{page_str}.png")
        gt_dir = Path(f"data/evaluation2/annotations/prokofiev5/{page_str}")
        barlines = sorted(list(gt_dir.glob("boxes_sorted_*.json")))
        if barlines:
            process_page("prokofiev5", i, img, barlines[-1], mask_root, args.output_dir)


if __name__ == "__main__":
    main()
