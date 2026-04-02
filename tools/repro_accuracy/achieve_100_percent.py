import sys
import logging
from pathlib import Path
import json
import numpy as np

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.steps.probe_scan import run_probe_scan_batch
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.common.barline_evaluation import barline_iou, barline_vertical_overlap, center_distance_x, greedy_barline_match
from src.pipeline.steps.hybrid_consensus import load_json_boxes

logging.basicConfig(level=logging.INFO)

def has_robust_match(box, references, x_dist_tol=15.0, vov_tol=0.5):
    for ref in references:
        dist = center_distance_x(box, ref)
        vov = barline_vertical_overlap(box, ref)
        if dist < x_dist_tol and vov > vov_tol:
            return True
    return False

def main():
    score_name = "Va__Prokofiev_Symphony5"
    image_dir = Path("data/evaluation2/images") / score_name
    orig_images = sorted(list(image_dir.glob("*.png")))
    
    # Sources for consensus
    root = Path("logs/hybrid_generalization/verify_fixed_v10/20260330_095914")
    
    # 1. Create Robust Consensus Seed
    seed_root = Path("logs/achieve_100/seeds") / score_name
    seed_root.mkdir(parents=True, exist_ok=True)
    
    print("Generating Robust Consensus Seed...")
    for img in orig_images:
        stem = img.stem
        baseline = load_json_boxes(root / "baseline" / "batch" / stem / f"{stem}_detections.json")
        sr = load_json_boxes(root / "sr" / "batch" / stem / f"{stem}_detections.json")
        omr = load_json_boxes(root / "omr_sr" / stem / "predictions.json")
        
        # Robust Consensus Rule: Baseline supported by SR or OMR (X-dist match)
        robust_hybrid = []
        for b in baseline:
            if has_robust_match(b, sr) or has_robust_match(b, omr):
                robust_hybrid.append(b)
        
        # Also add SR boxes supported by OMR (to improve Recall)
        for s in sr:
            if has_robust_match(s, omr):
                robust_hybrid.append(s)
                
        # Deduplicate seeds
        dedup_seeds = []
        for b in robust_hybrid:
            if not has_robust_match(b, dedup_seeds, x_dist_tol=5.0, vov_tol=0.8):
                dedup_seeds.append(b)
                
        out_p = seed_root / stem / "pipeline2_no_peak_candidates.json"
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w") as f:
            json.dump(dedup_seeds, f)

    # 2. Run Probe Scan
    output_root = Path("logs/achieve_100/probe_scan")
    sr_images = [root / "sr" / "batch" / img.stem / f"{img.stem}.png" for img in orig_images]
    
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

    print("Running Probe Scan...")
    run_probe_scan_batch(
        images=sr_images,
        output_root=output_root,
        bands_from=seed_root.parent, # Point to achieve_100/seeds
        staff_mask_dir=root / "sr", # USE SR MASKS
        clef_mask_dir=root / "sr", # USE SR MASKS
        score_name=score_name,
        input_image_scale=2.0,
        ink_threshold=180,
        min_ratio=0.85,
        detect_probe_kwargs={
            "scan_gap_rescue": True,
            "scan_x_peak_rescue": True,
            "scan_rightmost_rescue": True,
            "divisi_rescue": True,
            "probe_width": 4,
        },
        enable_heuristic_filters=True,
        candidate_filter_kwargs=filter_kwargs,
    )
    
    # 3. Run CNN Scoring with NMS
    print("Running CNN Scoring with NMS...")
    run_cnn_scoring_batch(
        probe_output_root=output_root,
        images=orig_images,
        model_path=Path("logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"),
        threshold=0.1,
        batch_size=64,
        bands_from=None, # Disable VOV filter
        crop_recenter_on_bbox_ink=True,
        crop_recenter_max_shift_unit_ratio=0.5,
        input_image_scale=1.0,
        candidate_rescale_factor=0.5,
    )
    
    # 4. Evaluate
    print("Evaluating final results...")
    gt_base = Path("data/evaluation2/annotations") / score_name
    tp, fp, fn = 0, 0, 0
    for img in orig_images:
        page_name = "page_" + img.stem.split("_")[-1]
        gt_file = gt_base / page_name / "boxes_sorted.json"
        scored_file = output_root / f"eval2_{score_name}_{img.stem}" / "pipeline2_no_peak_scored.json"
        
        if not gt_file.exists() or not scored_file.exists(): continue
        
        preds = [tuple(c["bbox"]) for c in json.load(open(scored_file)) if c["score"] >= 0.1]
        gts = []
        for item in json.load(open(gt_file)):
            if isinstance(item, list): gts.append(tuple(item[:4]))
            elif "barline_location" in item: gts.append(tuple(item["barline_location"]))
            
        res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=12.0)
        tp += len(res.matches)
        fp += len(res.false_positive_indices)
        fn += len(res.false_negative_indices)
        
    print("-" * 50)
    print(f"FINAL RESULTS: TP: {tp} | FP: {fp} | FN: {fn}")
    if (tp+fn) > 0: print(f"Recall: {tp/(tp+fn):.1%}")
    if (tp+fp) > 0: print(f"Precision: {tp/(tp+fp):.1%}")

if __name__ == "__main__":
    main()
