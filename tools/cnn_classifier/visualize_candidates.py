import json
from pathlib import Path

import cv2

DEFAULT_PAGES = [
    {
        "name": "page_001",
        "image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001.png",
        "gt": "logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json",
        "preds": "logs/phase5b_confirmed_union_eval/page_001_hybrid_preds.json",
    },
    {
        "name": "page_3",
        "image": "logs/homr_eval/baseline_for_hybrid/page_3/page_3.png",
        "gt": "data/evaluation/annotations/page_003/boxes_sorted.json",
        "preds": "logs/phase5b_confirmed_union_eval/page_3_hybrid_preds.json",
    },
    {
        "name": "page_004",
        "image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004.png",
        "gt": "logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json",
        "preds": "logs/phase5b_confirmed_union_eval/page_004_hybrid_preds.json",
    },
    {
        "name": "page_10",
        "image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10.png",
        "gt": "logs/phase6_detector_miss/gt_rebuild/page_10_boxes_sorted.json",
        "preds": "logs/phase5b_confirmed_union_eval/page_10_hybrid_preds.json",
    },
    {
        "name": "page_15",
        "image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15.png",
        "gt": "logs/phase6_detector_miss/gt_rebuild/page_15_boxes_sorted.json",
        "preds": "logs/phase5b_confirmed_union_eval/page_15_hybrid_preds.json",
    },
]


def barline_iou(box1, box2):
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    inter_x1 = max(x1_1, x1_2)
    inter_y1 = max(y1_1, y1_2)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)
    if inter_x2 < inter_x1 or inter_y2 < inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1 + 1) * (inter_y2 - inter_y1 + 1)
    area1 = (x2_1 - x1_1 + 1) * (y2_1 - y1_1 + 1)
    area2 = (x2_2 - x1_2 + 1) * (y2_2 - y1_2 + 1)
    return inter_area / float(area1 + area2 - inter_area)


import argparse


def visualize_candidates(output_dir, predictions_root=None, fp_source_file="fp_boxes.json"):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    repo_root = Path.cwd()
    iou_threshold = 0.1  # Stricter filtering: if overlap > 0.1, consider it Ambiguous/TP and remove from FP set.

    for page in DEFAULT_PAGES:
        print(f"Processing {page['name']}...")
        img_path = repo_root / page["image"]
        gt_path = repo_root / page["gt"]

        if not img_path.exists():
            print(f"Image missing: {img_path}")
            continue

        img = cv2.imread(str(img_path))
        vis_img = img.copy()

        with gt_path.open("r") as f:
            gt_data = json.load(f)
        gt_boxes = [entry["barline_location"] for entry in gt_data]

        # Draw TP Candidates (Green) - These are ALL GT boxes currently
        for box in gt_boxes:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(vis_img, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Draw FP Candidates (Red)
        if predictions_root:
            # Construct path with fallback and template substitution
            filename = fp_source_file.replace("{page}", page["name"])

            # Try per_page structure first (standard)
            fp_json_path = Path(predictions_root) / "per_page" / page["name"] / filename
            if not fp_json_path.exists():
                # Try flattened structure (e.g. validatiion logs)
                fp_json_path = Path(predictions_root) / page["name"] / filename

            if fp_json_path.exists():
                with fp_json_path.open("r") as f:
                    data = json.load(f)
                # Handle different JSON structures: list of boxes OR dict with "scores"
                if isinstance(data, list):
                    # Standard format (geom_kept, fp_boxes)
                    candidates = data
                elif isinstance(data, dict) and "scores" in data:
                    # Debug format (geom_debug)
                    candidates = [item["bbox"] for item in data["scores"]]
                else:
                    print(f"Unknown JSON format in {fp_source_file}")
                    candidates = []

                # Auto-detect scale mismatch
                # Heuristic: Check if preds fit in image. If not, downscale?
                # Better: Check which scale maximizes IoU with GT (since we know GT matches Image)
                best_scale = 1.0
                best_match_count = -1

                # Scales to test: 1.0 (No change), 0.24 (300->72dpi), 0.5 (2x), 2.0, 4.16 (72->300dpi)
                test_scales = [1.0, 0.24, 0.5, 0.333, 0.125]

                # Check if we have enough boxes to test
                if len(candidates) > 0 and len(gt_boxes) > 0:
                    for scale in test_scales:
                        matches = 0
                        for c_box in candidates:  # Test ALL candidates
                            s_box = [x * scale for x in c_box]
                            for g_box in gt_boxes:
                                if barline_iou(g_box, s_box) > 0.1:  # Loose check
                                    matches += 1
                                    break
                        if matches > best_match_count:
                            best_match_count = matches
                            best_scale = scale

                    if best_scale != 1.0:
                        print(
                            f"  [Auto-Scale] Detected scale mismatch! Applying scale {best_scale:.3f} (Matches: {best_match_count})"
                        )

                fp_count = 0
                for raw_box in candidates:
                    # Apply detected scale
                    box = [coord * best_scale for coord in raw_box]

                    # Check if this candidate matches any GT
                    is_match = False
                    for gt_box in gt_boxes:
                        if barline_iou(gt_box, box) > iou_threshold:
                            is_match = True
                            break

                    if not is_match:
                        x1, y1, x2, y2 = map(int, map(round, box))
                        cv2.rectangle(vis_img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        fp_count += 1
                print(f"  Drawn {fp_count} FPs from {len(candidates)} candidates.")
            else:
                print(f"FP boxes not found: {fp_json_path}")
        else:
            # Legacy: Derived from unmatched preds
            preds_path = repo_root / page["preds"]
            with preds_path.open("r") as f:
                pred_boxes = json.load(f)

            # Identify Matching
            matched_indices = set()
            for gt_box in gt_boxes:
                best_iou = 0.0
                best_idx = -1
                for i, pred_box in enumerate(pred_boxes):
                    iou = barline_iou(gt_box, pred_box)
                    if iou > best_iou:
                        best_iou = iou
                        best_idx = i
                if best_iou > iou_threshold:
                    matched_indices.add(best_idx)

            fp_indices = [i for i in range(len(pred_boxes)) if i not in matched_indices]
            for idx in fp_indices:
                box = pred_boxes[idx]
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(vis_img, (x1, y1), (x2, y2), (0, 0, 255), 2)

            # Also Draw Matched Predictions (Blue) - only in legacy mode where we have all preds
            for idx in matched_indices:
                box = pred_boxes[idx]
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(vis_img, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), (255, 0, 0), 1)

        save_file = output_path / f"{page['name']}_candidates_vis.png"
        cv2.imwrite(str(save_file), vis_img)
        print(f"Saved: {save_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="logs/cnn_classifier/candidate_vis")
    parser.add_argument(
        "--predictions-root", type=Path, help="Root of predictions logs for explicit FP boxes"
    )
    parser.add_argument(
        "--fp-source-file", default="fp_boxes.json", help="Filename to load as FP candidates"
    )
    args = parser.parse_args()

    visualize_candidates(args.output_dir, args.predictions_root, args.fp_source_file)
