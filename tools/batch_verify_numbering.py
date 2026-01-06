import argparse
import subprocess
import sys
from pathlib import Path

def run_command(cmd, desc):
    print(f"--- {desc} ---")
    # print(f"CMD: {' '.join(str(x) for x in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error in {desc}:")
        print(result.stderr)
        return False
    return True

def process_page(work_name, page_num, image_path, barline_path, mask_root, output_root):
    page_str = f"page_{page_num:03d}"
    
    # Construct paths
    # Mask path logic based on exploration
    # logs/hybrid_generalization/eval2_{work_key}_{page_str}/baseline/{page_str}/{page_str}/{page_str}_debug_...
    
    if work_name == "prokofiev1":
        work_key = "prokofiev1" 
    else:
        work_key = "prokofiev5"
        
    mask_dir = mask_root / f"eval2_{work_key}_{page_str}/baseline/{page_str}/{page_str}"
    staff_mask = mask_dir / f"{page_str}_debug_3_staff.png"
    notehead_mask = mask_dir / f"{page_str}_debug_6_notehead.png"
    
    if not staff_mask.exists() or not notehead_mask.exists():
        print(f"Skipping {work_name} {page_str}: Masks not found at {mask_dir}")
        return

    if not image_path.exists():
        print(f"Skipping {work_name} {page_str}: Image not found at {image_path}")
        return

    if not barline_path.exists():
        print(f"Skipping {work_name} {page_str}: Barlines not found at {barline_path}")
        return
        
    # Setup Output
    page_out_dir = output_root / work_name / page_str
    page_out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nProcessing {work_name} {page_str}...")
    
    # 1. Initial Numbering
    initial_json = page_out_dir / "numbering_initial.json"
    cmd_1 = [
        ".venv_omr_dln/bin/python", "tools/add_measure_numbers.py",
        "--barlines", str(barline_path),
        "--staff-mask", str(staff_mask),
        "--image", str(image_path),
        "--output-json", str(initial_json)
    ]
    if not run_command(cmd_1, "Initial Numbering"): return

    # 2. Generate Overrides (OCR)
    overrides_json = page_out_dir / "overrides.json"
    cmd_2 = [
        ".venv_omr_dln/bin/python", "tools/generate_numbering_overrides.py",
        "--numbering-json", str(initial_json),
        "--notehead-mask", str(notehead_mask),
        "--image", str(image_path),
        "--output-overrides", str(overrides_json),
        "--vertical-margin", "80",
        "--erode-iter", "1"
    ]
    if not run_command(cmd_2, "Generate Overrides"): return

    # 3. Final Numbering & Overlay
    final_json = page_out_dir / "numbering_final.json"
    final_overlay = page_out_dir / "overlay.png"
    cmd_3 = [
        ".venv_omr_dln/bin/python", "tools/add_measure_numbers.py",
        "--barlines", str(barline_path),
        "--staff-mask", str(staff_mask),
        "--image", str(image_path),
        "--config", str(overrides_json),
        "--output-json", str(final_json),
        "--output-overlay", str(final_overlay)
    ]
    if not run_command(cmd_3, "Final Numbering"): return
    
    print(f"Success! Overlay saved to: {final_overlay}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    
    mask_root = Path("logs/hybrid_generalization")
    
    # Prokofiev 1
    # Pages 1-6
    for i in range(1, 7):
        page_str = f"page_{i:03d}"
        img = Path(f"data/evaluation2/images/prokofiev1/{page_str}.png")
        gt_dir = Path(f"data/evaluation2/annotations/Va_Prokofiev_Symphony1/{page_str}")
        
        # Find barline json
        barlines = sorted(list(gt_dir.glob("boxes_sorted_*.json")))
        if not barlines:
            print(f"Skipping prokofiev1 {page_str}: No sorted boxes found in {gt_dir}")
            continue
        # Pick the latest one (lexicographically last usually implies latest date)
        gt = barlines[-1]
        
        process_page("prokofiev1", i, img, gt, mask_root, args.output_dir)

    # Prokofiev 5
    # Pages 1-23
    for i in range(1, 24):
        page_str = f"page_{i:03d}"
        img = Path(f"data/evaluation2/images/prokofiev5/{page_str}.png")
        gt_dir = Path(f"data/evaluation2/annotations/prokofiev5/{page_str}")
        
        barlines = sorted(list(gt_dir.glob("boxes_sorted_*.json")))
        if not barlines:
            print(f"Skipping prokofiev5 {page_str}: No sorted boxes found in {gt_dir}")
            continue
        gt = barlines[-1]
        
        process_page("prokofiev5", i, img, gt, mask_root, args.output_dir)

if __name__ == "__main__":
    main()
