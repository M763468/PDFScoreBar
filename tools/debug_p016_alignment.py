import json
from pathlib import Path

import cv2


def debug_p016():
    numb_path = Path("logs/experiments/batch_cnnv1/prokofiev5/page_016/numbering_initial.json")
    numb = json.load(open(numb_path))

    img_path = Path("data/evaluation2/images/prokofiev5/page_016.png")
    img = cv2.imread(str(img_path))

    # Map global index to bbox
    global_map = []
    for s_idx, system in enumerate(numb["pages"][0]["systems"]):
        for m_idx, measure in enumerate(system["measures"]):
            global_map.append(
                {"g_idx": len(global_map), "s": s_idx, "m": m_idx, "bbox": measure["bbox"]}
            )

    # GT indices from rest_gt.json
    gt_indices = [2, 11, 31, 36]

    for g_idx in gt_indices:
        if g_idx < len(global_map):
            info = global_map[g_idx]
            x1, y1, x2, y2 = info["bbox"]
            # Crop a wide area around the measure
            crop = img[
                max(0, y1 - 100) : min(img.shape[0], y2 + 100),
                max(0, x1 - 200) : min(img.shape[1], x2 + 200),
            ]
            # Draw bbox on crop for visual reference
            cv2.rectangle(crop, (200, 100), (200 + (x2 - x1), 100 + (y2 - y1)), (0, 0, 255), 2)
            out_name = f"debug_p016_gidx_{g_idx}.jpg"
            cv2.imwrite(out_name, crop)
            print(f"Index {g_idx} -> System {info['s']}, Measure {info['m']} (Saved to {out_name})")
        else:
            print(f"Index {g_idx} is out of bounds (Total detected measures: {len(global_map)})")


if __name__ == "__main__":
    debug_p016()
