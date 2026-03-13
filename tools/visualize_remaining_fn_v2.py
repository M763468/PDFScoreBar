import json
import math
from pathlib import Path

import cv2
import numpy as np

from src.common.barline_evaluation import (
    barline_iou,
    barline_vertical_overlap,
    center_distance_x,
    get_barline_match_rank,
    greedy_barline_match,
    is_barline_match,
)
from tools.re_evaluate_global import find_gt_file

# Paths
scored_root = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_same_source_bboxnorm_w0p8_h4p0_patch10_croprecenter_v2_ge0p5"
)
images_root = Path("data/evaluation2/images")
gt_root = Path("data/evaluation2/annotations")
# output dir for center_anchor rule results
out_root = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/fn_remaining_center_anchor_th0p1"
)
out_root.mkdir(parents=True, exist_ok=True)

# Evaluation Parameters (Center-Anchor)
EVAL_RULE = "center_anchor"
THRESHOLD = 0.1
VOV_THRESHOLD = 0.5
XDIST_THRESHOLD = 12.0
DISTANCE_THRESHOLD = 200  # for visualization pairing


def load_gt(p):
    data = json.load(open(p))
    out = []
    for it in data:
        if isinstance(it, list):
            out.append(tuple(int(v) for v in it[:4]))
        elif "box" in it:
            out.append(tuple(int(v) for v in it["box"][:4]))
        elif "barline_location" in it:
            out.append(tuple(int(v) for v in it["barline_location"][:4]))
    return out


def get_dist(b1, b2):
    c1 = ((b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2)
    c2 = ((b2[0] + b2[2]) / 2, (b2[1] + b2[3]) / 2)
    return math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2)


summary = []
idx = 1

for scored in sorted(scored_root.rglob("*_scored.json")):
    rel = scored.relative_to(scored_root)
    if len(rel.parts) < 3:
        continue
    score, page = rel.parts[0], rel.parts[1]
    gt_path = find_gt_file(gt_root, score, page)
    if not gt_path:
        continue
    image_path = images_root / score / f"{page}.png"
    if not image_path.exists():
        continue

    cands = json.load(open(scored))
    gts = load_gt(gt_path)
    accepted = [
        tuple(int(v) for v in c["bbox"][:4]) for c in cands if float(c["score"]) > THRESHOLD
    ]
    all_candidate_boxes = [tuple(int(v) for v in c["bbox"][:4]) for c in cands]

    # USE THE SAME MATCHING LOGIC AS GLOBAL EVAL
    match = greedy_barline_match(
        accepted,
        gts,
        rule_name=EVAL_RULE,
        vov_threshold=VOV_THRESHOLD,
        xdist_threshold=XDIST_THRESHOLD,
    )

    if not match.false_negative_indices:
        continue

    img = cv2.imread(str(image_path))
    if img is None:
        continue

    for fn_idx in match.false_negative_indices:
        gt = gts[fn_idx]
        best = None
        found_by_detector = False

        for cand_box in all_candidate_boxes:
            dist = get_dist(cand_box, gt)
            if dist < DISTANCE_THRESHOLD:
                # Check if this candidate satisfies the evaluation rule
                if is_barline_match(
                    cand_box,
                    gt,
                    EVAL_RULE,
                    vov_threshold=VOV_THRESHOLD,
                    xdist_threshold=XDIST_THRESHOLD,
                ):
                    found_by_detector = True

                # Use common ranking logic to pick the best for visualization
                rank = get_barline_match_rank(cand_box, gt, EVAL_RULE)
                if best is None or rank > best["rank"]:
                    # Extract individual metrics for visualization
                    iou = barline_iou(cand_box, gt)
                    vov = barline_vertical_overlap(cand_box, gt)
                    xdist = center_distance_x(cand_box, gt)
                    # Find original candidate score
                    score = 0.0
                    for c in cands:
                        if tuple(c["bbox"][:4]) == cand_box:
                            score = float(c.get("score", 0.0))
                            break

                    best = {
                        "bbox": cand_box,
                        "score": score,
                        "iou": iou,
                        "vov": vov,
                        "xdist": xdist,
                        "dist": dist,
                        "rank": rank,
                    }

        kind = "fn_cnn" if found_by_detector else "fn_det"

        canvas = img.copy()
        x1, y1, x2, y2 = gt
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 3)
        cv2.putText(
            canvas,
            "GT",
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        if best:
            bx1, by1, bx2, by2 = best["bbox"]
            color = (0, 255, 255) if kind == "fn_cnn" else (0, 0, 255)
            cv2.rectangle(canvas, (bx1, by1), (bx2, by2), color, 2)
            cv2.putText(
                canvas,
                f"cand s={best['score']:.3f} vov={best['vov']:.2f} xdist={best['xdist']:.1f}",
                (max(0, bx1 - 20), min(canvas.shape[0] - 10, by1 + 25)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
                cv2.LINE_AA,
            )
        else:
            cv2.putText(
                canvas,
                "NO CANDIDATE NEARBY",
                (x1, y2 + 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        cv2.putText(
            canvas,
            f"{idx:02d} {kind} {score} {page}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 0, 0),
            2,
            cv2.LINE_AA,
        )
        out_path = out_root / f"{idx:02d}_{kind}_{score}__{page}.png"
        cv2.imwrite(str(out_path), canvas)

        summary.append(
            {
                "index": idx,
                "kind": kind,
                "image": str(out_path),
                "score": score,
                "page": page,
                "gt": list(gt),
                "best_vov": None if not best else round(best["vov"], 6),
                "best_xdist": None if not best else round(best["xdist"], 6),
                "best_score": None if not best else round(best["score"], 6),
                "best_cand": None if not best else list(best["bbox"]),
                "best_dist": None if not best else round(best["dist"], 2),
            }
        )
        idx += 1

# Generate contact sheets
for kind in ["fn_cnn", "fn_det"]:
    items = [s for s in summary if s["kind"] == kind]
    if not items:
        continue
    thumbs = []
    for s in items:
        im = cv2.imread(s["image"])
        h, w = im.shape[:2]
        scale = min(320 / w, 220 / h)
        tw, th = int(w * scale), int(h * scale)
        thumb = cv2.resize(im, (tw, th))
        tile = 255 * np.ones((240, 340, 3), dtype="uint8")
        y, x = (240 - th) // 2, (340 - tw) // 2
        tile[y : y + th, x : x + tw] = thumb
        cv2.putText(
            tile,
            f"{s['index']:02d} {s['score']} {s['page']}",
            (8, 230),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
        thumbs.append(tile)
    cols = 2
    rows = math.ceil(len(thumbs) / cols)
    sheet = 255 * np.ones((rows * 240, cols * 340, 3), dtype="uint8")
    for i, t in enumerate(thumbs):
        r, c = i // cols, i % cols
        sheet[r * 240 : (r + 1) * 240, c * 340 : (c + 1) * 340] = t
    cv2.imwrite(str(out_root / f"contact_sheet_{kind}.png"), sheet)

with open(out_root / "summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(f"Done. Generated {len(summary)} images in {out_root}")
