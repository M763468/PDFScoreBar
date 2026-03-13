import subprocess
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SUBSET = [
    (
        "Shostakovich-Festival_Overture_Va",
        "data/evaluation2/pdfs/Shostakovich-Festival_Overture_Va.pdf",
        "1,2",
    ),
    ("Shostakovich-Sym5-Va", "data/evaluation2/pdfs/Shostakovich-Sym5-Va.pdf", "1,2"),
    (
        "Sibelius-Violin_Concerto-Viola",
        "data/evaluation2/pdfs/Sibelius-Violin_Concerto-Viola.pdf",
        "1,6",
    ),
    ("Va_Prokofiev_Symphony1", "data/evaluation2/pdfs/Va_Prokofiev_Symphony1.pdf", "1,5"),
]


def run_eval():
    import time

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_base_name = f"logs/bypass_eval_{timestamp}"
    output_base = PROJECT_ROOT / output_base_name
    output_base.mkdir(parents=True)

    results = []

    for score_name, pdf_path, pages in SUBSET:
        print(f"\n>>> Processing {score_name} (Pages: {pages})")

        # We MUST use /workspace prefix for the container to see it as the mounted volume
        abs_output_root = f"/workspace/{output_base_name}"

        config = {
            "run": {"run_id": f"run_{score_name}", "output_root": abs_output_root},
            "inputs": {
                "pdf_path": pdf_path,
                "pdf_to_images": {
                    "output_dir": f"{abs_output_root}/images_{score_name}",
                    "dpi": 360,
                    "pages": pages,
                    "interpolation": "area",
                    "overwrite": True,
                },
            },
            "steps": {
                "pdf_to_images": True,
                "detection": True,
                "filter_pages": True,
                "numbering_base": True,
                "mmr_overrides": False,
                "apply_measure_overrides": False,
                "overlay": True,
            },
            "detection": {
                "enable_sr": False,
                "crop_recenter_on_bbox_ink": True,
                "crop_recenter_max_shift_unit_ratio": 0.5,
                "hybrid_output_root": f"{abs_output_root}/hybrid_{score_name}",
                "probe_score_name": score_name,
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

        config_path = output_base / f"config_{score_name}.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        rel_config_path = config_path.relative_to(PROJECT_ROOT)
        subprocess.run(["make", "run-pipeline", f"CONFIG={rel_config_path}"], check=True)

        # Evaluate each page
        for p in pages.split(","):
            p_pad = p.zfill(3)
            run_id_page = f"eval2_{score_name}_page_{p_pad}"
            pred_json = (
                output_base
                / f"run_{score_name}/intermediate/probe_scan/{run_id_page}/pipeline2_no_peak_filtered_cnn.json"
            )
            gt_json = (
                PROJECT_ROOT
                / f"data/evaluation2/annotations/{score_name}/page_{p_pad}/boxes_sorted.json"
            )

            if not pred_json.exists():
                print(f"Warning: Pred JSON not found at {pred_json}")
                continue

            eval_cmd = [
                str(PROJECT_ROOT / ".venv_pdf/bin/python"),
                "tools/eval_existing_json.py",
                "--pred",
                str(pred_json),
                "--gt",
                str(gt_json),
                "--rule",
                "center_anchor",
            ]

            env = {"PYTHONPATH": f".:src:{PROJECT_ROOT}"}
            res = subprocess.run(eval_cmd, capture_output=True, text=True, env=env)
            print(res.stdout)
            results.append((score_name, p_pad, res.stdout))

    with open(output_base / "batch_summary.txt", "w") as f:
        for score, page, out in results:
            f.write(f"=== {score} Page {page} ===\n{out}\n")


if __name__ == "__main__":
    run_eval()
