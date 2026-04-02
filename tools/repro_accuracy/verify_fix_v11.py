import sys
import logging
from pathlib import Path
import json

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from src.pipeline.steps.probe_scan import run_probe_scan_batch
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.common.barline_evaluation import greedy_barline_match

logging.basicConfig(level=logging.INFO)

def load_json(p):
    with open(p, "r") as f:
        return json.load(f)

def get_gt_boxes(gt_data):
    boxes = []
    for item in gt_data:
        if isinstance(item, list):
            boxes.append(tuple(item[:4]))
        elif isinstance(item, dict):
            if "barline_location" in item:
                boxes.append(tuple(item["barline_location"]))
            elif "box" in item:
                boxes.append(tuple(item["box"]))
    return boxes

def main():
    image_dir = Path("data/evaluation2/images/Va__Prokofiev_Symphony5")
    orig_images = sorted(list(image_dir.glob("*.png")))
    
    # We need a run that has SR images. Assuming they exist from a previous run or we can use the same bands_from
    bands_from = Path("logs/hybrid_generalization/verify_fixed_v10/20260330_095914")
    sr_images = []
    for img in orig_images:
        sr_img = bands_from / "sr" / "batch" / img.stem / f"{img.stem}.png"
        sr_images.append(sr_img)
        
    print(f"Collected {len(orig_images)} 1x images, {len(sr_images)} SR images")
    
    output_root = Path("logs/verify_fix_v11/probe_scan")
    
    filter_kwargs = {
        "left_margin_ratio": 0.12,
        "clef_left_ratio": 0.25,
        "min_height_median_ratio": 0.3,
        "ink_threshold": 180,
        "min_ink_ratio": 0.18,
        "paper_threshold": 200,
        "min_paper_overlap_ratio": 0.6,
        "min_staff_overlap_ratio": 0.01,
        "max_width_ratio": 0.05,
    }
    
    print("Running probe scan with NEW split seed logic...")
    run_probe_scan_batch(
        images=sr_images,
        output_root=output_root,
        bands_from=bands_from,
        staff_mask_dir=bands_from,
        clef_mask_dir=bands_from,
        ink_threshold=180,
        min_ratio=0.85, # BACK TO ORIGINAL VALUE
        min_height_ratio=0.012,
        min_width_ratio=0.0001,
        score_name="Va__Prokofiev_Symphony5",
        band_cluster_max_dist=None,
        band_min_row_count=1,
        vertical_closing=4,
        skip_existing=False,
        input_image_scale=2.0,
        detect_probe_kwargs={
            "scan_x_peak_rescue": True,
            "scan_x_peak_ratio_min": 1.2,
            "scan_rightmost_rescue": True,
            "scan_gap_rescue": True,
            "max_per_band": 200,
            "band_source": "row_stats",
            "probe_width": 4, # BACK TO ORIGINAL VALUE
            "band_row_pad_ratio": 0.1,
            "post_split_wide_candidates": True,
        },
        enable_heuristic_filters=True,
        candidate_filter_kwargs=filter_kwargs,
    )
    
    print("Running CNN scoring...")
    run_cnn_scoring_batch(
        probe_output_root=output_root,
        images=orig_images,
        model_path=Path("logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"),
        threshold=0.1, # BACK TO ORIGINAL VALUE
        batch_size=64,
        bands_from=bands_from,
        staff_vov_threshold=0.5,
        crop_recenter_on_bbox_ink=True,
        crop_recenter_max_shift_unit_ratio=0.5,
        input_image_scale=1.0,
        candidate_rescale_factor=0.5,
    )
    
    print("Evaluating results...")
    gt_base = Path("data/evaluation2/annotations/Va__Prokofiev_Symphony5")
    tp, fp, fn = 0, 0, 0
    fn_list = []
    
    for scored_file in sorted(output_root.rglob("pipeline2_no_peak_scored.json")):
        stem = scored_file.parent.name
        parts = stem.split("_")
        page_name = "page_" + parts[-1]
        
        gt_file = gt_base / page_name / "boxes_sorted.json"
        if not gt_file.exists():
            continue
            
        data = load_json(scored_file)
        preds = [tuple(c["bbox"]) for c in data if c["score"] >= 0.1]
        gts = get_gt_boxes(load_json(gt_file))
        
        res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=30.0)
        tp += len(res.matches)
        fp += len(res.false_positive_indices)
        fn += len(res.false_negative_indices)
        
        for fn_idx in res.false_negative_indices:
            fn_list.append((page_name, gts[fn_idx]))
        
    print("-" * 50)
    print(f"TOTAL: TP: {tp} | FP: {fp} | FN: {fn}")
    if (tp + fn) > 0:
        print(f"Recall: {tp/(tp+fn):.1