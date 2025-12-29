import argparse
import json
from pathlib import Path
from collections import defaultdict

def calculate_iou(boxA, boxB):
    """
    Calculate the Intersection over Union (IoU) of two bounding boxes.
    Each box is in the format [x1, y1, x2, y2].
    """
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    unionArea = float(boxAArea + boxBArea - interArea)
    if unionArea == 0:
        return 0
    return interArea / unionArea

def find_match(gt_bbox, pred_bboxes, iou_threshold):
    """
    Find if a matching prediction exists for a given ground truth bbox.
    """
    for pred_bbox in pred_bboxes:
        iou = calculate_iou(gt_bbox["bbox"], pred_bbox["bbox"])
        if iou >= iou_threshold:
            return True
    return False

def load_json_predictions(path):
    """Load bboxes from a JSON file."""
    if not path or not Path(path).exists():
        # print(f"Warning: Prediction file not found: {path}")
        return []
    with open(path, 'r') as f:
        data = json.load(f)

    # Handles lists of {"bbox": [x1,y1,x2,y2]}
    if isinstance(data, list) and len(data) > 0 and "bbox" in data[0]:
        return data
    # Handles lists of [x1, y1, x2, y2]
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
         return [{"bbox": bbox} for bbox in data]
    # Handles homr _detections.json format
    if isinstance(data, dict) and "predictions" in data:
        bboxes = [p["orig_bbox"] for p in data.get("predictions", [])]
        return [{"bbox": b} for b in bboxes]
    # Handles fn_only.json format
    if isinstance(data, list) and len(data) > 0 and "barline_location" in data[0]:
        return [{"bbox": item["barline_location"], "id": item.get("id", "N/A")} for item in data]

    # print(f"Warning: Could not extract bboxes from {path}")
    return []


def analyze_page(page_context, iou_threshold):
    """
    Analyzes a single page's false negatives.
    """
    fn_gt_path = page_context["fn_gt"]
    homr_base_path = page_context["homr_base"]
    homr_sr_path = page_context["homr_sr"]
    omr_dln_path = page_context["omr_dln"]
    hybrid_path = page_context["hybrid"]

    fn_gt_bboxes = load_json_predictions(fn_gt_path)
    homr_base_preds = load_json_predictions(homr_base_path)
    homr_sr_preds = load_json_predictions(homr_sr_path)
    omr_dln_preds = load_json_predictions(omr_dln_path)
    hybrid_preds = load_json_predictions(hybrid_path)

    # Combine homr predictions
    homr_preds = homr_base_preds + homr_sr_preds

    results = []
    for fn_bbox in fn_gt_bboxes:
        fn_id = fn_bbox.get("id", str(fn_bbox["bbox"]))
        analysis = {
            "fn_id": fn_id,
            "bbox": fn_bbox["bbox"],
            "attribution_label": "",
            "evidence": {}
        }

        is_in_hybrid = find_match(fn_bbox, hybrid_preds, iou_threshold)
        analysis["evidence"]["present_in_hybrid"] = is_in_hybrid

        if is_in_hybrid:
            analysis["attribution_label"] = "post_filter_removal"
            results.append(analysis)
            continue

        is_in_homr = find_match(fn_bbox, homr_preds, iou_threshold)
        is_in_omr_dln = find_match(fn_bbox, omr_dln_preds, iou_threshold)
        analysis["evidence"]["present_in_homr"] = is_in_homr
        analysis["evidence"]["present_in_omr_dln"] = is_in_omr_dln

        if is_in_homr or is_in_omr_dln:
            analysis["attribution_label"] = "hybrid_integration_loss"
        else:
            analysis["attribution_label"] = "ambiguous"
            analysis["evidence"]["reason"] = "Missed by both homr and omr-dln source models."

        results.append(analysis)

    return results

def main():
    IOU_THRESHOLD = 0.4

    # Define the pages and their corresponding file paths
    PAGES = [
        {
            "name": "Beethoven page_10",
            "dataset": "Beethoven",
            "stem": "page_10",
            "run_dir": "logs/hybrid_generalization/page_10_hybrid_test",
            "fn_gt": "data/training/annotations/page_010/fn_only.json",
        },
        {
            "name": "Beethoven page_15",
            "dataset": "Beethoven",
            "stem": "page_15",
            "run_dir": "logs/hybrid_generalization/page_15_hybrid_test",
            "fn_gt": "data/training/annotations/page_015/fn_only.json",
        },
        {
            "name": "Prokofiev page_001",
            "dataset": "Prokofiev",
            "stem": "page_001",
            "run_dir": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001",
            "fn_gt": "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json",
        },
        {
            "name": "Prokofiev page_004",
            "dataset": "Prokofiev",
            "stem": "page_004",
            "run_dir": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004",
            "fn_gt": "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json",
        }
    ]

    all_results = []
    aggregate_summary = defaultdict(lambda: defaultdict(int))

    for page in PAGES:
        run_dir = page["run_dir"]
        stem = page["stem"]
        
        # This path structure is strange, but confirmed from file listings
        homr_base_path = f"{run_dir}/baseline/{stem}/{stem}/{stem}_detections.json"
        homr_sr_path = f"{run_dir}/sr/{stem}/{stem}/{stem}_detections.json"
        
        # Some older runs might not have this deep structure
        if not Path(homr_base_path).exists():
             homr_base_path = f"{run_dir}/baseline/{stem}/{stem}_detections.json"
        if not Path(homr_sr_path).exists():
             homr_sr_path = f"{run_dir}/sr/{stem}/{stem}_detections.json"

        context = {
            "fn_gt": page["fn_gt"],
            "homr_base": homr_base_path,
            "homr_sr": homr_sr_path,
            "omr_dln": f"{run_dir}/omr_sr/predictions.json",
            "hybrid": f"{run_dir}/hybrid_predictions.json",
        }

        page_results = analyze_page(context, IOU_THRESHOLD)
        all_results.append({"page": page["name"], "results": page_results})

        # Update summary
        for res in page_results:
            label = res["attribution_label"]
            aggregate_summary["total"][label] += 1
            aggregate_summary[page["dataset"]][label] += 1

    # --- Output Results ---
    print("="*80)
    print("FN Attribution Analysis Results")
    print("="*80)

    print("\n--- Per-Page Breakdown ---")
    for page_res in all_results:
        print(f"\n--- {page_res['page']} ---")
        for item in page_res["results"]:
            print(f"  FN ID: {item['fn_id']}, BBox: {item['bbox']}, Label: {item['attribution_label']}")
            # print(f"    Evidence: {item['evidence']}")
        print("-"*20)


    print("\n" + "="*80)
    print("--- Aggregate Summary ---")
    print(json.dumps(aggregate_summary, indent=2))
    print("="*80)


if __name__ == "__main__":
    main()