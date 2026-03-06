
import json
import subprocess
import sys
from pathlib import Path
import shutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.pipeline.probe_scan import run_probe_scan_batch
from tools.cnn_classifier.score_candidates_batch import run_scoring_batch
from src.common.barline_evaluation import greedy_barline_match
from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes

def run_test(tag, image_path, sr_enabled, sr_scale):
    print(f"\n>>> Testing {tag} (SR: {sr_enabled}, Scale: {sr_scale})")
    
    # 1. Setup paths
    gt_path = PROJECT_ROOT / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    bands_from = PROJECT_ROOT / "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
    output_root = PROJECT_ROOT / f"artifacts/verify_v12_{tag}"
    
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    # 2. Probe Scan (Issue 44 Params)
    # ...
    # We need to manually place the candidates since we are bypass-testing
    # and run_probe_scan_batch expects existing ones if bands_from is provided.
    
    # If SR is requested, we need to provide the SR image.
    # We can use the images already generated in previous manual runs.
    if sr_enabled:
        if sr_scale == 4:
            sr_img = PROJECT_ROOT / "artifacts/manual_sr_x4/sr4/page_001/page_001.png"
        else:
            sr_img = PROJECT_ROOT / "logs/hybrid_generalization/sr_x2_test/eval2_sr_x2_test_split/sr/batch/page_001/page_001.png"
        target_images = [sr_img]
    else:
        target_images = [image_path]

    detect_probe_kwargs = {
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.5,
        "scan_gap_rescue_min_ratio": 0.3,
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "divisi_rescue": True,
        "scan_center_on_peak": True,
        "max_per_band": 100,
    }

    run_probe_scan_batch(
        images=target_images,
        output_root=output_root,
        bands_from=None, 
        staff_mask_dir=None,
        ink_threshold=180,
        min_ratio=0.85,
        min_height_ratio=0.012,
        detect_probe_kwargs=detect_probe_kwargs,
        score_name="Va_Prokofiev_Symphony1"
    )
    
    # Now place the v12 candidates into the run dir created by probe scan
    run_dir = list(output_root.glob("eval2_Va_Prokofiev_Symphony1_page_001"))[0]
    source_cand = bands_from / "Va_Prokofiev_Symphony1/page_001/pipeline2_no_peak_candidates.json"
    
    if sr_enabled:
        with open(source_cand) as f:
            cands = json.load(f)
        # Scale coords up to SR scale
        scaled_cands = [[int(v * sr_scale) for v in b] for b in cands]
        with open(run_dir / "pipeline2_no_peak_candidates.json", "w") as f:
            json.dump(scaled_cands, f)
    else:
        shutil.copy(source_cand, run_dir / "pipeline2_no_peak_candidates.json")

    # 3. CNN Scoring
    model_path = PROJECT_ROOT / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    
    from tools.cnn_classifier.score_candidates_batch import run_scoring_batch
    
    # We must match the expected images_root such that score_name/page_num.png works.
    # images_root / score_name / page_num.png
    # In our case: PROJECT_ROOT / artifacts / manual_sr_x4 / sr4 / page_001.png
    # But resolve_image_path expects: images_root / Va_Prokofiev_Symphony1 / page_001.png
    
    # Let's just use a custom images_root by symlinking or copying temporarily if needed,
    # OR better: run_scoring_batch now takes logs and images_root.
    
    if sr_enabled:
        # Create a temp images root that matches the expected structure
        temp_img_root = output_root / "temp_images"
        score_dir = temp_img_root / "Va_Prokofiev_Symphony1"
        score_dir.mkdir(parents=True)
        shutil.copy(target_images[0], score_dir / "page_001.png")
        current_images_root = temp_img_root
    else:
        current_images_root = PROJECT_ROOT / "logs/full_pipeline_runs/bypass_sr_test/eval2_bypass_sr_test_v2/inputs/images"
        # Wait, that would be inputs/images/page_001.png. resolve expects score_name subdir.
        temp_img_root = output_root / "temp_images"
        score_dir = temp_img_root / "Va_Prokofiev_Symphony1"
        score_dir.mkdir(parents=True)
        shutil.copy(image_path, score_dir / "page_001.png")
        current_images_root = temp_img_root

    run_scoring_batch(
        logs=output_root,
        model=model_path,
        threshold=0.1,
        images_root=current_images_root,
        crop_recenter_on_bbox_ink=True, 
        crop_recenter_max_shift_unit_ratio=0.5,
        bands_from=None if sr_enabled else bands_from, # Bypass geo-filter for SR due to coords mismatch
        staff_vov_threshold=0.5,
        overwrite=True,
    )

    # 4. Eval
    # Result folder naming is tricky due to score_name
    result_json = list(output_root.glob("**/pipeline2_no_peak_scored.json"))[0]
    with open(result_json) as f:
        scored_data = json.load(f)
    
    preds = [tuple(item["bbox"]) for item in scored_data if item["score"] >= 0.1]
    
    # If SR was used, map preds back to 1x for eval against GT
    if sr_enabled:
        preds = [(int(x1/sr_scale), int(y1/sr_scale), int(x2/sr_scale), int(y2/sr_scale)) for x1,y1,x2,y2 in preds]

    gt_boxes = load_ground_truth_boxes(gt_path)
    match_result = greedy_barline_match(preds, gt_boxes, rule_name="center_anchor")
    
    print(f"RESULT {tag}: P={len(match_result.matches)/(len(match_result.matches)+len(match_result.false_positive_indices)):.4f}, R={len(match_result.matches)/len(gt_boxes):.4f}, TP={len(match_result.matches)}, FN={len(match_result.false_negative_indices)}")

def main():
    orig_image = PROJECT_ROOT / "logs/full_pipeline_runs/bypass_sr_test/eval2_bypass_sr_test_v2/inputs/images/page_001.png"
    
    # Compare SR levels using EXACT same Issue #44 candidates
    run_test("Bypass_v12", orig_image, False, 1)
    run_test("SRx2_v12", None, True, 2)
    run_test("SRx4_v12", None, True, 4)

if __name__ == "__main__":
    main()
