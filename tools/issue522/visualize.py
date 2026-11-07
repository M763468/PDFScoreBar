#!/usr/bin/env python3
"""Issue #522 (harness from #519): before/after overlays of control vs no_omr on the original score images.

Draws, on the unchanged source image, GT barlines, retained producer candidates
(original HOMR, x4 HOMR, OMR-DLN), each variant's final predictions and each variant's
final measure boxes with final measure numbers.  Produces a full-page overlay and a
side-by-side zoom (control | no_omr) with a coordinate legend.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path("/workspace")
SRC = ROOT / "logs/issue409/full68-numbering-20261009/candidate"
ABL = ROOT / "logs/issue519/ablation"
DOWN = ROOT / "logs/issue519/downstream-20261108"

# BGR
C_GT = (0, 170, 0)
C_HOMR = (255, 120, 0)
C_X4 = (200, 200, 0)
C_OMR = (0, 200, 255)
C_FINAL = (0, 0, 230)
C_LOST = (255, 0, 255)
C_MEASURE = (150, 60, 150)


def read(p):
    return json.loads(Path(p).read_text())


def boxes(path):
    data = read(path)
    if isinstance(data, dict) and "predictions" in data:
        return [p["orig_bbox"] for p in data["predictions"]]
    if data and isinstance(data[0], dict):
        return [d["barline_location"] for d in data]
    return data


def sources(score, page):
    summary = read(SRC / "variant_summary.json")
    item = next(s for s in summary["scores"] if s["score"] == score)
    hyb = ROOT / Path(item["hybrid_run"]).relative_to("/workspace")
    sup = read(hyb / "current_support" / score / page / "result.json")
    return dict(
        homr=boxes(hyb / "baseline/batch" / page / f"{page}_detections.json"),
        x4=boxes(sup["current_sr_detection"]),
        omr=boxes(sup["current_omr"]),
        gt=[
            g["barline_location"]
            for g in read(ROOT / f"data/evaluation2/annotations/{score}/{page}/boxes_sorted.json")
        ],
    )


def finals(variant, score, page):
    pred = read(ABL / variant / "candidate" / score / page / "predictions.json")
    fin = read(DOWN / variant / score / "outputs" / page / "numbering_final.json")
    measures = [m for s in fin["pages"][0]["systems"] for m in s["measures"]]
    return pred, measures


def rect(img, b, color, t=1, pad=0):
    cv2.rectangle(img, (int(b[0]) - pad, int(b[1])), (int(b[2]) + pad, int(b[3])), color, t)


def intersects(b, win):
    return b[2] >= win[0] and b[0] <= win[2] and b[3] >= win[1] and b[1] <= win[3]


def panel(image, win, src, pred, measures, other_pred, title, show_omr, scale):
    x1, y1, x2, y2 = win
    crop = image[y1:y2, x1:x2].copy()
    crop = cv2.resize(
        crop,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )

    def s(b):
        return [(b[0] - x1) * scale, (b[1] - y1) * scale, (b[2] - x1) * scale, (b[3] - y1) * scale]

    for m in measures:
        if intersects(m["bbox"], win):
            rect(crop, s(m["bbox"]), C_MEASURE, 1)
            bx = s(m["bbox"])
            cv2.putText(
                crop,
                f"#{m['number']}",
                (int(bx[0]) + 6, int(bx[1]) + 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                C_MEASURE,
                2,
            )
    layers = [("homr", C_HOMR, 9), ("x4", C_X4, 13)] + ([("omr", C_OMR, 17)] if show_omr else [])
    for key, color, pad in layers:
        for b in src[key]:
            if intersects(b, win):
                rect(crop, s(b), color, 1, pad)
    for b in src["gt"]:
        if intersects(b, win):
            rect(crop, s(b), C_GT, 2, 5)
    for b in pred:
        if intersects(b, win):
            rect(crop, s(b), C_FINAL, 2, 2)
    for b in other_pred:
        if b not in pred and intersects(b, win):
            rect(crop, s(b), C_LOST, 2, 3)
            cv2.putText(
                crop,
                "missing here",
                (int(s(b)[2]) + 8, int((s(b)[1] + s(b)[3]) / 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                C_LOST,
                2,
            )
    bar = np.full((40, crop.shape[1], 3), 255, np.uint8)
    cv2.putText(bar, title, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return np.vstack([bar, crop])


def legend(width, lines):
    items = [
        ("GT barline", C_GT),
        ("original HOMR candidate", C_HOMR),
        ("x4 HOMR candidate", C_X4),
        ("OMR-DLN barline (control only)", C_OMR),
        ("final prediction (this variant)", C_FINAL),
        ("final in other variant, absent here", C_LOST),
        ("final measure bbox + number", C_MEASURE),
    ]
    h = 30 * (len(items) + len(lines)) + 20
    img = np.full((h, width, 3), 255, np.uint8)
    y = 25
    for text, color in items:
        cv2.rectangle(img, (10, y - 14), (40, y), color, 3)
        cv2.putText(img, text, (50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
        y += 30
    for text in lines:
        cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
        y += 30
    return img


def render(score, page, win, out, notes, full_page=False, scale=1.0):
    image = cv2.imread(str(ROOT / f"data/evaluation2/images/{score}/{page}.png"))
    src = sources(score, page)
    cp, cm = finals("control", score, page)
    npred, nm = finals("no_omr", score, page)
    left = panel(
        image, win, src, cp, cm, npred, f"control (OMR-DLN support) {score}/{page}", True, scale
    )
    right = panel(
        image, win, src, npred, nm, cp, f"no_omr (OMR-DLN removed) {score}/{page}", False, scale
    )
    sep = np.full((left.shape[0], 12, 3), 80, np.uint8)
    body = np.hstack([left, sep, right])
    lines = [f"window x{win[0]}-{win[2]} y{win[1]}-{win[3]} (source px, scale {scale})"] + notes
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack([body, legend(body.shape[1], lines)]))
    if full_page:
        h, w = image.shape[:2]
        full = render_full(image, src, cp, npred, cm, win)
        cv2.imwrite(str(out.with_name(out.stem + "_fullpage.png")), full)
    print(out, flush=True)


def render_full(image, src, cp, npred, measures, win):
    img = image.copy()
    for m in measures:
        rect(img, m["bbox"], C_MEASURE, 2)
        cv2.putText(
            img,
            str(m["number"]),
            (m["bbox"][0] + 8, m["bbox"][1] + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            C_MEASURE,
            2,
        )
    for b in src["gt"]:
        rect(img, b, C_GT, 3, 8)
    for b in cp:
        rect(img, b, C_FINAL, 2, 3)
    for b in cp:
        if b not in npred:
            rect(img, b, C_LOST, 5, 14)
    cv2.rectangle(img, (win[0], win[1]), (win[2], win[3]), (0, 0, 0), 4)
    cv2.putText(
        img, "zoom window", (win[0], win[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3
    )
    bar = np.full((70, img.shape[1], 3), 255, np.uint8)
    cv2.putText(
        bar,
        "green=GT  red=control final  magenta=control final absent in no_omr  "
        "purple=final measure (no_omr numbering identical)",
        (10, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
    )
    return np.vstack([bar, img])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="JSON list of {score,page,window,name,notes,full_page,scale}",
    )
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    for item in read(a.plan):
        render(
            item["score"],
            item["page"],
            item["window"],
            a.out_dir / f"{item['name']}.png",
            item.get("notes", []),
            item.get("full_page", False),
            item.get("scale", 1.0),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
