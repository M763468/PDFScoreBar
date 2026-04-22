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
    is_barline_match,
)


def find_scored_file(scored_root, subdir, page_name):
    # Try multiple patterns used in various runs
    candidates = [
        Path(scored_root) / subdir / page_name / "pipeline2_no_peak_scored.json",
        Path(scored_root) / f"eval2_{subdir}_{page_name}" / "pipeline2_no_peak_scored.json",
        # New pattern for nested pipeline runs
        Path(scored_root)
        / subdir
        / "intermediate"
        / "probe_scan"
        / f"eval2_{subdir}_{page_name}"
        / "pipeline2_no_peak_scored.json",
        # Pattern observed in full inprocess run where stem was used as score name
        Path(scored_root)
        / subdir
        / "intermediate"
        / "probe_scan"
        / f"eval2_{page_name}_{page_name}"
        / "pipeline2_no_peak_scored.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("debug_outputs/failure_visualizations_v9")
    )
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--eval-rule", default="center_anchor")
    args = parser.parse_args()

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # LOOP BASED ON GT (matches official evaluation behavior)
    global_counter = 1

    subdirs = sorted([d.name for d in Path(args.gt_root).iterdir() if d.is_dir()])

    for subdir in tqdm(subdirs, desc="Scores"):
        page_dirs = sorted([d for d in (Path(args.gt_root) / subdir).iterdir() if d.is_dir()])
        for page_dir in page_dirs:
            page_name = page_dir.name
            gt_candidates = sorted(list(page_dir.glob("boxes_sorted*.json")), reverse=True)
            if not gt_candidates:
                continue
            gt_file = gt_candidates[0]

            with open(gt_file, "r") as f:
                gt_data = json.load(f)
                gt_boxes = [
                    tuple(b["barline_location"]) for b in gt_data if "barline_location" in b
                ]

            scored_path = find_scored_file(args.scored_root, subdir, page_name)
            candidates = []
            if scored_path:
                with open(scored_path, "r") as f:
                    candidates = json.load(f)

            accepted_candidates = [
                tuple(c["bbox"]) for c in candidates if c["score"] >= args.threshold
            ]

            res = greedy_barline_match(accepted_candidates, gt_boxes, rule_name=args.eval_rule)

            if not res.false_negative_indices and not res.false_positive_indices:
                continue

            # Load image
            img_path = args.images_root / subdir / f"{page_name}.png"
            img = cv2.imread(str(img_path))
            if img is None:
                continue

            # FNs
            for fn_idx in res.false_negative_indices:
                gt_box = gt_boxes[fn_idx]
                found_by_detector = False
                best_score_any = 0.0
                for cand in candidates:
                    if is_barline_match(tuple(cand["bbox"]), gt_box, args.eval_rule):
                        found_by_detector = True
                        best_score_any = max(best_score_any, cand["score"])

                error_type = "FN_cnn" if found_by_detector else "FN_det"
                x1, y1, x2, y2 = gt_box
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                pad = 150
                crop = img[
                    max(0, cy - pad * 2) : min(img.shape[0], cy + pad * 2),
                    max(0, cx - pad) : min(img.shape[1], cx + pad),
                ].copy()
                cx1, cy1 = max(0, cx - pad), max(0, cy - pad * 2)

                label = f"{global_counter:03d}_{error_type}_{subdir}_{page_name}_fn{fn_idx}"
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
            for fp_idx in res.false_positive_indices:
                fp_box = accepted_candidates[fp_idx]
                fp_score = next((c["score"] for c in candidates if tuple(c["bbox"]) == fp_box), 0.0)

                x1, y1, x2, y2 = fp_box
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                pad = 150
                crop = img[
                    max(0, cy - pad * 2) : min(img.shape[0], cy + pad * 2),
                    max(0, cx - pad) : min(img.shape[1], cx + pad),
                ].copy()
                cx1, cy1 = max(0, cx - pad), max(0, cy - pad * 2)

                label = f"{global_counter:03d}_FP_{subdir}_{page_name}_fp{fp_idx}"
                cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 165, 255), 3)
                cv2.putText(
                    crop, f"ERR: FP (Score: {fp_score:.3f})", (10, 30), 0, 0.6, (0, 165, 255), 2
                )
                cv2.imwrite(str(args.output_dir / f"{label}.png"), crop)
                global_counter += 1

    print(f"\nFinal: Generated {global_counter - 1} images in {args.output_dir}")


if __name__ == "__main__":
    main()
