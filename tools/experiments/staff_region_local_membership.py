import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_local_staff_bands(
    mask: np.ndarray,
    x_center: int,
    scan_width_ratio: float = 0.2,
    gap_tolerance: int = 5,
    min_height: int = 10,
    line_ratio_thresh: float = 0.1,
) -> List[Tuple[int, int]]:
    """
    Get staff bands by looking only at a vertical strip around x_center.
    """
    h, w = mask.shape[:2]
    scan_width = int(w * scan_width_ratio)
    x1 = max(0, int(x_center - scan_width // 2))
    x2 = min(w - 1, int(x_center + scan_width // 2))
    if x2 <= x1:
        return []

    strip = mask[:, x1 : x2 + 1]
    # Calculate row-wise ink ratio
    row_ratio = strip.sum(axis=1) / float(strip.shape[1])
    # Assume mask values are 255. If so, max ratio is 255.
    # Convert to 0-1 range if mask max is > 1.
    if strip.max() > 1:
        row_ratio = row_ratio / 255.0

    active_rows = np.where(row_ratio >= line_ratio_thresh)[0]
    if active_rows.size == 0:
        return []

    # Group adjacent active rows
    groups = []
    start = int(active_rows[0])
    prev = int(active_rows[0])
    for r in active_rows[1:]:
        if int(r) - prev <= gap_tolerance:
            prev = int(r)
            continue
        groups.append((start, prev))
        start = int(r)
        prev = int(r)
    groups.append((start, prev))

    # Filter by minimum height (which acts as a proxy for staff height)
    # Since we are looking at region masks, gap_tolerance could merge lines into staves.
    # If we use `debug_3_staff` (line masks), we might need larger gap_tolerance.
    bands = []
    for g_start, g_end in groups:
        if (g_end - g_start + 1) >= min_height:
            bands.append((g_start, g_end))

    return bands


def filter_by_local_staff_overlap(
    boxes: List[List[int]],
    mask: np.ndarray,
    scan_width_ratio: float = 0.2,
    vov_threshold: float = 0.5,
    gap_tolerance: int = 5,
    min_height: int = 10,
    line_ratio_thresh: float = 0.1,
) -> Tuple[List[List[int]], List[List[int]]]:
    kept = []
    dropped = []
    for box in boxes:
        x1, y1, x2, y2 = box
        cx = (x1 + x2) / 2.0
        local_bands = get_local_staff_bands(
            mask,
            x_center=int(cx),
            scan_width_ratio=scan_width_ratio,
            gap_tolerance=gap_tolerance,
            min_height=min_height,
            line_ratio_thresh=line_ratio_thresh,
        )
        
        h_box = max(1, y2 - y1)
        max_vov = 0.0
        for by1, by2 in local_bands:
            overlap = min(y2, by2) - max(y1, by1)
            vov = max(0, overlap) / float(h_box)
            max_vov = max(max_vov, vov)
            
        if max_vov >= vov_threshold:
            kept.append(box)
        else:
            dropped.append(box)
            
    return kept, dropped


def main():
    root_dir = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
    eval2_dir = root_dir / "data/evaluation2/annotations"
    
    # We will use the v12_restore_nms_x0_staff0 as our baseline run for predictions
    baseline_run_dir = root_dir / "logs/hybrid_generalization/verification_full_v12_restore/eval2_e2e_v12_restore_nms_x0_staff0"
    
    # To get staff masks, we can use the `staff_mask.png` generated in the baseline run
    # For `debug_3_staff.png`, we might need to look into hybrid_pipeline_bench, but let's start with `staff_mask.png`
    # or `page_0XX_staff_mask.png`.
    
    # Let's load the fp_out_of_staff list from trace_examples.csv
    import csv
    fp_csv = root_dir / "logs/issue120_e2e_recovery/staff_region_filter_investigation/trace_examples.csv"
    fp_list = []
    if fp_csv.exists():
        with open(fp_csv, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    box = json.loads(row["bbox"])
                    fp_list.append({"score": row["score"], "page": row["page"], "box": box})
                except:
                    pass
    
    logger.info(f"Loaded {len(fp_list)} fp_out_of_staff examples")

    # Load GTs
    gt_stats = {"total": 0, "dropped": 0}
    
    # We need to find the staff mask for each page.
    # In `eval2_full_v12_restore_h25_th08_{score}/baseline/batch/{page}/{page}_staff_mask.png`
    
    all_scores = [d.name for d in eval2_dir.iterdir() if d.is_dir()]
    
    param_grid = [
        {"scan_width_ratio": 0.2, "vov_threshold": v, "gap_tolerance": g, "min_height": 20, "line_ratio_thresh": 0.05}
        for v in [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]
        for g in [20, 30, 40, 50]
    ]
    results = { i: {"gt_dropped": 0, "fp_dropped": 0} for i in range(len(param_grid)) }
    gt_total = 0
    fp_total = len(fp_list)

    # Step 1: Evaluate GTs
    for score in all_scores:
        score_dir = eval2_dir / score
        
        # group GTs by page
        page_to_gts = {}
        for page_dir in score_dir.iterdir():
            if not page_dir.is_dir():
                continue
            boxes_file = page_dir / "boxes_sorted.json"
            if not boxes_file.exists():
                continue
            try:
                gts = json.loads(boxes_file.read_text())
                page_to_gts[page_dir.name] = []
                for gt in gts:
                    if isinstance(gt, dict) and "barline_location" in gt:
                        page_to_gts[page_dir.name].append(gt["barline_location"])
            except Exception as e:
                pass
            
        mask_root = root_dir / f"logs/hybrid_generalization/verification_full_v12_restore/eval2_full_v12_restore_h25_th08_{score}/baseline/batch"
        for page, boxes in page_to_gts.items():
            mask_path = mask_root / page / f"{page}_staff_mask.png"
            if not mask_path.exists():
                mask_path = mask_root / page / page / f"{page}_proxy_debug_3_staff.png"
                if not mask_path.exists():
                    continue
            
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask is None:
                continue
            
            gt_total += len(boxes)
            for i, p in enumerate(param_grid):
                kept, dropped = filter_by_local_staff_overlap(boxes, mask, **p)
                results[i]["gt_dropped"] += len(dropped)

    # Step 2: Evaluate FPs
    # Group FPs by page to load masks efficiently
    page_to_fps = {}
    for item in fp_list:
        score = item["score"]
        page = item["page"]
        box = item["box"]
        key = (score, page)
        if key not in page_to_fps:
            page_to_fps[key] = []
        page_to_fps[key].append(box)

    for (score, page), boxes in page_to_fps.items():
        mask_root = root_dir / f"logs/hybrid_generalization/verification_full_v12_restore/eval2_full_v12_restore_h25_th08_{score}/baseline/batch"
        mask_path = mask_root / page / f"{page}_staff_mask.png"
        if not mask_path.exists():
            continue
            
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            continue
            
        for i, p in enumerate(param_grid):
            kept, dropped = filter_by_local_staff_overlap(boxes, mask, **p)
            results[i]["fp_dropped"] += len(dropped)

    # Summarize results
    logger.info(f"Total GT: {gt_total}, Total FP out of staff: {fp_total}")
    logger.info(f"Results with GT drops == 0:")
    
    safe_results = []
    for i, res in results.items():
        if res["gt_dropped"] == 0:
            safe_results.append((res["fp_dropped"], param_grid[i]))
            
    # Sort by fp_dropped descending
    safe_results.sort(key=lambda x: x[0], reverse=True)
    
    for fp_dr, p in safe_results[:10]:
        logger.info(f"  FP dropped: {fp_dr}/{fp_total} | params: vov={p['vov_threshold']}, gap={p['gap_tolerance']}")
    
    if not safe_results:
        logger.info("No parameter combinations were count-safe (0 GT drops)!")

if __name__ == "__main__":
    main()
