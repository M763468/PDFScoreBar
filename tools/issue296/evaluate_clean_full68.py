#!/usr/bin/env python3
"""Temporary Issue #296 full68 audit for the contamination-free clean model.

Diagnostic-only. Delete before PR preparation.

This script intentionally does NOT combine the clean checkpoint with the
historical production checkpoint and does NOT apply any rescue rule.  The
historical accepted artifact is used only as a control to reproduce the
canonical retained-artifact contract.
"""
from __future__ import annotations

import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from src.common.barline_evaluation import greedy_barline_match, is_barline_match
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
CLEAN_CKPT = ROOT / "logs/cnn_barline_classification/issue296_clean_retrain_v1/cnn_classifier_best.pth"
OUT = ROOT / "logs/issue296/diagnostic_07_clean_full68"
THRESHOLD = 0.1
TARGET_SCORE = "Va__Prokofiev_Symphony5"
TARGET_PAGE = "page_015"
TARGET = (580, 4005, 584, 4115)
P007 = {
    (665, 908, 669, 1018),
    (668, 908, 672, 1018),
}
MULTI_TYPES = ("double_barline", "end_barline", "repeat")
EXPECTED_CONTROL = {"pages": 68, "gt": 3567, "tp": 3565, "hard_fp": 3, "fn": 2, "soft": 31}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_box(raw: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    return tuple(int(round(float(v))) for v in raw[:4])


def extract_boxes(payload: Any) -> list[tuple[int, int, int, int]]:
    if not isinstance(payload, list):
        return []
    result: list[tuple[int, int, int, int]] = []
    for item in payload:
        raw = item.get("bbox") if isinstance(item, dict) else item
        box = norm_box(raw)
        if box is not None:
            result.append(box)
    return result


def gt_rows(score: str, page: str) -> list[dict[str, Any]]:
    return load_json(GT_ROOT / score / page / "boxes_sorted.json")


def gt_boxes(score: str, page: str) -> list[tuple[int, int, int, int]]:
    result = []
    for row in gt_rows(score, page):
        box = norm_box(row.get("barline_location"))
        if box is not None:
            result.append(box)
    return result


def parse_context(scored_path: Path) -> tuple[str, str]:
    name = scored_path.parent.name
    if not name.startswith("eval2_") or "_page_" not in name:
        raise ValueError(f"unparseable retained page dir: {name}")
    body = name[len("eval2_") :]
    score, page_no = body.rsplit("_page_", 1)
    return score, f"page_{page_no}"


def retained_paths(score: str, page: str) -> tuple[Path, Path]:
    root = (
        RUN_ROOT
        / "runs"
        / score
        / "intermediate/dense_full_pipeline_route/dense_candidate_reconstruction/probe_rescue_candidates"
        / f"eval2_{score}_{page}"
    )
    return root / "pipeline2_no_peak_scored.json", root / "pipeline2_no_peak_filtered_cnn.json"


def xcenter(box: tuple[int, int, int, int]) -> float:
    return (box[0] + box[2]) / 2.0


def short_side_vov(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    ha = max(1, abs(a[3] - a[1]))
    hb = max(1, abs(b[3] - b[1]))
    return overlap / min(ha, hb)


def p3_pairs_for_page(score: str, page: str) -> list[dict[str, Any]]:
    typed: list[tuple[tuple[int, int, int, int], str]] = []
    for row in gt_rows(score, page):
        box = norm_box(row.get("barline_location"))
        if box is None:
            continue
        typed.append((box, str(row.get("barline_type") or "barline")))

    pairs = []
    for (a, atype), (b, btype) in combinations(typed, 2):
        # This is the same semantic-near-line criterion already used by the
        # frozen Issue #296 P3 guard collector. It is used here for AUDIT only,
        # not as an inference rule.
        if abs(xcenter(a) - xcenter(b)) > 15 or short_side_vov(a, b) < 0.70:
            continue
        if not any(wanted in (atype, btype) for wanted in MULTI_TYPES):
            continue
        pairs.append({
            "a": list(a),
            "a_type": atype,
            "b": list(b),
            "b_type": btype,
            "xdist": abs(xcenter(a) - xcenter(b)),
            "short_side_vov": short_side_vov(a, b),
        })
    return pairs


def score_boxes(
    image: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    model: torch.nn.Module,
    gpu_norm: GPUNormalize,
) -> list[float]:
    tensors = []
    for box in boxes:
        x1, y1, x2, y2 = box
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
        cw, ch = crop_size_from_bbox(box)
        crop = center_crop(image, cx, cy, cw, ch)
        pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        tensor = transforms.ToTensor()(pil.resize((IMG_SIZE[1], IMG_SIZE[0]), Image.BILINEAR))
        tensors.append(tensor)

    scores: list[float] = []
    for start in range(0, len(tensors), 64):
        batch = torch.stack(tensors[start : start + 64]).to(DEVICE)
        batch = gpu_norm(batch)
        with torch.no_grad():
            chunk = torch.sigmoid(model(batch)).cpu().numpy().reshape(-1)
        scores.extend(float(v) for v in chunk)
    return scores


def evaluate(preds: list[tuple[int, int, int, int]], truths: list[tuple[int, int, int, int]]):
    result = greedy_barline_match(
        preds,
        truths,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    return result


def matches_any(preds: list[tuple[int, int, int, int]], gt: tuple[int, int, int, int]) -> bool:
    return any(
        is_barline_match(
            pred,
            gt,
            "center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        )
        for pred in preds
    )


def aggregate(page_rows: list[dict[str, Any]], prefix: str) -> dict[str, int]:
    return {
        "pages": len(page_rows),
        "gt": sum(row["gt_count"] for row in page_rows),
        "tp": sum(row[f"{prefix}_tp"] for row in page_rows),
        "hard_fp": sum(row[f"{prefix}_hard_fp"] for row in page_rows),
        "fn": sum(row[f"{prefix}_fn"] for row in page_rows),
        "soft": sum(row[f"{prefix}_soft"] for row in page_rows),
    }


def main() -> int:
    if not CLEAN_CKPT.is_file():
        raise FileNotFoundError(CLEAN_CKPT)
    if not RUN_ROOT.is_dir():
        raise FileNotFoundError(RUN_ROOT)

    OUT.mkdir(parents=True, exist_ok=True)
    model = get_model(CLEAN_CKPT, "resnet18")
    gpu_norm = GPUNormalize(MEAN, STD).to(DEVICE)

    scored_paths = sorted(
        RUN_ROOT.glob(
            "runs/*/intermediate/dense_full_pipeline_route/"
            "dense_candidate_reconstruction/probe_rescue_candidates/"
            "eval2_*/pipeline2_no_peak_scored.json"
        )
    )
    if len(scored_paths) != 68:
        raise RuntimeError(f"expected 68 retained scored pages, got {len(scored_paths)}")

    pages: list[dict[str, Any]] = []
    residuals: list[dict[str, Any]] = []
    p3_rows: list[dict[str, Any]] = []
    acceptance_deltas: list[dict[str, Any]] = []

    for page_idx, scored_path in enumerate(scored_paths, 1):
        score, page = parse_context(scored_path)
        _, accepted_path = retained_paths(score, page)
        if not accepted_path.is_file():
            raise FileNotFoundError(accepted_path)
        image_path = IMAGE_ROOT / score / f"{page}.png"
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)

        scored_payload = load_json(scored_path)
        candidates = extract_boxes(scored_payload)
        control = extract_boxes(load_json(accepted_path))
        truths = gt_boxes(score, page)
        clean_scores = score_boxes(image, candidates, model, gpu_norm)
        clean = [box for box, value in zip(candidates, clean_scores) if value > THRESHOLD]

        control_eval = evaluate(control, truths)
        clean_eval = evaluate(clean, truths)
        pages.append({
            "score": score,
            "page": page,
            "candidate_count": len(candidates),
            "gt_count": len(truths),
            "control_accepted": len(control),
            "clean_accepted": len(clean),
            "control_tp": len(control_eval.matches),
            "control_hard_fp": len(control_eval.false_positive_indices),
            "control_fn": len(control_eval.false_negative_indices),
            "control_soft": len(control_eval.soft_matches),
            "clean_tp": len(clean_eval.matches),
            "clean_hard_fp": len(clean_eval.false_positive_indices),
            "clean_fn": len(clean_eval.false_negative_indices),
            "clean_soft": len(clean_eval.soft_matches),
        })

        control_set = set(control)
        clean_set = set(clean)
        for box, value in zip(candidates, clean_scores):
            before = box in control_set
            after = box in clean_set
            if before != after:
                acceptance_deltas.append({
                    "score": score,
                    "page": page,
                    "bbox": list(box),
                    "control_accept": before,
                    "clean_accept": after,
                    "clean_score": value,
                    "target": score == TARGET_SCORE and page == TARGET_PAGE and box == TARGET,
                    "p007_known_fp": score == TARGET_SCORE and page == "page_007" and box in P007,
                })

        for pred_idx in clean_eval.false_positive_indices:
            residuals.append({
                "kind": "clean_hard_fp",
                "score": score,
                "page": page,
                "bbox": list(clean[pred_idx]),
            })
        for gt_idx in clean_eval.false_negative_indices:
            residuals.append({
                "kind": "clean_fn",
                "score": score,
                "page": page,
                "bbox": list(truths[gt_idx]),
            })

        for pair in p3_pairs_for_page(score, page):
            a = tuple(pair["a"])
            b = tuple(pair["b"])
            pair.update({
                "score": score,
                "page": page,
                "control_a_present": matches_any(control, a),
                "control_b_present": matches_any(control, b),
                "clean_a_present": matches_any(clean, a),
                "clean_b_present": matches_any(clean, b),
            })
            pair["control_pair_complete"] = pair["control_a_present"] and pair["control_b_present"]
            pair["clean_pair_complete"] = pair["clean_a_present"] and pair["clean_b_present"]
            p3_rows.append(pair)

        print(f"[{page_idx:02d}/68] {score}/{page}: candidates={len(candidates)} clean={len(clean)}")

    control_agg = aggregate(pages, "control")
    clean_agg = aggregate(pages, "clean")
    control_reproduces = control_agg == EXPECTED_CONTROL

    if len(p3_rows) != 51:
        raise RuntimeError(f"P3 audit invariant failed: expected 51 pairs, got {len(p3_rows)}")

    target_delta = next(
        (row for row in acceptance_deltas if row["target"]),
        None,
    )
    p007_deltas = [row for row in acceptance_deltas if row["p007_known_fp"]]
    p3_incomplete = [row for row in p3_rows if not row["clean_pair_complete"]]

    residual_counts = Counter(row["kind"] for row in residuals)
    payload = {
        "schema_version": "issue296.clean_full68.v1",
        "purpose": "full68 contamination-free clean-model audit; no ensemble and no rescue rule",
        "checkpoint": str(CLEAN_CKPT),
        "device": str(DEVICE),
        "threshold": THRESHOLD,
        "matcher": {"rule": "center_anchor", "vov_threshold": 0.5, "xdist_threshold": 12.0},
        "expected_control": EXPECTED_CONTROL,
        "control": control_agg,
        "control_reproduces_canonical_contract": control_reproduces,
        "clean": clean_agg,
        "delta_vs_control": {key: clean_agg[key] - control_agg[key] for key in ("tp", "hard_fp", "fn", "soft")},
        "target_x580_acceptance_delta": target_delta,
        "p007_known_fp_acceptance_deltas": p007_deltas,
        "acceptance_delta_count": len(acceptance_deltas),
        "p3": {
            "pair_count": len(p3_rows),
            "control_complete_pairs": sum(1 for row in p3_rows if row["control_pair_complete"]),
            "clean_complete_pairs": sum(1 for row in p3_rows if row["clean_pair_complete"]),
            "clean_incomplete_pair_count": len(p3_incomplete),
            "clean_incomplete_pairs": p3_incomplete,
        },
        "residual_counts": dict(residual_counts),
        "residuals": residuals,
        "acceptance_deltas": acceptance_deltas,
        "pages": pages,
    }

    out = OUT / "clean_full68_summary.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "control": control_agg,
        "control_reproduces_canonical_contract": control_reproduces,
        "clean": clean_agg,
        "delta_vs_control": payload["delta_vs_control"],
        "target_x580_acceptance_delta": target_delta,
        "p007_known_fp_acceptance_deltas": p007_deltas,
        "p3_pair_count": len(p3_rows),
        "p3_clean_complete_pairs": payload["p3"]["clean_complete_pairs"],
        "p3_clean_incomplete_pair_count": len(p3_incomplete),
        "residual_counts": dict(residual_counts),
        "output": str(out),
    }, indent=2, ensure_ascii=False))

    if not control_reproduces:
        raise SystemExit("control failed to reproduce canonical retained-artifact contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
