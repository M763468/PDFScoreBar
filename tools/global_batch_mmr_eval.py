import argparse
import subprocess
import sys
from pathlib import Path

def run_command(cmd, desc):
    print(f"--- {desc} ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error in {desc}:")
        print(result.stderr)
        return False
    return True

def process_page(work_name, page_num, image_path, barline_path, mask_root, output_root, threshold, rescue_threshold, model_path=None):
    page_str = f"page_{page_num:03d}"
    
    # Mask path mapping
    mask_dir = mask_root / f"eval2_{work_name}_{page_str}/baseline/{page_str}/{page_str}"
    staff_mask = mask_dir / f"{page_str}_debug_3_staff.png"
    notehead_mask = mask_dir / f"{page_str}_debug_6_notehead.png"
    
    if not staff_mask.exists():
        # Try alternate path if first one fails
        mask_dir = mask_root / f"eval2_{work_name}_{page_str}/baseline"
        staff_mask = mask_dir / f"{page_str}_debug_3_staff.png"
        notehead_mask = mask_dir / f"{page_str}_debug_6_notehead.png"

    if not staff_mask.exists():
        print(f"Skipping {work_name} {page_str}: Staff mask not found.")
        return False

    if not image_path.exists():
        print(f"Skipping {work_name} {page_str}: Image not found at {image_path}")
        return False

    if not barline_path.exists():
        print(f"Skipping {work_name} {page_str}: Barlines not found at {barline_path}")
        return False
        
    page_out_dir = output_root / work_name / page_str
    page_out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nProcessing {work_name} {page_str}...")
    
    # 0. Resume Check
    final_json = page_out_dir / "numbering_final.json"
    if final_json.exists():
        print(f"Skipping {work_name} {page_str}: Already done.")
        return True

    # 1. Initial Numbering
    initial_json = page_out_dir / "numbering_initial.json"
    cmd_1 = [
        ".venv_omr_dln/bin/python", "tools/add_measure_numbers.py",
        "--barlines", str(barline_path),
        "--staff-mask", str(staff_mask),
        "--image", str(image_path),
        "--output-json", str(initial_json)
    ]
    if not run_command(cmd_1, "Initial Numbering"): return False

    # 2. Generate Overrides (OCR Refined)
    overrides_json = page_out_dir / "overrides.json"
    cmd_2 = [
        ".venv_omr_dln/bin/python", "tools/generate_numbering_overrides.py",
        "--numbering-json", str(initial_json),
        "--image", str(image_path),
        "--output-overrides", str(overrides_json),
        "--threshold", str(threshold),
        "--rescue-threshold", str(rescue_threshold)
    ]
    if model_path:
        cmd_2.extend(["--model-path", str(model_path)])

    if not run_command(cmd_2, "Generate Overrides"): return False

    # 3. Final Numbering
    final_json = page_out_dir / "numbering_final.json"
    cmd_3 = [
        ".venv_omr_dln/bin/python", "tools/add_measure_numbers.py",
        "--barlines", str(barline_path),
        "--staff-mask", str(staff_mask),
        "--image", str(image_path),
        "--config", str(overrides_json),
        "--output-json", str(final_json)
    ]
    if not run_command(cmd_3, "Final Numbering"): return False
    
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("logs/experiments/global_mmr_eval_v1"))
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--rescue-threshold", type=float, default=0.1)
    parser.add_argument("--model-path", type=Path, default=None)
    parser.add_argument("--filter", type=str, default=None, help="Filter works by name (case-insensitive)")
    args = parser.parse_args()
    
    mask_root = Path("logs/hybrid_generalization")
    ann_root = Path("data/evaluation2/annotations")
    img_root = Path("data/evaluation2/images")
    
    # Discovery: iterate through annotation directories
    works = [d.name for d in ann_root.iterdir() if d.is_dir()]
    
    if args.filter:
        print(f"Filtering works by '{args.filter}'...")
        works = [w for w in works if args.filter.lower() in w.lower()]
        
    for work in sorted(works):
        print(f"\n=== Work: {work} ===")
        work_ann_dir = ann_root / work
        
        # Image directory name might differ from annotation directory name
        # Mapping for known discrepancies
        img_work_name = work
        if work == "Va_Prokofiev_Symphony1": img_work_name = "prokofiev1" # Typical mapping
        
        work_img_dir = img_root / img_work_name
        if not work_img_dir.exists():
            # Try original name
            work_img_dir = img_root / work
            
        if not work_img_dir.exists():
            print(f"Skipping {work}: Image directory not found.")
            continue

        # Iterate through pages in annotations
        pages = sorted([d.name for d in work_ann_dir.iterdir() if d.is_dir() and d.name.startswith("page_")])
        
        for page_str in pages:
            page_num = int(page_str.split("_")[1])
            img_path = work_img_dir / f"{page_str}.png"
            
            # Find latest barlines
            page_ann_dir = work_ann_dir / page_str
            # Match both versioned and unversioned sorted boxes
            barlines = sorted(list(page_ann_dir.glob("boxes_sorted*.json")))
            if not barlines:
                print(f"Skipping {work} {page_str}: No barlines found.")
                continue
            gt_barlines = barlines[-1]
            
            process_page(work, page_num, img_path, gt_barlines, mask_root, args.output_dir, args.threshold, args.rescue_threshold, args.model_path)

    # Finally run the evaluation script if we have any results
    print("\n=== GLOBAL EVALUATION ===")
    cmd_eval = [
        ".venv_omr_dln/bin/python", "tools/evaluate_rest_detection.py",
        "--eval-root", "data/evaluation2/rest_gt",
        "--overrides-root", str(args.output_dir)
    ]
    run_command(cmd_eval, "Full Pipeline Evaluation")

if __name__ == "__main__":
    main()
