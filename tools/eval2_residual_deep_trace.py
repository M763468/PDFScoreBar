#!/usr/bin/env python3
"""Archived Issue 120 residual trace utility.

This script was added after the main Issue 120 probe-scan experiment to preserve
the ad-hoc residual tracing procedure that produced
``logs/issue120_final_residuals/residual_trace.csv`` and crop images. It is kept
for provenance and visual follow-up, not as the canonical detector evaluation
harness. Prefer ``tools/issue120_targeted_residual_replay.py`` for new targeted
residual verification.
"""

import csv
import json
import re
from pathlib import Path

import cv2


def get_box(c):
    if isinstance(c, dict):
        return c.get("box", c.get("bbox", c))
    return c


def iou(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def find_best_match(box, others, dist_tol=20):
    best_iou = 0
    best_item = None
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0

    for item in others:
        ob = get_box(item)
        if not isinstance(ob, list) or len(ob) != 4:
            continue
        ocx = (ob[0] + ob[2]) / 2.0
        ocy = (ob[1] + ob[3]) / 2.0

        if abs(cx - ocx) < dist_tol and abs(cy - ocy) < 100:
            val = iou(box, ob)
            if val > best_iou:
                best_iou = val
                best_item = item
            elif best_iou == 0:
                best_item = item
                best_iou = 0.001
    return best_item, best_iou


def trace_fn(gt_box, score, page_id, run_root):
    page_data_root = run_root / score / "intermediate" / "probe_scan" / f"eval2_{score}_{page_id}"
    layers = [
        ("candidates", page_data_root / "pipeline2_no_peak_candidates.json"),
        ("scored", page_data_root / "pipeline2_no_peak_scored.json"),
        ("filtered", page_data_root / "pipeline2_no_peak_filtered_cnn.json"),
    ]

    history = {}
    for name, path in layers:
        if not path.exists():
            history[name] = "Layer missing"
            continue
        with open(path) as f:
            data = json.load(f)
        match, match_iou = find_best_match(gt_box, data)
        history[name] = {"match": match, "iou": match_iou}

    if history.get("candidates") == "Layer missing" or (
        isinstance(history.get("candidates"), dict) and history["candidates"]["iou"] < 0.0001
    ):
        return "seed_miss_or_probe_reject", history
    if history.get("scored") == "Layer missing" or (
        isinstance(history.get("scored"), dict) and history["scored"]["iou"] < 0.0001
    ):
        return "scoring_error", history
    scored_match = history["scored"]["match"]
    if isinstance(scored_match, dict) and scored_match.get("score", 0) < 0.5:
        return "cnn_low_score", history
    if history.get("filtered") == "Layer missing" or (
        isinstance(history.get("filtered"), dict) and history["filtered"]["iou"] < 0.0001
    ):
        return "geometric_filter_reject", history
    return "unknown_post_filter", history


def visualize_residual(img, box, others, out_path, label_box="GT"):
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    y1, y2 = max(0, cy - 200), min(img.shape[0], cy + 200)
    x1, x2 = max(0, cx - 250), min(img.shape[1], cx + 250)

    crop = img[y1:y2, x1:x2].copy()
    if len(crop.shape) == 2:
        crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)

    for o in others:
        ob = get_box(o)
        if not isinstance(ob, list) or len(ob) != 4:
            continue
        # Draw neighbors in Cyan
        cv2.rectangle(crop, (ob[0] - x1, ob[1] - y1), (ob[2] - x1, ob[3] - y1), (255, 255, 0), 1)

    color = (0, 0, 255) if label_box == "GT" else (0, 255, 0)
    cv2.rectangle(crop, (box[0] - x1, box[1] - y1), (box[2] - x1, box[3] - y1), color, 2)
    cv2.putText(crop, f"{label_box}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.imwrite(str(out_path), crop)


scores = [
    "Shostakovich-Festival_Overture_Va",
    "Shostakovich-Sym5-Va",
    "Sibelius-Violin_Concerto-Viola",
    "Va_Prokofiev_Symphony1",
    "Va__Prokofiev_Symphony5",
]
run_root = Path("logs/full_pipeline_runs/issue120_final_v1")
out_dir = Path("logs/issue120_final_residuals")
out_dir.mkdir(exist_ok=True)
vis_dir = out_dir / "visuals"
vis_dir.mkdir(exist_ok=True)

residual_list = []

for score in scores:
    score_dir = run_root / score
    if not score_dir.exists():
        continue
    probe_scan_dir = score_dir / "intermediate" / "probe_scan"
    if not probe_scan_dir.exists():
        continue

    for page_dir in sorted(probe_scan_dir.iterdir()):
        if not page_dir.is_dir():
            continue
        m = re.search(r"page_(\d+)", page_dir.name)
        if not m:
            continue
        page_id = f"page_{m.group(1)}"
        pred_json = page_dir / "pipeline2_no_peak_filtered_cnn.json"
        gt_json = Path(f"data/evaluation2/annotations/{score}/{page_id}/boxes_sorted.json")
        img_path = Path(f"data/evaluation2/images/{score}/{page_id}.png")
        if not pred_json.exists() or not gt_json.exists():
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        with open(pred_json) as f:
            preds = json.load(f)
        with open(gt_json) as f:
            gts = json.load(f)

        pred_boxes = [get_box(c) for c in preds]
        gt_boxes = [g["barline_location"] for g in gts if "barline_location" in g]

        matched_gt = set()
        matched_pred = set()
        for pi, pb in enumerate(pred_boxes):
            pcx = (pb[0] + pb[2]) / 2.0
            pcy = (pb[1] + pb[3]) / 2.0
            for gi, gb in enumerate(gt_boxes):
                if gi in matched_gt:
                    continue
                gcx = (gb[0] + gb[2]) / 2.0
                gcy = (gb[1] + gb[3]) / 2.0
                if abs(pcx - gcx) < 20 and abs(pcy - gcy) < 60:
                    matched_gt.add(gi)
                    matched_pred.add(pi)
                    break

        for gi, gb in enumerate(gt_boxes):
            if gi not in matched_gt:
                reason, _trace = trace_fn(gb, score, page_id, run_root)
                res_id = f"FN_{score}_{page_id}_gt{gi}"
                visualize_residual(img, gb, pred_boxes, vis_dir / f"{res_id}.png", "GT")
                residual_list.append(
                    {
                        "type": "FN",
                        "score": score,
                        "page": page_id,
                        "id": gi,
                        "bbox": gb,
                        "reason": reason,
                        "vis": f"visuals/{res_id}.png",
                    }
                )

        for pi, pb in enumerate(pred_boxes):
            if pi not in matched_pred:
                res_id = f"FP_{score}_{page_id}_pred{pi}"
                visualize_residual(img, pb, gt_boxes, vis_dir / f"{res_id}.png", "FP")
                residual_list.append(
                    {
                        "type": "FP",
                        "score": score,
                        "page": page_id,
                        "id": pi,
                        "bbox": pb,
                        "reason": "survived_all",
                        "vis": f"visuals/{res_id}.png",
                    }
                )

with open(out_dir / "residual_trace.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["type", "score", "page", "id", "bbox", "reason", "vis"])
    writer.writeheader()
    writer.writerows(residual_list)
print(f"Deep trace complete. Total residuals: {len(residual_list)}")
