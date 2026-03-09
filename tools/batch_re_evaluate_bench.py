import shutil
import sys
from pathlib import Path

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.pipeline.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.probe_scan import run_probe_scan_batch


def find_bench_dirs():
    bench_root = PROJECT_ROOT / "logs/hybrid_pipeline_bench"
    # Find directories that contain hybrid_predictions.json and match the eval2_* pattern
    dirs = []
    for d in bench_root.iterdir():
        if d.is_dir() and d.name.startswith("eval2_") and (d / "hybrid_predictions.json").exists():
            dirs.append(d)
    return dirs


def parse_bench_name(bench_name):
    # Format: eval2_Score-Name_page_XXX_TIMESTAMP
    parts = bench_name.split("_")
    if "page" not in parts:
        return None, None
    page_idx = parts.index("page")
    score_name = "_".join(parts[1:page_idx])
    page_num = parts[page_idx + 1]
    return score_name, f"page_{page_num}"


def run_batch_verification():
    bench_dirs = find_bench_dirs()
    print(f"Found {len(bench_dirs)} benchmark directories.")

    output_root = PROJECT_ROOT / "artifacts/batch_verify_issue75"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    cnn_model_path = (
        PROJECT_ROOT
        / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    )

    # We need to provide images. Bench runs were likely 300 DPI, but we should use the same images.
    # Actually, the user says "活用できないですか", so we assume the images in data/evaluation2/images are compatible
    # or we can find images inside the bench dirs.

    # Let's map score/page to bench dir
    mapping = {}
    for d in bench_dirs:
        score, page = parse_bench_name(d.name)
        if score and page:
            mapping[(score, page)] = d

    # Run for ALL bench directories
    targets = []
    for score, page in mapping.keys():
        targets.append((score, page))

    # Sort for consistent output
    targets.sort()

    # Parameters from my fix
    detect_probe_kwargs = {
        "post_split_wide_candidates": True,
        "post_split_min_width_unit_ratio": 0.5,
        "post_split_box_width_unit_ratio": 0.4,
        "post_split_peak_distance_unit_ratio": 0.3,
        "divisi_rescue": True,
        "scan_gap_rescue": True,
        "scan_x_peak_rescue": True,
    }

    for score, page in targets:
        if (score, page) not in mapping:
            print(f"Skipping {score}/{page}: No bench data found.")
            continue

        bench_dir = mapping[(score, page)]
        print(f"\n>>> Verifying {score}/{page} using {bench_dir.name}")

        # 1. Setup temporary bands from bench results
        temp_bands = output_root / "temp_bands" / score / page
        temp_bands.mkdir(parents=True, exist_ok=True)
        # run_probe_scan_batch expects hybrid_results/{stem}_hybrid.json
        (temp_bands / "hybrid_results").mkdir(parents=True, exist_ok=True)
        shutil.copy(
            bench_dir / "hybrid_predictions.json",
            temp_bands / "hybrid_results" / f"{page}_hybrid.json",
        )

        # 2. Find image
        image_path = PROJECT_ROOT / f"data/evaluation2/images/{score}/{page}.png"
        if not image_path.exists():
            # Try flat structure
            image_path = PROJECT_ROOT / f"data/evaluation2/images/{page}.png"

        if not image_path.exists():
            print(f"Error: Image not found for {score}/{page}")
            continue

        # 3. Run Probe Scan
        run_probe_scan_batch(
            images=[image_path],
            output_root=output_root / "probe_scan",
            bands_from=temp_bands,
            staff_mask_dir=None,  # Use row_stats fallback as per my fix
            ink_threshold=180,
            min_ratio=0.70,
            min_height_ratio=0.012,
            score_name=score,
            detect_probe_kwargs=detect_probe_kwargs,
            skip_existing=False,
        )

        # 4. Run CNN Scoring
        run_cnn_scoring_batch(
            probe_output_root=output_root / "probe_scan",
            images=[image_path],
            model_path=cnn_model_path,
            threshold=0.1,
            score_name=score,
            crop_recenter_on_bbox_ink=True,
        )

    # 5. Global Evaluation
    print("\n--- Final Evaluation ---")
    import subprocess

    subprocess.run(
        [
            ".venv_pdf/bin/python",
            "tools/re_evaluate_global.py",
            "--scored-root",
            str(output_root / "probe_scan"),
            "--gt-root",
            "data/evaluation2/annotations",
            "--output-csv",
            str(output_root / "summary.csv"),
            "--eval-rule",
            "center_anchor",
            "--threshold",
            "0.1",
        ]
    )


if __name__ == "__main__":
    run_batch_verification()
