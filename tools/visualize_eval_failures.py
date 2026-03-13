import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
from tqdm import tqdm

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import (
    greedy_barline_match,
)


def parse_context(dir_name):
    parts = dir_name.split("_")
    if "page" not in parts:
        return None, None
    p_idx = parts.index("page")
    start = 1 if parts[0] == "eval2" else 0
    score_name = "_".join(parts[start:p_idx])
    page_name = "_".join(parts[p_idx:])
    return score_name, page_name


def find_files(gt_root, images_root, score_name, page_name):
    gt_path = None
    gt_candidates = []
    for p in Path(gt_root).rglob(f"{page_name}/boxes_sorted*.json"):
        if score_name.replace("_", "-").lower() in p.parts[-3].replace("_", "-").lower():
            gt_candidates.append(p)
    if gt_candidates:
        gt_candidates.sort(key=lambda x: x.name, reverse=True)
        gt_path = gt_candidates[0]

    img_path = None
    for p in Path(images_root).rglob(f"{page_name}.png"):
        if score_name.replace("_", "-").lower() in p.parts[-2].replace("_", "-").lower():
            img_path = p
            break
    return gt_path, img_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("debug_outputs/failure_visualizations_v8")
    )
    parser.add_argument("--threshold", type=float, default=0.1)
    args = parser.parse_args()

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    scored_files = list(args.scored_root.rglob("pipeline2_no_peak_scored.json"))
    global_counter = 1

    for scored_path in tqdm(scored_files):
        score_name, page_name = parse_context(scored_path.parent.name)
        if not score_name:
            continue
        gt_path, img_path = find_files(args.gt_root, args.images_root, score_name, page_name)
        if not gt_path or not img_path:
            continue

        with gt_path.open("r") as f:
            gt_boxes = [b["barline_location"] for b in json.load(f) if "barline_location" in b]
        with scored_path.open("r") as f:
            preds_all = json.load(f)
            preds = [p for p in preds_all if p["score"] >= args.threshold]

        # Call with rule_name="center_anchor"
        res = greedy_barline_match([p["bbox"] for p in preds], gt_boxes, rule_name="center_anchor")

        if not res.false_negative_indices and not res.false_positive_indices:
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        # FNs
        for gt_idx in res.false_negative_indices:
            gt_box = gt_boxes[gt_idx]
            best_score_any = 0.0
            matched_any = False
            for p in preds_all:
                # Manual matching for FN_det vs FN_cnn classification
                gx1, gy1, gx2, gy2 = gt_box
                px1, py1, px2, py2 = p["bbox"]
                if abs((gx1 + gx2) / 2.0 - (px1 + px2) / 2.0) <= 12:
                    vov = max(0, min(gy2, py2) - max(gy1, py1)) / float(
                        max(1, max(gy2, py2) - min(gy1, py1))
                    )
                    if vov >= 0.5:
                        matched_any = True
                        best_score_any = max(best_score_any, p["score"])

            error_type = "FN_cnn" if matched_any else "FN_det"
            x1, y1, x2, y2 = gt_box
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            pad = 150
            cx1, cy1 = max(0, cx - pad), max(0, cy - pad * 2)
            crop = img[
                max(0, cy - pad * 2) : min(img.shape[0], cy + pad * 2),
                max(0, cx - pad) : min(img.shape[1], cx + pad),
            ].copy()

            label = f"{global_counter:03d}_{error_type}_{score_name}_{page_name}"
            cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 0, 255), 3)
            cv2.putText(
                crop,
                f"ERR: {error_type} (MaxScore: {best_score_any:.4f})",
                (10, 30),
                0,
                0.6,
                (0, 0, 255),
                2,
            )
            cv2.imwrite(str(args.output_dir / f"{label}.png"), crop)
            global_counter += 1

        # FPs
        for pr_idx in res.false_positive_indices:
            p = preds[pr_idx]
            x1, y1, x2, y2 = p["bbox"]
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            pad = 150
            cx1, cy1 = max(0, cx - pad), max(0, cy - pad * 2)
            crop = img[
                max(0, cy - pad * 2) : min(img.shape[0], cy + pad * 2),
                max(0, cx - pad) : min(img.shape[1], cx + pad),
            ].copy()

            label = f"{global_counter:03d}_FP_{score_name}_{page_name}"
            cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 165, 255), 3)
            cv2.putText(
                crop, f"ERR: FP (Score: {p['score']:.3f})", (10, 30), 0, 0.6, (0, 165, 255), 2
            )
            cv2.imwrite(str(args.output_dir / f"{label}.png"), crop)
            global_counter += 1

    print(f"\nSuccess: Generated {global_counter - 1} images.")


if __name__ == "__main__":
    main()
