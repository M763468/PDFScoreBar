import argparse
import json
from pathlib import Path

import cv2


def export_crops(work, page, target_measure, output_dir):
    page_str = f"page_{page:03d}"
    print(f"Exporting {work} {page_str} M{target_measure}...")

    # Paths
    json_path = Path(
        f"logs/experiments/batch_verification_20260107_v5/{work}/{page_str}/numbering_final.json"
    )
    if not json_path.exists():
        print(f"  [Error] JSON not found: {json_path}")
        return

    img_path = Path(f"data/evaluation2/images/{work}/{page_str}.png")
    mask_path = Path(
        f"logs/hybrid_generalization/eval2_{work}_{page_str}/baseline/{page_str}/{page_str}/{page_str}_debug_6_notehead.png"
    )

    img = cv2.imread(str(img_path))
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

    with open(json_path, "r") as f:
        data = json.load(f)

    # Find measure. Since numbering might be offset, we look for nearby numbers.
    # We will export the target and 2 neighbors.
    found = False
    for page_data in data["pages"]:
        for system in page_data["systems"]:
            for measure in system["measures"]:
                m_num = measure["number"]
                if abs(m_num - target_measure) <= 2:
                    bbox = measure["bbox"]
                    x1, y1, x2, y2 = bbox

                    # 1. Broad Context Crop (200px margin)
                    pad = 200
                    cx1 = max(0, x1 - pad)
                    cy1 = max(0, y1 - pad)
                    cx2 = min(img.shape[1], x2 + pad)
                    cy2 = min(img.shape[0], y2 + pad)
                    context_crop = img[cy1:cy2, cx1:cx2].copy()

                    # Draw ROI indicators on context
                    # Blue: Measure BBox
                    cv2.rectangle(
                        context_crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (255, 0, 0), 2
                    )

                    crop_name = f"{work}_{page_str}_M{m_num}_context.png"
                    cv2.imwrite(str(output_dir / crop_name), context_crop)

                    # 2. OCR ROI (80px margin)
                    ry1 = max(0, y1 - 80)
                    ry2 = min(img.shape[0], y2 + 30)
                    rx1 = max(0, x1 - 10)
                    rx2 = min(img.shape[1], x2 + 10)
                    ocr_crop = img[ry1:ry2, rx1:rx2]
                    cv2.imwrite(
                        str(output_dir / f"{work}_{page_str}_M{m_num}_ocr_roi.png"), ocr_crop
                    )

                    # 3. Mask ROI
                    # Scale logic simplified for crop
                    mx1 = int(x1 * mask.shape[1] / img.shape[1])
                    my1 = int(y1 * mask.shape[0] / img.shape[0])
                    mx2 = int(x2 * mask.shape[1] / img.shape[1])
                    my2 = int(y2 * mask.shape[0] / img.shape[0])
                    mask_crop = mask[
                        max(0, my1 - 20) : min(mask.shape[0], my2 + 20),
                        max(0, mx1 - 20) : min(mask.shape[1], mx2 + 20),
                    ]
                    cv2.imwrite(str(output_dir / f"{work}_{page_str}_M{m_num}_mask.png"), mask_crop)

                    if m_num == target_measure:
                        found = True

    if not found:
        print(f"  [Warn] Exact measure {target_measure} not found in JSON.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path("logs/experiments/failure_crops_20260108")
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        ("prokofiev1", 3, 7),
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
        ("prokofiev5", 8, 63),
        ("prokofiev5", 9, 63),
        ("prokofiev5", 17, 1),
    ]

    for work, page, measure in targets:
        export_crops(work, page, measure, args.output_dir)


if __name__ == "__main__":
    main()
