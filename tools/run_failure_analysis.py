import subprocess
import argparse
from pathlib import Path

def run_debug(work, page, measure, output_dir):
    print(f"\n--- Analyzing {work} Page {page} Measure {measure} ---")
    
    page_str = f"page_{page:03d}"
    
    # Paths
    json_path = Path(f"logs/experiments/batch_verification_20260107_v4/{work}/{page_str}/numbering_final.json")
    
    # Image/Mask Paths
    if work == "prokofiev1":
        img_root = Path("data/evaluation2/images/prokofiev1")
        mask_root = Path(f"logs/hybrid_generalization/eval2_prokofiev1_{page_str}/baseline/{page_str}/{page_str}")
    else:
        img_root = Path("data/evaluation2/images/prokofiev5")
        mask_root = Path(f"logs/hybrid_generalization/eval2_prokofiev5_{page_str}/baseline/{page_str}/{page_str}")
        
    img_path = img_root / f"{page_str}.png"
    mask_path = mask_root / f"{page_str}_debug_6_notehead.png"
    
    out_img = output_dir / f"{work}_{page_str}_m{measure}.png"
    
    cmd = [
        ".venv_omr_dln/bin/python", "tools/debug_ocr_candidates.py",
        "--numbering-json", str(json_path),
        "--notehead-mask", str(mask_path),
        "--image", str(img_path),
        "--output-image", str(out_img),
        "--force-measure", str(measure),
        "--vertical-margin-check", "10",
        "--vertical-margin-ocr", "80",
        "--threshold", "150",
        "--erode-iter", "1"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("logs/experiments/failure_analysis_20260107"))
    args = parser.parse_args()
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    targets = [
        ("prokofiev1", 4, 204),
        ("prokofiev1", 4, 207),
        ("prokofiev1", 4, 210),
        ("prokofiev1", 5, 34),
        ("prokofiev1", 5, 36),
        ("prokofiev1", 6, 86),
        ("prokofiev5", 1, 1),
        ("prokofiev5", 1, 6),
        ("prokofiev5", 2, 26),
        ("prokofiev5", 2, 27),
        ("prokofiev5", 2, 28),
        ("prokofiev5", 2, 29),
        ("prokofiev5", 8, 101),
        # ("prokofiev5", 8, 63), # Added based on user context "63 next is 38"
        ("prokofiev5", 9, 63),
        ("prokofiev5", 17, 1),
    ]
    
    for work, page, measure in targets:
        run_debug(work, page, measure, args.output_dir)

if __name__ == "__main__":
    main()
