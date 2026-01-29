import subprocess
from pathlib import Path


def run_command(cmd):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True)


def main():
    base_out = Path("logs/experiments/rest_roi_batch_test")
    base_out.mkdir(parents=True, exist_ok=True)

    test_cases = [
        {
            "page": "001",
            "gt": "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted_v20251229.json",
            "mask": "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_6_notehead.png",
            "image": "data/evaluation2/images/prokofiev1/page_001.png",  # Using raw image if available, else homr input
            "homr_image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001.png",
            "staff_mask": "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_3_staff.png",
        },
        {
            "page": "004",
            "gt": "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/boxes_sorted_v20251229.json",
            "mask": "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_6_notehead.png",
            "image": "data/evaluation2/images/prokofiev1/page_004.png",
            "homr_image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004.png",
            "staff_mask": "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png",
        },
    ]

    for case in test_cases:
        p_out = base_out / f"page_{case['page']}"
        p_out.mkdir(parents=True, exist_ok=True)

        # 1. Generate Numbering JSON
        num_json = p_out / "numbering.json"
        num_overlay = p_out / "numbering_overlay.png"

        # Use homr_image for consistency with mask size
        img_path = case["homr_image"]

        cmd_num = (
            f".venv_omr_dln/bin/python tools/add_measure_numbers.py "
            f"--barlines {case['gt']} "
            f"--staff-mask {case['staff_mask']} "
            f"--image {img_path} "
            f"--output-json {num_json} "
            f"--output-overlay {num_overlay} "
            f"--page-number {int(case['page'])}"
        )
        run_command(cmd_num)

        # 2. Visualize ROIs
        roi_overlay = p_out / "roi_overlay.png"
        cmd_roi = (
            f".venv_omr_dln/bin/python tools/visualize_rest_rois.py "
            f"--numbering-json {num_json} "
            f"--notehead-mask {case['mask']} "
            f"--image {img_path} "
            f"--output-image {roi_overlay} "
            f"--vertical-margin 80 "
            f"--erode-iter 1"
        )
        run_command(cmd_roi)


if __name__ == "__main__":
    main()
