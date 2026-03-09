import sys
from pathlib import Path

import cv2

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes


def main():
    img_path = (
        PROJECT_ROOT
        / "logs/full_pipeline_runs/bypass_sr_test/eval2_bypass_sr_test_v2/inputs/images/page_001.png"
    )
    gt_path = (
        PROJECT_ROOT
        / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    )

    img = cv2.imread(str(img_path))
    gt_boxes = load_ground_truth_boxes(gt_path)

    # GT 38, 39 are very close (dist 11)
    # GT 40, 41 are very close (dist 12)
    # GT 36 is missing

    targets = [36, 38, 39, 40, 41]
    for idx in targets:
        box = gt_boxes[idx]
        x1, y1, x2, y2 = box
        # Crop with margin
        margin = 100
        cy1 = max(0, y1 - margin)
        cy2 = min(img.shape[0], y2 + margin)
        cx1 = max(0, x1 - margin)
        cx2 = min(img.shape[1], x2 + margin)

        crop = img[cy1:cy2, cx1:cx2].copy()
        # Draw the box
        cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 0, 255), 2)

        out_path = PROJECT_ROOT / f"artifacts/inspect_gt_{idx}.png"
        cv2.imwrite(str(out_path), crop)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
