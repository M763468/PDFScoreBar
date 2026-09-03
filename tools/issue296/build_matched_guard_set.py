#!/usr/bin/env python3
"""Build the temporary Issue #296 matched guard set before solution tuning.

Diagnostic-only: delete this helper before PR preparation.
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from tools.cnn_classifier.score_candidates_batch import (
    DEVICE,
    GPUNormalize,
    IMG_SIZE,
    MEAN,
    STD,
    center_crop,
    crop_size_from_bbox,
    get_model,
)

ROOT = Path(__file__).resolve().parents[2]
GT_ROOT = ROOT / "data/evaluation2/annotations"
IMAGE_ROOT = ROOT / "data/evaluation2/images"
RUN_ROOT = ROOT / "logs/issue274_homr_unification_analysis/issue274_two_homr_full68_fresh_01"
OUT = ROOT / "logs/issue296/diagnostic_04_matched_guards"
CHECKPOINT = ROOT / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
TARGET_SCORE = "Va__Prokofiev_Symphony5"
TARGET_PAGE = "page_015"
TARGET = (580, 4005, 584, 4115)
CNN_THRESHOLD = 0.1
MULTI_TYPES = ("double_barline", "end_barline", "repeat")

STATIC_CASES = (
    ("benign_fp_p007_a", "benign_current_fp", "Va__Prokofiev_Symphony5", "page_007", (665, 908, 669, 1018), "negative", "current_canonical_issue291_residual"),
    ("benign_fp_p007_b", "benign_current_fp", "Va__Prokofiev_Symphony5", "page_007", (668, 908, 672, 1018), "negative", "current_canonical_issue291_residual"),
    ("current_fn_sibelius_p004", "current_fn_control", "Sibelius-Violin_Concerto-Viola", "page_004", (2713, 3166, 2720, 3274), "true_barline", "current_canonical_issue291_residual"),
    ("current_fn_prokofiev1_p004", "current_fn_control", "Va_Prokofiev_Symphony1", "page_004", (2715, 2481, 2720, 2582), "true_barline", "current_canonical_issue291_residual"),
    ("historical_flat_fp_issue205", "historical_flat_representative", "Va_Prokofiev_Symphony1", "page_004", (2613, 4110, 2617, 4208), "negative", "issue205_issue206_historical_representative"),
    ("historical_flat_near_true_issue205", "historical_flat_true_guard", "Va_Prokofiev_Symphony1", "page_004", (2404, 4107, 2412, 4208), "true_barline", "issue205_same_row_nearest_gt"),
    ("reg_festival_p009", "canonical_regression_control", "Shostakovich-Festival_Overture_Va", "page_009", (1232, 1848, 1236, 1959), "true_barline", "issue291_canonical_contract"),
    ("reg_shostakovich_p004_a", "canonical_regression_control", "Shostakovich-Sym5-Va", "page_004", (1690, 2627, 1699, 2727), "true_barline", "issue291_canonical_contract"),
    ("reg_shostakovich_p004_b", "canonical_regression_control", "Shostakovich-Sym5-Va", "page_004", (2730, 1893, 2739, 1995), "true_barline", "issue291_canonical_contract"),
    ("reg_shostakovich_p006", "canonical_regression_control", "Shostakovich-Sym5-Va", "page_006", (2728, 2612, 2737, 2714), "true_barline", "issue291_canonical_contract"),
    ("reg_shostakovich_p013", "canonical_regression_control", "Shostakovich-Sym5-Va", "page_013", (1679, 1168, 1683, 1270), "true_barline", "issue291_canonical_contract"),
    ("reg_sibelius_p004_a", "canonical_regression_control", "Sibelius-Violin_Concerto-Viola", "page_004", (1514, 4015, 1518, 4195), "true_barline", "issue291_canonical_contract"),
    ("reg_sibelius_p004_b", "canonical_regression_control", "Sibelius-Violin_Concerto-Viola", "page_004", (1924, 4015, 1928, 4195), "true_barline", "issue291_canonical_contract"),
    ("iter7_rescue_sibelius_p006", "cnn_rescue_control", "Sibelius-Violin_Concerto-Viola", "page_006", (1919, 1580, 1923, 1687), "true_barline", "issue44_iter7_rescue"),
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_box(raw: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    return tuple(int(round(float(v))) for v in raw[:4])


def boxes(payload: Any) -> list[tuple[int, int, int, int]]:
    if isinstance(payload, dict):
        for key in ("predictions", "scores", "boxes"):
            if key in payload:
                return boxes(payload[key])
        for key in ("bbox", "pred_bbox", "barline_location"):
            parsed = norm_box(payload.get(key))
            if parsed is not None:
                return [parsed]
        return []
    if not isinstance(payload, list):
        return []
    result = []
    for item in payload:
        parsed = None
        if isinstance(item, dict):
            for key in ("bbox", "pred_bbox", "barline_location"):
                parsed = norm_box(item.get(key))
                if parsed is not None:
                    break
        else:
            parsed = norm_box(item)
        if parsed is not None:
            result.append(parsed)
    return result


def gt_map(score: str, page: str) -> dict[tuple[int, int, int, int], str]:
    path = GT_ROOT / score / page / "boxes_sorted.json"
    result = {}
    for row in load_json(path):
        bbox = norm_box(row.get("barline_location"))
        if bbox is not None:
            result[bbox] = str(row.get("barline_type") or "barline")
    return result


def xcenter(box: tuple[int, int, int, int]) -> float:
    return (box[0] + box[2]) / 2.0


def yover(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return overlap / max(1, min(abs(a[3] - a[1]), abs(b[3] - b[1])))


def matches_gt(candidate: tuple[int, int, int, int], truths: Iterable[tuple[int, int, int, int]]) -> bool:
    return any(abs(xcenter(candidate) - xcenter(gt)) <= 12 and yover(candidate, gt) >= 0.5 for gt in truths)


def dense_paths(score: str, page: str) -> dict[str, Path]:
    root = RUN_ROOT / "runs" / score / "intermediate/dense_full_pipeline_route/dense_candidate_reconstruction"
    rescue = root / "probe_rescue_candidates" / f"eval2_{score}_{page}"
    return {
        "raw": root / "probe_candidates_from_inventory" / score / page / "pipeline2_no_peak_candidates.json",
        "filtered": root / "probe_candidates_filtered" / score / page / "pipeline2_no_peak_candidates.json",
        "rescue": rescue / "pipeline2_no_peak_candidates.json",
        "scored": rescue / "pipeline2_no_peak_scored.json",
        "accepted": rescue / "pipeline2_no_peak_filtered_cnn.json",
    }


def source_paths(score: str, page: str) -> dict[str, Path]:
    base = RUN_ROOT / "hybrid" / score
    cur = base / "current_support" / score / page / "artifacts"
    return {
        "hybrid": base / "hybrid_results" / f"{page}_hybrid.json",
        "baseline": base / "baseline" / "batch" / page / f"{page}_detections.json",
        "current_homr": cur / "current_homr" / "batch" / page / f"{page}_detections.json",
        "omr_sr": cur / "omr_sr" / page / "predictions.json",
    }


def presence(path: Path, bbox: tuple[int, int, int, int]) -> bool | None:
    if not path.is_file():
        return None
    return bbox in boxes(load_json(path))


def retained_score(path: Path, bbox: tuple[int, int, int, int]) -> float | None:
    if not path.is_file():
        return None
    for item in load_json(path):
        if isinstance(item, dict) and norm_box(item.get("bbox")) == bbox:
            value = item.get("score")
            return float(value) if isinstance(value, (int, float)) else None
    return None


def add_case(cases: list[dict[str, Any]], case_id: str, category: str, score: str, page: str, bbox: tuple[int, int, int, int], role: str, provenance: str) -> None:
    key = (score, page, bbox, category)
    if any((c["score"], c["page"], tuple(c["bbox"]), c["category"]) == key for c in cases):
        return
    cases.append({"case_id": case_id, "category": category, "score": score, "page": page, "bbox": list(bbox), "expected_detector_role": role, "provenance": provenance})


def build_dynamic_cases(cases: list[dict[str, Any]]) -> None:
    add_case(cases, "target_page015_x580", "target_downstream_fp", TARGET_SCORE, TARGET_PAGE, TARGET, "negative", "current_canonical_and_causal_replay")
    target_h = TARGET[3] - TARGET[1]
    truths = gt_map(TARGET_SCORE, TARGET_PAGE)
    same_band = [(b, t) for b, t in truths.items() if yover(b, TARGET) >= 0.75 and target_h - 30 <= b[3] - b[1] <= target_h + 30 and b[2] - b[0] <= 15]
    for idx, (bbox, bar_type) in enumerate(sorted(same_band)[:8], 1):
        add_case(cases, f"target_band_true_{idx:02d}", "matched_true_same_band", TARGET_SCORE, TARGET_PAGE, bbox, "true_barline", f"current_canonical_gt:{bar_type}")

    raw = boxes(load_json(dense_paths(TARGET_SCORE, TARGET_PAGE)["raw"]))
    options = []
    for bbox in raw:
        if bbox == TARGET or matches_gt(bbox, truths):
            continue
        h, w = abs(bbox[3] - bbox[1]), abs(bbox[2] - bbox[0])
        if yover(bbox, TARGET) >= 0.70 and 70 <= h <= 145 and 1 <= w <= 14:
            distance = abs(h - target_h) + 4 * abs(w - 4)
            options.append((distance, bbox))
    for idx, (_distance, bbox) in enumerate(sorted(options)[:10], 1):
        add_case(cases, f"matched_probe_negative_{idx:02d}", "matched_first_probe_negative", TARGET_SCORE, TARGET_PAGE, bbox, "negative", "retained_issue274_first_dense_raw_non_gt_match")


def add_p3_controls(cases: list[dict[str, Any]]) -> None:
    selected: dict[str, tuple[str, str, tuple[int, int, int, int], tuple[int, int, int, int]]] = {}
    for path in sorted(GT_ROOT.glob("*/page_*/boxes_sorted.json")):
        score, page = path.parent.parent.name, path.parent.name
        typed = list(gt_map(score, page).items())
        for (a, atype), (b, btype) in combinations(typed, 2):
            if abs(xcenter(a) - xcenter(b)) > 15 or yover(a, b) < 0.70:
                continue
            for wanted in MULTI_TYPES:
                if wanted not in selected and wanted in (atype, btype):
                    selected[wanted] = (score, page, a, b)
        if len(selected) == len(MULTI_TYPES):
            break
    for bar_type, (score, page, a, b) in selected.items():
        for idx, bbox in enumerate((a, b), 1):
            add_case(cases, f"p3_{bar_type}_stroke_{idx}", f"p3_{bar_type}_physical_stroke", score, page, bbox, "true_barline", "current_canonical_p3_contract")


def features(image: np.ndarray, bbox: tuple[int, int, int, int]) -> dict[str, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape
    x1, y1, x2, y2 = bbox
    xa, xb = max(0, min(x1, x2)), min(w_img, max(x1, x2))
    ya, yb = max(0, min(y1, y2)), min(h_img, max(y1, y2))
    core = gray[ya:yb, xa:xb] < 200
    left = gray[ya:yb, max(0, xa - 32):xa] < 200
    right = gray[ya:yb, xb:min(w_img, xb + 32)] < 200
    def row_ratio(mask: np.ndarray) -> float:
        return float(np.mean(np.any(mask, axis=1))) if mask.size and mask.shape[0] else 0.0
    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
    cw, ch = crop_size_from_bbox(bbox)
    crop = center_crop(image, cx, cy, cw, ch)
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return {
        "width": float(abs(x2 - x1)), "height": float(abs(y2 - y1)),
        "aspect_h_over_w": float(abs(y2 - y1) / max(1, abs(x2 - x1))),
        "bbox_ink_ratio_lt200": float(np.mean(core)) if core.size else 0.0,
        "bbox_vertical_coverage": row_ratio(core),
        "left_adjacent_ink_row_ratio_32px": row_ratio(left),
        "right_adjacent_ink_row_ratio_32px": row_ratio(right),
        "production_crop_ink_ratio_lt200": float(np.mean(crop_gray < 200)),
        "production_crop_width": float(cw), "production_crop_height": float(ch),
    }


def rescore(image: np.ndarray, bbox: tuple[int, int, int, int], model: torch.nn.Module | None, gpu_norm: GPUNormalize | None) -> float | None:
    if model is None or gpu_norm is None:
        return None
    x1, y1, x2, y2 = bbox
    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
    cw, ch = crop_size_from_bbox(bbox)
    crop = center_crop(image, cx, cy, cw, ch)
    pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    tensor = transforms.ToTensor()(pil.resize((IMG_SIZE[1], IMG_SIZE[0]), Image.BILINEAR))
    batch = gpu_norm(tensor.unsqueeze(0).to(DEVICE))
    with torch.no_grad():
        return float(torch.sigmoid(model(batch)).cpu().item())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    build_dynamic_cases(cases)
    for item in STATIC_CASES:
        add_case(cases, *item)
    add_p3_controls(cases)

    model = get_model(CHECKPOINT, "resnet18") if CHECKPOINT.is_file() else None
    gpu_norm = GPUNormalize(MEAN, STD).to(DEVICE) if model is not None else None
    enriched = []
    for case in cases:
        score, page = case["score"], case["page"]
        bbox = tuple(case["bbox"])
        image_path = IMAGE_ROOT / score / f"{page}.png"
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        gt = gt_map(score, page)
        dpaths, spaths = dense_paths(score, page), source_paths(score, page)
        record = dict(case)
        record.update({
            "canonical_gt_exact": bbox in gt,
            "canonical_gt_type": gt.get(bbox),
            "retained_production_score": retained_score(dpaths["scored"], bbox),
            "retained_accepted": presence(dpaths["accepted"], bbox),
            "stage_presence": {name: presence(path, bbox) for name, path in dpaths.items() if name != "scored"},
            "source_support_exact": {name: presence(path, bbox) for name, path in spaths.items()},
            "features": features(image, bbox),
            "rescored_current_checkpoint": rescore(image, bbox, model, gpu_norm),
        })
        value = record["rescored_current_checkpoint"]
        record["rescored_accepts_at_0p1"] = value is not None and value > CNN_THRESHOLD
        enriched.append(record)

    counts: dict[str, int] = {}
    for case in enriched:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    payload = {
        "schema_version": "issue296.matched_guard_set.v1",
        "purpose": "freeze matched guards before solution tuning",
        "temporary_helper": True,
        "checkpoint": str(CHECKPOINT),
        "checkpoint_status": "loaded" if model is not None else "missing",
        "device": str(DEVICE),
        "cnn_threshold": CNN_THRESHOLD,
        "case_count": len(enriched),
        "category_counts": counts,
        "cases": enriched,
    }
    out = OUT / "matched_guard_set.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nSUMMARY={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
