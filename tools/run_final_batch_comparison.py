import subprocess
import time
from pathlib import Path

import yaml

HOST_ROOT = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
PDF_ROOT = HOST_ROOT / "data/evaluation2/pdfs"
OUTPUT_BASE = HOST_ROOT / "logs/final_issue25_verification"


def run_pipeline_for_all(scale: int):
    name = "Bypass" if scale == 1 else "SRx2"
    mode_output = OUTPUT_BASE / name
    mode_output.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(list(PDF_ROOT.glob("*.pdf")))

    total_start = time.time()
    for pdf in pdfs:
        score_name = pdf.stem
        print(f"\n>>> Running {name} for {score_name}...")

        config = {
            "run": {
                "run_id": f"run_{score_name}",
                "output_root": f"/workspace/logs/final_issue25_verification/{name}",
            },
            "inputs": {
                "pdf_path": f"data/evaluation2/pdfs/{pdf.name}",
                "pdf_to_images": {
                    "output_dir": f"logs/preprocess/evaluation2/{score_name}",
                    "dpi": 360,
                    "interpolation": "area",
                },
            },
            "steps": {
                "pdf_to_images": True,
                "detection": True,
                "filter_pages": True,
                "numbering_base": False,
                "mmr_overrides": False,
                "apply_measure_overrides": False,
                "overlay": False,
            },
            "detection": {
                "enable_sr": True if scale > 1 else False,
                "sr_scale": scale,
                "crop_recenter_on_bbox_ink": True,
                "crop_recenter_max_shift_unit_ratio": 0.5,
                "ink_threshold": 180,
                "min_ratio": 0.85,
                "min_height_ratio": 0.012,
                "cnn_model_path": "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth",
                "cnn_threshold": 0.1,
                "divisi_rescue": True,
                "scan_gap_rescue": True,
                "scan_x_peak_rescue": True,
                "scan_center_on_peak": True,
                "max_per_band": 200,
                "post_split_wide_candidates": True,
                "post_split_min_width_unit_ratio": 0.5,
                "post_split_box_width_unit_ratio": 0.4,
                "post_split_peak_distance_unit_ratio": 0.3,
                "staff_mask_dir": None,
            },
        }

        config_path = mode_output / f"config_{score_name}.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Run via Makefile target
        subprocess.run(
            ["make", "run-pipeline", f"CONFIG={config_path.relative_to(HOST_ROOT)}"], check=True
        )

    total_duration = time.time() - total_start
    return total_duration


def main():
    if OUTPUT_BASE.exists():
        import shutil

        shutil.rmtree(OUTPUT_BASE)
    OUTPUT_BASE.mkdir(parents=True)

    print("Starting Final Batch Comparison (68 pages)...")

    # 1. Run Bypass
    t_bypass = run_pipeline_for_all(1)

    # 2. Run SR x2
    t_srx2 = run_pipeline_for_all(2)

    # 3. Final Evaluation
    print("\n" + "=" * 80)
    print("FINAL EVALUATION SUMMARY")
    print("=" * 80)

    for name in ["Bypass", "SRx2"]:
        print(f"\n--- {name} Results ---")
        res = subprocess.run(
            [
                ".venv_pdf/bin/python",
                "tools/re_evaluate_global.py",
                "--scored-root",
                str(OUTPUT_BASE / name),
                "--gt-root",
                "data/evaluation2/annotations",
                "--eval-rule",
                "center_anchor",
                "--threshold",
                "0.1",
            ],
            capture_output=True,
            text=True,
        )
        print(res.stdout)

    print("\nPerformance:")
    print(f"  Bypass total time: {t_bypass:.1f}s (Avg {t_bypass / 68:.2f}s/page)")
    print(f"  SRx2 total time:   {t_srx2:.1f}s (Avg {t_srx2 / 68:.2f}s/page)")


if __name__ == "__main__":
    main()
