#!/usr/bin/env python3
import argparse
import csv
import json
import random
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm


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


def center_crop(img, cx, cy, crop_w, crop_h):
    w_half = crop_w // 2
    h_half = crop_h // 2
    cy1 = max(0, cy - h_half)
    cy2 = min(img.shape[0], cy + h_half)
    cx1 = max(0, cx - w_half)
    cx2 = min(img.shape[1], cx + w_half)
    crop = img[cy1:cy2, cx1:cx2]
    if crop.shape[0] < crop_h or crop.shape[1] < crop_w:
        pad_y1 = h_half - (cy - cy1)
        pad_y2 = h_half - (cy2 - cy)
        pad_x1 = w_half - (cx - cx1)
        pad_x2 = w_half - (cx2 - cx)
        crop = cv2.copyMakeBorder(
            crop,
            pad_y1,
            pad_y2,
            pad_x1,
            pad_x2,
            cv2.BORDER_CONSTANT,
            value=[255, 255, 255],
        )
    return crop


def load_palette_index(seg_path: Path) -> np.ndarray:
    seg_img = Image.open(seg_path)
    if seg_img.mode != "P":
        seg_img = seg_img.convert("P")
    return np.array(seg_img)


def find_components(mask: np.ndarray):
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    comps = []
    for idx in range(1, num):
        x, y, w, h, area = stats[idx].tolist()
        comps.append(
            {
                "label": idx,
                "bbox": [x, y, x + w - 1, y + h - 1],
                "w": w,
                "h": h,
                "area": area,
            }
        )
    return comps


def crop_size_from_bbox(
    box,
    scale,
    aspect_ratio,
    min_h,
    max_h,
    min_w,
    max_w,
):
    x1, y1, x2, y2 = box
    bbox_h = max(1.0, abs(y2 - y1))
    crop_h = int(round(bbox_h * scale))
    crop_h = max(min_h, min(max_h, crop_h))
    crop_w = int(round(crop_h * aspect_ratio))
    crop_w = max(min_w, min(max_w, crop_w))
    return crop_w, crop_h


def extract_local_tp_fp(
    repo_root,
    output_root,
    crop_w,
    crop_h,
    iou_threshold,
    crop_scale,
    min_crop_h,
    max_crop_h,
    predictions_root=None,
    candidate_filename="geom_kept.json",
):
    tp_dir = output_root / "local" / "tp"
    fp_dir = output_root / "local" / "fp"
    tp_dir.mkdir(parents=True, exist_ok=True)
    fp_dir.mkdir(parents=True, exist_ok=True)

    scale = crop_scale
    aspect_ratio = crop_w / crop_h
    min_h = min_crop_h
    max_h = max_crop_h
    min_w = max(16, int(round(min_h * aspect_ratio)))
    max_w = max(32, int(round(max_h * aspect_ratio)))

    tp_count = 0
    fp_count = 0
    for page in DEFAULT_PAGES:
        image_path = repo_root / page["image"]
        gt_path = repo_root / page["gt"]
        # preds_path unused if predictions_root is provided
        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
        with gt_path.open("r") as f:
            gt_data = json.load(f)
        gt_boxes = [entry["barline_location"] for entry in gt_data]

        gt_boxes = [entry["barline_location"] for entry in gt_data]

        for i, box in enumerate(tqdm(gt_boxes, desc=f"{page['name']} GT", leave=False)):
            x1, y1, x2, y2 = box
            cx = int(round((x1 + x2) / 2))
            cy = int(round((y1 + y2) / 2))
            local_w, local_h = crop_size_from_bbox(
                box,
                scale,
                aspect_ratio,
                min_h,
                max_h,
                min_w,
                max_w,
            )
            crop = center_crop(img, cx, cy, local_w, local_h)
            save_path = tp_dir / f"{page['name']}_tp_{i:05d}.png"
            cv2.imwrite(str(save_path), crop)
            tp_count += 1

        if predictions_root:
            # Load candidates from logs
            filename = candidate_filename.replace("{page}", page["name"])
            
            cand_path = Path(predictions_root) / "per_page" / page["name"] / filename
            if not cand_path.exists():
                cand_path = Path(predictions_root) / page["name"] / filename

            if not cand_path.exists():
                print(f"Warning: Candidate file not found for {page['name']} at {cand_path}")
                continue
                
            with cand_path.open("r") as f:
                data = json.load(f)
            
            if isinstance(data, list):
                candidates = data
            elif isinstance(data, dict) and "scores" in data:
                candidates = [item["bbox"] for item in data["scores"]]
            else:
                print(f"Unknown JSON format in {candidate_filename}")
                candidates = []

            # Auto-detect scale mismatch REMOVED. 
            # Reason: Incompatible with pure FP files (fp_boxes.json) which have 0 overlap by definition.
            # Auto-scale logic would find 0 matches at scale 1.0 and pick random scales that have accidental overlap.
            # Reverting to fixed scale (assume 1.0 for fp_boxes.json as in v2).
            best_scale = 1.0
            
            # Filter matches: if candidate overlaps GT, it's a TP (already handled above), so skip.
            # Only keep non-matching candidates as FP (Hard Negatives).
            fp_candidates = []
            for raw_cand in candidates:
                cand = [x * best_scale for x in raw_cand] # Apply scale (1.0)
                is_match = False
                for gt_box in gt_boxes:
                    iou = barline_iou(gt_box, cand)
                    if iou > iou_threshold: 
                        is_match = True
                        break
                if not is_match:
                    fp_candidates.append(cand)
            
            for idx, box in enumerate(tqdm(fp_candidates, desc=f"{page['name']} FP", leave=False)):
                x1, y1, x2, y2 = box
                cx = int(round((x1 + x2) / 2))
                cy = int(round((y1 + y2) / 2))
                local_w, local_h = crop_size_from_bbox(
                    box,
                    scale,
                    aspect_ratio,
                    min_h,
                    max_h,
                    min_w,
                    max_w,
                )
                crop = center_crop(img, cx, cy, local_w, local_h)
                save_path = fp_dir / f"{page['name']}_fp_{idx:05d}.png"
                cv2.imwrite(str(save_path), crop)
                fp_count += 1

        else:
            # Fallback to dynamic FP generation (legacy)
            preds_path = repo_root / page["preds"]
            with preds_path.open("r") as f:
                pred_boxes = json.load(f)
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
            for idx in tqdm(fp_indices, desc=f"{page['name']} FP-Legacy", leave=False):
                box = pred_boxes[idx]
                x1, y1, x2, y2 = box
                cx = int(round((x1 + x2) / 2))
                cy = int(round((y1 + y2) / 2))
                local_w, local_h = crop_size_from_bbox(
                    box,
                    scale,
                    aspect_ratio,
                    min_h,
                    max_h,
                    min_w,
                    max_w,
                )
                crop = center_crop(img, cx, cy, local_w, local_h)
                save_path = fp_dir / f"{page['name']}_fp_{idx:05d}.png"
                cv2.imwrite(str(save_path), crop)
                fp_count += 1

    return tp_count, fp_count


def find_latest_gt(page_dir: Path) -> Path | None:
    preferred = page_dir / "boxes_sorted_v20260106.json"
    if preferred.exists():
        return preferred
    fallback = page_dir / "boxes_sorted.json"
    if fallback.exists():
        return fallback
    return None


def load_eval2_pages(annotations_root: Path):
    pages = []
    for score_dir in sorted(annotations_root.iterdir()):
        if not score_dir.is_dir():
            continue
        for page_dir in sorted(score_dir.iterdir()):
            if not page_dir.is_dir():
                continue
            gt_path = find_latest_gt(page_dir)
            if not gt_path:
                continue
            pages.append(
                {
                    "score": score_dir.name,
                    "page": page_dir.name,
                    "gt": gt_path,
                }
            )
    return pages


def extract_eval2_tp_fp(
    repo_root,
    output_root,
    crop_w,
    crop_h,
    iou_threshold,
    crop_scale,
    min_crop_h,
    max_crop_h,
    annotations_root,
    images_root,
    candidates_root,
    candidate_filename,
):
    tp_dir = output_root / "eval2" / "tp"
    fp_dir = output_root / "eval2" / "fp"
    tp_dir.mkdir(parents=True, exist_ok=True)
    fp_dir.mkdir(parents=True, exist_ok=True)

    scale = crop_scale
    aspect_ratio = crop_w / crop_h
    min_h = min_crop_h
    max_h = max_crop_h
    min_w = max(16, int(round(min_h * aspect_ratio)))
    max_w = max(32, int(round(max_h * aspect_ratio)))

    tp_count = 0
    fp_count = 0
    pages = load_eval2_pages(annotations_root)
    for page in pages:
        score = page["score"]
        page_name = page["page"]
        image_path = images_root / score / f"{page_name}.png"
        if not image_path.exists():
            print(f"Warning: eval2 image not found: {image_path}")
            continue
        img = cv2.imread(str(image_path))
        if img is None:
            print(f"Warning: eval2 image failed to load: {image_path}")
            continue
        with page["gt"].open("r") as f:
            gt_data = json.load(f)
        try:
            gt_boxes = normalize_gt_boxes(gt_data)
        except ValueError as exc:
            print(f"Warning: {page['gt']} - {exc}")
            continue

        for i, box in enumerate(
            tqdm(gt_boxes, desc=f"{score}/{page_name} GT", leave=False)
        ):
            x1, y1, x2, y2 = box
            cx = int(round((x1 + x2) / 2))
            cy = int(round((y1 + y2) / 2))
            local_w, local_h = crop_size_from_bbox(
                box,
                scale,
                aspect_ratio,
                min_h,
                max_h,
                min_w,
                max_w,
            )
            crop = center_crop(img, cx, cy, local_w, local_h)
            save_path = tp_dir / f"{score}_{page_name}_tp_{i:05d}.png"
            cv2.imwrite(str(save_path), crop)
            tp_count += 1

        run_dir = candidates_root / f"eval2_{score}_{page_name}"
        cand_path = run_dir / candidate_filename
        if not cand_path.exists():
            print(f"Warning: eval2 candidate file not found: {cand_path}")
            continue

        with cand_path.open("r") as f:
            data = json.load(f)
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict) and "scores" in data:
            candidates = [item["bbox"] for item in data["scores"]]
        else:
            print(f"Unknown JSON format in {cand_path}")
            candidates = []

        fp_candidates = []
        for raw_cand in candidates:
            cand = [x * 1.0 for x in raw_cand]
            is_match = False
            for gt_box in gt_boxes:
                iou = barline_iou(gt_box, cand)
                if iou > iou_threshold:
                    is_match = True
                    break
            if not is_match:
                fp_candidates.append(cand)

        for idx, box in enumerate(
            tqdm(fp_candidates, desc=f"{score}/{page_name} FP", leave=False)
        ):
            x1, y1, x2, y2 = box
            cx = int(round((x1 + x2) / 2))
            cy = int(round((y1 + y2) / 2))
            local_w, local_h = crop_size_from_bbox(
                box,
                scale,
                aspect_ratio,
                min_h,
                max_h,
                min_w,
                max_w,
            )
            crop = center_crop(img, cx, cy, local_w, local_h)
            save_path = fp_dir / f"{score}_{page_name}_fp_{idx:05d}.png"
            cv2.imwrite(str(save_path), crop)
            fp_count += 1

    return tp_count, fp_count


def normalize_gt_boxes(gt_data):
    if isinstance(gt_data, list):
        if not gt_data:
            return []
        first = gt_data[0]
        if isinstance(first, dict):
            if "barline_location" in first:
                return [entry["barline_location"] for entry in gt_data]
            if "bbox" in first:
                return [entry["bbox"] for entry in gt_data]
        if isinstance(first, (list, tuple)) and len(first) == 4:
            return gt_data
    if isinstance(gt_data, dict):
        if "boxes" in gt_data:
            return gt_data["boxes"]
        if "annotations" in gt_data:
            return [
                entry["barline_location"]
                for entry in gt_data["annotations"]
                if "barline_location" in entry
            ]
    raise ValueError("Unknown GT format for evaluation2")


def load_staff_boxes_by_filename(ds_root: Path):
    staff_map = {}
    for split_name in ("deepscores_train.json", "deepscores_test.json"):
        json_path = ds_root / split_name
        if not json_path.exists():
            continue
        with json_path.open("r") as f:
            data = json.load(f)
        staff_ids = {
            cid for cid, c in data.get("categories", {}).items() if c.get("name") == "staff"
        }
        if not staff_ids:
            continue
        images = {str(img["id"]): img for img in data.get("images", [])}
        annotations = data.get("annotations", {})
        for img_id, img in images.items():
            ann_ids = img.get("ann_ids", [])
            staff_boxes = []
            for ann_id in ann_ids:
                ann = annotations.get(str(ann_id))
                if not ann:
                    continue
                cat_ids = ann.get("cat_id", [])
                if any(cid in staff_ids for cid in cat_ids):
                    x1, y1, x2, y2 = ann["a_bbox"]
                    staff_boxes.append(
                        (int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))
                    )
            if staff_boxes:
                staff_map[img["filename"]] = staff_boxes
    return staff_map


def expand_boxes_to_staff_boxes(boxes, staff_boxes, img_h):
    if not staff_boxes:
        return list(boxes)
    staff_centers = [(y1 + y2) / 2.0 for _, y1, _, y2 in staff_boxes]
    expanded = []
    for x1, y1, x2, y2 in boxes:
        cy = (y1 + y2) / 2.0
        best_idx = None
        for idx, (_, sy1, _, sy2) in enumerate(staff_boxes):
            if sy1 <= cy <= sy2:
                best_idx = idx
                break
        if best_idx is None:
            dists = [abs(cy - c) for c in staff_centers]
            best_idx = int(np.argmin(dists))
        _, sy1, _, sy2 = staff_boxes[best_idx]
        sy1 = max(0, sy1)
        sy2 = min(img_h - 1, sy2)
        expanded.append((x1, sy1, x2, sy2))
    return expanded


def extract_deepscores_probe_fp(
    ds_root,
    output_root,
    crop_w,
    crop_h,
    iou_threshold,
    crop_scale,
    min_crop_h,
    max_crop_h,
    tp_palette_index,
    tp_min_area,
    tp_min_height,
    max_total,
    seg_offset,
    seg_count,
):
    from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan

    fp_dir = output_root / "deepscores_probe" / "fp"
    fp_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(fp_dir.glob("*.png")))
    if max_total is not None and existing >= max_total:
        return existing

    scale = crop_scale
    aspect_ratio = crop_w / crop_h
    min_h = min_crop_h
    max_h = max_crop_h
    min_w = max(16, int(round(min_h * aspect_ratio)))
    max_w = max(32, int(round(max_h * aspect_ratio)))

    seg_root = ds_root / "segmentation"
    img_root = ds_root / "images"
    seg_files = sorted(seg_root.glob("*_seg.png"))
    if seg_offset:
        seg_files = seg_files[seg_offset:]
    if seg_count:
        seg_files = seg_files[:seg_count]

    staff_boxes_by_name = load_staff_boxes_by_filename(ds_root)

    total = existing
    for seg_path in tqdm(seg_files, desc="DeepScores probe FP"):
        if max_total is not None and total >= max_total:
            break
        seg_np = load_palette_index(seg_path)
        mask = (seg_np == tp_palette_index).astype(np.uint8) * 255
        comps = find_components(mask)
        tp_boxes = []
        for comp in comps:
            if comp["area"] < tp_min_area:
                continue
            if comp["h"] < tp_min_height:
                continue
            x1, y1, x2, y2 = comp["bbox"]
            tp_boxes.append((x1, y1, x2, y2))
        if not tp_boxes:
            continue

        image_name = seg_path.name.replace("_seg.png", ".png")
        image_path = img_root / image_name
        img = cv2.imread(str(image_path))
        if img is None:
            continue

        staff_boxes = staff_boxes_by_name.get(image_name)
        if not staff_boxes:
            continue

        staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        candidates = detect_probe_scan(
            base_img=img,
            staff_mask=staff_mask,
            existing_boxes=tp_boxes,
            band_source="row_stats",
            scan_x_peak_rescue=True,
            scan_rightmost_rescue=True,
            divisi_rescue=True,
            scan_x_peak_rescue_mode="topbottom",
            probe_width=4,
            ink_threshold=200,
            min_ratio=0.50,
            scan_center_on_peak=True,
            scan_x_peak_ratio_min=0.0,
            scan_rightmost_min_ratio=0.10,
            max_per_band=0,
        )

        tp_boxes = expand_boxes_to_staff_boxes(tp_boxes, staff_boxes, img.shape[0])
        candidates = expand_boxes_to_staff_boxes(candidates, staff_boxes, img.shape[0])

        fp_boxes = []
        for cand in candidates:
            is_match = False
            for gt_box in tp_boxes:
                iou = barline_iou(gt_box, cand)
                if iou > iou_threshold:
                    is_match = True
                    break
            if not is_match:
                fp_boxes.append(cand)

        for idx, box in enumerate(fp_boxes):
            if max_total is not None and total >= max_total:
                break
            x1, y1, x2, y2 = box
            cx = int(round((x1 + x2) / 2))
            cy = int(round((y1 + y2) / 2))
            local_w, local_h = crop_size_from_bbox(
                box,
                scale,
                aspect_ratio,
                min_h,
                max_h,
                min_w,
                max_w,
            )
            crop = center_crop(img, cx, cy, local_w, local_h)
            save_path = fp_dir / f"{seg_path.stem}_fp_{idx:05d}.png"
            if not save_path.exists():
                cv2.imwrite(str(save_path), crop)
                total += 1

    return total

def category_matches(name, prefixes, names):
    if name in names:
        return True
    return any(name.startswith(prefix) for prefix in prefixes)


def extract_deepscores_negatives(
    ds_root,
    output_root,
    crop_w,
    crop_h,
    prefixes,
    names,
    max_per_image,
    max_total,
    seed,
):
    output_dir = output_root / "deepscores" / "fp"
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.png")))
    if max_total is not None and existing >= max_total:
        return existing

    rng = random.Random(seed)
    total = existing
    for split_name in ["deepscores_train.json", "deepscores_test.json"]:
        json_path = ds_root / split_name
        with json_path.open("r") as f:
            data = json.load(f)
        categories = data["categories"]
        cat_id_to_name = {str(k): v["name"] for k, v in categories.items()}

        images = {str(img["id"]): img for img in data["images"]}
        annotations = data["annotations"]

        annotations = data["annotations"]

        for img_id, img_info in tqdm(images.items(), desc=f"Scanning {split_name}"):
            if max_total is not None and total >= max_total:
                return total
            ann_ids = img_info.get("ann_ids", [])
            candidates = []
            for ann_id in ann_ids:
                ann = annotations.get(str(ann_id))
                if not ann:
                    continue
                cat_ids = ann.get("cat_id", [])
                for cat_id in cat_ids:
                    name = cat_id_to_name.get(str(cat_id))
                    if name and category_matches(name, prefixes, names):
                        candidates.append(ann)
                        break
            if not candidates:
                continue
            rng.shuffle(candidates)
            if max_per_image is not None:
                candidates = candidates[:max_per_image]

            image_path = ds_root / "images" / img_info["filename"]
            img = cv2.imread(str(image_path))
            if img is None:
                continue
            for ann in candidates:
                if max_total is not None and total >= max_total:
                    return total
                x1, y1, x2, y2 = ann["a_bbox"]
                cx = int(round((x1 + x2) / 2))
                cy = int(round((y1 + y2) / 2))
                crop = center_crop(img, cx, cy, crop_w, crop_h)
                save_path = output_dir / f"{split_name.replace('.json','')}_{img_id}_{ann['comments'].split(';')[0]}.png"
                if not save_path.exists():
                    cv2.imwrite(str(save_path), crop)
                    total += 1
    return total


def extract_deepscores_tp_from_segmentation(
    ds_root,
    output_root,
    crop_w,
    crop_h,
    palette_index,
    min_area,
    min_height,
    max_total,
    seg_offset,
    seg_count,
):
    output_dir = output_root / "deepscores" / "tp"
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.png")))
    if max_total is not None and existing >= max_total:
        return existing

    total = existing
    seg_root = ds_root / "segmentation"
    img_root = ds_root / "images"
    seg_files = sorted(seg_root.glob("*_seg.png"))
    if seg_offset:
        seg_files = seg_files[seg_offset:]
    if seg_count:
        seg_files = seg_files[:seg_count]
    for seg_path in tqdm(seg_files, desc="Scanning DeepScores Seg"):
        if max_total is not None and total >= max_total:
            break
        seg_np = load_palette_index(seg_path)
        mask = (seg_np == palette_index).astype(np.uint8) * 255
        comps = find_components(mask)
        for comp in comps:
            if max_total is not None and total >= max_total:
                break
            if comp["area"] < min_area:
                continue
            if comp["h"] < min_height:
                continue
            # Logic for vertical_ratio check removed as per user request to relax filters
            x1, y1, x2, y2 = comp["bbox"]
            cx = int(round((x1 + x2) / 2))
            cy = int(round((y1 + y2) / 2))
            # match segmentation filename to image filename
            image_name = seg_path.name.replace("_seg.png", ".png")
            image_path = img_root / image_name
            img = cv2.imread(str(image_path))
            if img is None:
                continue
            crop = center_crop(img, cx, cy, crop_w, crop_h)
            save_path = output_dir / (
                f"{seg_path.stem}_idx{comp['label']}_x{x1}_y{y1}.png"
            )
            if not save_path.exists():
                cv2.imwrite(str(save_path), crop)
                total += 1
    return total


def build_samples(output_root):
    samples = []
    local_tp = sorted((output_root / "local" / "tp").glob("*.png"))
    local_fp = sorted((output_root / "local" / "fp").glob("*.png"))
    eval2_tp = sorted((output_root / "eval2" / "tp").glob("*.png"))
    eval2_fp = sorted((output_root / "eval2" / "fp").glob("*.png"))
    ds_fp = sorted((output_root / "deepscores" / "fp").glob("*.png"))
    ds_tp = sorted((output_root / "deepscores" / "tp").glob("*.png"))
    ds_probe_fp = sorted((output_root / "deepscores_probe" / "fp").glob("*.png"))

    for path in local_tp:
        group = path.name.split("_tp_")[0]
        samples.append(
            {"path": path, "label": 1, "source": "local", "group": group}
        )
    for path in local_fp:
        group = path.name.split("_fp_")[0]
        samples.append(
            {"path": path, "label": 0, "source": "local", "group": group}
        )
    for path in eval2_tp:
        group = path.name.split("_tp_")[0]
        samples.append(
            {"path": path, "label": 1, "source": "eval2", "group": group}
        )
    for path in eval2_fp:
        group = path.name.split("_fp_")[0]
        samples.append(
            {"path": path, "label": 0, "source": "eval2", "group": group}
        )
    for path in ds_fp:
        parts = path.stem.split("_")
        group = parts[2] if len(parts) > 2 else path.stem
        samples.append(
            {"path": path, "label": 0, "source": "deepscores", "group": group}
        )
    for path in ds_probe_fp:
        parts = path.stem.split("_")
        group = parts[2] if len(parts) > 2 else path.stem
        samples.append(
            {"path": path, "label": 0, "source": "deepscores_probe", "group": group}
        )
    for path in ds_tp:
        parts = path.stem.split("_")
        group = parts[2] if len(parts) > 2 else path.stem
        samples.append(
            {"path": path, "label": 1, "source": "deepscores", "group": group}
        )
    return samples


def assign_splits(samples, ratios, seed):
    rng = random.Random(seed)
    group_to_samples = {}
    for sample in samples:
        group_to_samples.setdefault(sample["group"], []).append(sample)

    groups = list(group_to_samples.keys())
    rng.shuffle(groups)

    split_targets = {k: int(len(samples) * v) for k, v in ratios.items()}
    split_counts = {k: 0 for k in ratios}
    split_groups = {k: [] for k in ratios}

    def split_score(split_key):
        target = split_targets.get(split_key, 1)
        if target == 0:
            return split_counts[split_key]
        return split_counts[split_key] / target

    groups_sorted = sorted(groups, key=lambda g: len(group_to_samples[g]), reverse=True)
    for group in groups_sorted:
        split_key = min(split_counts.keys(), key=split_score)
        split_groups[split_key].append(group)
        split_counts[split_key] += len(group_to_samples[group])

    assignments = {}
    for split_key, groups_in_split in split_groups.items():
        for group in groups_in_split:
            for sample in group_to_samples[group]:
                assignments[sample["path"]] = split_key
    return assignments


def link_or_copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    # Always copy to avoid symlink issues
    try:
        shutil.copy2(src, dst)
    except Exception as e:
        print(f"Error copying {src} to {dst}: {e}")


def write_outputs(output_root, samples, assignments):
    splits_root = output_root / "splits"
    metadata_dir = output_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    split_dirs = {}
    for split in sorted(set(assignments.values())):
        split_dirs[split] = {
            1: splits_root / split / "tp",
            0: splits_root / split / "fp",
        }

    rows = []
    for idx, sample in enumerate(tqdm(samples, desc="Writing Samples")):
        split = assignments[sample["path"]]
        label = sample["label"]
        suffix = sample["path"].suffix
        sample_id = f"{sample['source']}_{sample['group']}_{idx:06d}{suffix}"
        dst = split_dirs[split][label] / sample_id
        link_or_copy(sample["path"], dst)
        rows.append(
            {
                "sample_id": sample_id,
                "path": str(sample["path"]),
                "label": label,
                "source": sample["source"],
                "group": sample["group"],
                "split": split,
            }
        )

    csv_path = metadata_dir / "samples.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["sample_id", "path", "label", "source", "group", "split"]
        )
        writer.writeheader()
        writer.writerows(rows)

    stats = {}
    for split in split_dirs:
        stats[split] = {
            "tp": len(list((splits_root / split / "tp").glob("*.png"))),
            "fp": len(list((splits_root / split / "fp").glob("*.png"))),
        }
    stats_path = metadata_dir / "stats.json"
    with stats_path.open("w") as f:
        json.dump(stats, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Build CNN classifier dataset (local TP/FP + DeepScores negatives)."
    )
    parser.add_argument(
        "--output-root",
        default="/mnt/d/datasets/cnn_classifier_v1",
        help="Output dataset root.",
    )
    parser.add_argument(
        "--deepscores-root",
        default="/mnt/d/datasets/DeepScoresV2/ds2_dense",
        help="DeepScores V2 Dense root.",
    )
    parser.add_argument(
        "--predictions-root",
        type=Path,
        help="Path to the root of the predictions logs (e.g. logs/gt_rebuild_hybrid_eval/...) containing per_page/{page}/fp_boxes.json. If provided, explicit FP boxes are used.",
    )
    parser.add_argument(
        "--fp-source-file",
        type=str,
        default="geom_kept.json",
        help="Filename in the predictions-root/per_page/{page}/ directory to load as FP candidates (default: geom_kept.json). GT subtraction is applied.",
    )
    parser.add_argument("--crop-width", type=int, default=128)
    parser.add_argument("--crop-height", type=int, default=256)
    parser.add_argument(
        "--crop-scale",
        type=float,
        default=3.0,
        help="Scale factor for bbox height to derive crop height.",
    )
    parser.add_argument("--min-crop-height", type=int, default=48)
    parser.add_argument("--max-crop-height", type=int, default=256)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-per-image", type=int, default=5)
    parser.add_argument("--max-total", type=int, default=10000)
    parser.add_argument("--skip-local", action="store_true", help="Skip local TP/FP extraction.")
    parser.add_argument("--skip-eval2", action="store_true", help="Skip evaluation2 TP/FP extraction.")
    parser.add_argument("--skip-deepscores", action="store_true", help="Skip DeepScores extraction (TP+FP).")
    parser.add_argument("--skip-deepscores-fp", action="store_true", help="Skip DeepScores FP extraction.")
    parser.add_argument("--skip-deepscores-tp", action="store_true", help="Skip DeepScores TP extraction.")
    parser.add_argument(
        "--deepscores-probe-fp",
        action="store_true",
        help="Add DeepScores probe-scan FP extraction (hard negatives).",
    )
    parser.add_argument("--only-split", action="store_true", help="Only (re)build splits/metadata.")
    parser.add_argument(
        "--neg-prefix",
        action="append",
        default=["stem", "clef", "key", "accidental", "rest", "notehead", "beam"],
        help="Category name prefix to include as negatives (repeatable).",
    )
    parser.add_argument(
        "--neg-name",
        action="append",
        default=["ledgerLine", "legerLine"],
        help="Exact category name to include as negatives (repeatable).",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--tp-palette-index", type=int, default=3)
    parser.add_argument("--tp-min-area", type=int, default=30)
    parser.add_argument("--tp-min-height", type=int, default=30)
    parser.add_argument("--tp-vertical-ratio", type=float, default=3.0)
    parser.add_argument("--tp-max-total", type=int, default=None)
    parser.add_argument("--tp-seg-offset", type=int, default=0)
    parser.add_argument("--tp-seg-count", type=int, default=0)
    parser.add_argument(
        "--eval2-annotations-root",
        type=Path,
        default=Path("data/evaluation2/annotations"),
    )
    parser.add_argument(
        "--eval2-images-root",
        type=Path,
        default=Path("data/evaluation2/images"),
    )
    parser.add_argument(
        "--eval2-candidates-root",
        type=Path,
        default=Path("logs/hybrid_generalization"),
    )
    parser.add_argument(
        "--eval2-candidate-file",
        type=str,
        default="expanded_candidates_nopeak.json",
    )
    parser.add_argument(
        "--deepscores-probe-max-total",
        type=int,
        default=None,
        help="Max total crops for DeepScores probe-scan FP extraction.",
    )
    parser.add_argument(
        "--deepscores-probe-seg-offset",
        type=int,
        default=0,
        help="Segmentation offset for DeepScores probe FP scan.",
    )
    parser.add_argument(
        "--deepscores-probe-seg-count",
        type=int,
        default=0,
        help="Segmentation count for DeepScores probe FP scan.",
    )

    args = parser.parse_args()
    output_root = Path(args.output_root)
    repo_root = Path(__file__).resolve().parents[2]

    if not args.only_split:
        if not args.skip_local:
            tp_count, fp_count = extract_local_tp_fp(
                repo_root,
                output_root,
                args.crop_width,
                args.crop_height,
                args.iou_threshold,
                args.crop_scale,
                args.min_crop_height,
                args.max_crop_height,
                predictions_root=args.predictions_root,
                candidate_filename=args.fp_source_file,
            )
            print(f"Local crops: TP={tp_count}, FP={fp_count}")
        if not args.skip_eval2:
            tp_count, fp_count = extract_eval2_tp_fp(
                repo_root,
                output_root,
                args.crop_width,
                args.crop_height,
                args.iou_threshold,
                args.crop_scale,
                args.min_crop_height,
                args.max_crop_height,
                repo_root / args.eval2_annotations_root,
                repo_root / args.eval2_images_root,
                repo_root / args.eval2_candidates_root,
                args.eval2_candidate_file,
            )
            print(f"Eval2 crops: TP={tp_count}, FP={fp_count}")
        if not args.skip_deepscores and not args.skip_deepscores_fp:
            ds_count = extract_deepscores_negatives(
                Path(args.deepscores_root),
                output_root,
                args.crop_width,
                args.crop_height,
                args.neg_prefix,
                args.neg_name,
                args.max_per_image,
                args.max_total,
                args.seed,
            )
            print(f"DeepScores negatives: {ds_count}")
        if not args.skip_deepscores and not args.skip_deepscores_tp:
            tp_count = extract_deepscores_tp_from_segmentation(
                Path(args.deepscores_root),
                output_root,
                args.crop_width,
                args.crop_height,
                args.tp_palette_index,
                args.tp_min_area,
                args.tp_min_height,
                # args.tp_vertical_ratio removed
                args.tp_max_total,
                args.tp_seg_offset,
                args.tp_seg_count,
            )
            print(f"DeepScores TP (palette {args.tp_palette_index}): {tp_count}")
        if not args.skip_deepscores and args.deepscores_probe_fp:
            probe_count = extract_deepscores_probe_fp(
                Path(args.deepscores_root),
                output_root,
                args.crop_width,
                args.crop_height,
                args.iou_threshold,
                args.crop_scale,
                args.min_crop_height,
                args.max_crop_height,
                args.tp_palette_index,
                args.tp_min_area,
                args.tp_min_height,
                args.deepscores_probe_max_total,
                args.deepscores_probe_seg_offset,
                args.deepscores_probe_seg_count,
            )
            print(f"DeepScores probe FP: {probe_count}")

    samples = build_samples(output_root)
    ratios = {
        "train": args.train_ratio,
        "val": args.val_ratio,
        "test": args.test_ratio,
    }
    assignments = assign_splits(samples, ratios, args.seed)
    write_outputs(output_root, samples, assignments)
    print(f"Dataset built at: {output_root}")


if __name__ == "__main__":
    main()
