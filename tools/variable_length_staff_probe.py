#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def extract_staff_bands(mask: np.ndarray, min_height: int = 10) -> List[Box]:
    mask_bin = (mask > 0).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
    merged = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    bands = []
    for i in range(1, num_labels):
        x, y, w, h, _ = stats[i]
        if h < min_height:
            continue
        bands.append((x, y, x + w, y + h))
    bands.sort(key=lambda b: b[1])
    return bands


def find_staff_lines(gray: np.ndarray, band: Box, max_lines: int = 5) -> List[int]:
    x1, y1, x2, y2 = band
    crop = gray[y1:y2, x1:x2]
    if crop.size == 0:
        return []
    ink = 255 - crop
    row_sum = ink.sum(axis=1)
    rows = list(range(len(row_sum)))
    min_sep = max(2, int(round((y2 - y1) / 6)))
    candidates = sorted(rows, key=lambda r: row_sum[r], reverse=True)
    picked = []
    for r in candidates:
        if all(abs(r - p) >= min_sep for p in picked):
            picked.append(r)
        if len(picked) >= max_lines:
            break
    picked.sort()
    return [y1 + r for r in picked]


def longest_run(vec: np.ndarray) -> int:
    max_run = 0
    run = 0
    for v in vec:
        if v:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def make_variants(gray: np.ndarray, staff_mask: np.ndarray) -> Dict[str, np.ndarray]:
    variants = {}
    variants["raw_gray"] = gray
    # Adaptive binarization variants
    variants["adap_mean"] = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 10
    )
    variants["adap_gauss"] = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7
    )
    # Staff-line suppressed: set staff mask pixels to white
    staff_suppressed = gray.copy()
    staff_suppressed[staff_mask > 0] = 255
    variants["staff_suppressed"] = staff_suppressed
    return variants


def binarize_for_scoring(img: np.ndarray, variant_name: str) -> np.ndarray:
    if img.ndim == 2 and variant_name.startswith("adap_"):
        return img < 128
    if img.ndim == 2:
        return img < 160
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < 160


def score_window(
    bin_col: np.ndarray,
    note_col: Optional[np.ndarray],
    staff_line_rows: List[int],
    y_start: int,
    length: int,
) -> Dict[str, float]:
    y_end = y_start + length
    seg = bin_col[y_start:y_end]
    ink_ratio = float(np.count_nonzero(seg)) / float(length)
    cont = float(longest_run(seg)) / float(length)
    crossings = 0
    crossing_rows = []
    for r in staff_line_rows:
        if y_start <= r < y_end and bin_col[r]:
            crossings += 1
            crossing_rows.append(r)
    if len(crossing_rows) >= 2:
        diffs = np.diff(crossing_rows)
        crossing_uniformity = float(np.var(diffs)) if len(diffs) > 0 else 0.0
    else:
        crossing_uniformity = 999.0
    note_ratio = 0.0
    if note_col is not None:
        note_seg = note_col[y_start:y_end]
        note_ratio = float(np.count_nonzero(note_seg)) / float(length)
    return {
        "ink_ratio": ink_ratio,
        "continuity": cont,
        "staff_line_crossings": float(crossings),
        "crossing_uniformity": crossing_uniformity,
        "note_ratio": note_ratio,
    }


def score_to_rank(s: Dict[str, float]) -> float:
    crossings_norm = s["staff_line_crossings"] / 5.0
    uniform_pen = min(s["crossing_uniformity"] / 4.0, 1.0)
    return (
        0.6 * s["ink_ratio"]
        + 0.4 * s["continuity"]
        + 0.6 * crossings_norm
        - 0.3 * s["note_ratio"]
        - 0.2 * uniform_pen
    )


def put_text_block(img: np.ndarray, lines: List[str], origin=(8, 18)) -> None:
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 16


def draw_staff_bounds(img: np.ndarray, bands: List[Box]) -> None:
    for x1, y1, x2, y2 in bands:
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 0), 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--notehead-mask", type=Path, required=False)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--page-id", type=str, required=True)
    ap.add_argument("--probe-step", type=int, default=2)
    ap.add_argument("--y-step", type=int, default=2)
    ap.add_argument("--length-factors", type=str, default="0.7,0.85,1.0,1.1")
    ap.add_argument("--topk", type=int, default=10)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    staff = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff is None:
        raise SystemExit(f"Failed to load staff mask: {args.staff_mask}")
    notehead = None
    if args.notehead_mask:
        notehead = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
        if notehead is None:
            raise SystemExit(f"Failed to load notehead mask: {args.notehead_mask}")

    if staff.shape[:2] != base.shape[:2]:
        staff = cv2.resize(staff, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_NEAREST)
    if notehead is not None and notehead.shape[:2] != base.shape[:2]:
        notehead = cv2.resize(
            notehead, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_NEAREST
        )

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    bands = extract_staff_bands(staff)
    length_factors = [float(v) for v in args.length_factors.split(",")]

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    variants = make_variants(gray, staff)

    for vname, vimg in variants.items():
        variant_dir = out_dir / vname
        variant_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(variant_dir / f"{args.page_id}_{vname}.png"), vimg)

        bin_img = binarize_for_scoring(vimg, vname)
        note_bin = (notehead > 0) if notehead is not None else None

        band_results = []
        all_probes = []
        topk_all = []

        for band_idx, band in enumerate(bands):
            x1, y1, x2, y2 = band
            staff_lines = find_staff_lines(gray, band)
            staff_h = max(1, y2 - y1)
            lengths = [max(2, int(round(f * staff_h))) for f in length_factors]

            probes = []
            for x in range(x1, x2, args.probe_step):
                col = bin_img[:, x]
                note_col = note_bin[:, x] if note_bin is not None else None
                for L in lengths:
                    y_min = max(0, y1 - max(0, int(round((L - staff_h) / 2))))
                    y_max = min(base.shape[0] - L, y2)
                    if y_max <= y_min:
                        continue
                    best = None
                    for y in range(y_min, y_max + 1, args.y_step):
                        s = score_window(col, note_col, staff_lines, y, L)
                        s["score"] = score_to_rank(s)
                        if best is None or s["score"] > best["score"]:
                            best = s
                            best["x"] = int(x)
                            best["y1"] = int(y)
                            best["y2"] = int(y + L)
                            best["length"] = int(L)
                    if best is not None:
                        probes.append(best)
                        all_probes.append(best)
            probes_sorted = sorted(probes, key=lambda p: p["score"], reverse=True)
            topk = probes_sorted[: args.topk]
            topk_all.extend(topk)
            band_results.append(
                {
                    "band_index": int(band_idx),
                    "band_box": [int(v) for v in band],
                    "staff_lines": [int(v) for v in staff_lines],
                    "topk": [
                        {
                            "x": int(p["x"]),
                            "y1": int(p["y1"]),
                            "y2": int(p["y2"]),
                            "length": int(p["length"]),
                            "score": float(p["score"]),
                            "ink_ratio": float(p["ink_ratio"]),
                            "continuity": float(p["continuity"]),
                            "staff_line_crossings": float(p["staff_line_crossings"]),
                            "crossing_uniformity": float(p["crossing_uniformity"]),
                            "note_ratio": float(p["note_ratio"]),
                        }
                        for p in topk
                    ],
                }
            )

        # Overlay A: all probes (yellow, alpha)
        overlay_all = base.copy()
        probe_layer = overlay_all.copy()
        for p in all_probes:
            cv2.line(probe_layer, (p["x"], p["y1"]), (p["x"], p["y2"]), (0, 255, 255), 1)
        overlay_all = cv2.addWeighted(probe_layer, 0.25, overlay_all, 0.75, 0)
        draw_staff_bounds(overlay_all, bands)
        put_text_block(
            overlay_all,
            [
                f"Variant={vname}, Yellow=all probes (all lengths), Blue=staff bounds",
                f"base: {args.base}",
                f"staff: {args.staff_mask}",
                f"notehead: {args.notehead_mask if args.notehead_mask else 'none'}",
                f"length_factors: {args.length_factors}",
            ],
            origin=(8, 18),
        )
        cv2.imwrite(str(variant_dir / f"{args.page_id}_{vname}_all_probes.png"), overlay_all)

        # Overlay B: top-10 probes per staff (green)
        overlay_top10 = base.copy()
        for p in topk_all:
            cv2.line(overlay_top10, (p["x"], p["y1"]), (p["x"], p["y2"]), (0, 180, 0), 2)
        draw_staff_bounds(overlay_top10, bands)
        put_text_block(
            overlay_top10,
            [
                f"Variant={vname}, Green=top-10 probes per staff, Blue=staff bounds",
                f"base: {args.base}",
                f"staff: {args.staff_mask}",
                f"notehead: {args.notehead_mask if args.notehead_mask else 'none'}",
                f"length_factors: {args.length_factors}",
            ],
            origin=(8, 18),
        )
        cv2.imwrite(str(variant_dir / f"{args.page_id}_{vname}_top10.png"), overlay_top10)

        # Overlay C: top-1 probe per staff (bright green)
        overlay_top1 = base.copy()
        for band in band_results:
            if not band["topk"]:
                continue
            p = band["topk"][0]
            cv2.line(overlay_top1, (p["x"], p["y1"]), (p["x"], p["y2"]), (0, 255, 0), 3)
        draw_staff_bounds(overlay_top1, bands)
        put_text_block(
            overlay_top1,
            [
                f"Variant={vname}, BrightGreen=top-1 probe per staff, Blue=staff bounds",
                f"base: {args.base}",
                f"staff: {args.staff_mask}",
                f"notehead: {args.notehead_mask if args.notehead_mask else 'none'}",
                f"length_factors: {args.length_factors}",
            ],
            origin=(8, 18),
        )
        cv2.imwrite(str(variant_dir / f"{args.page_id}_{vname}_top1.png"), overlay_top1)

        # Overlay D: staff bounds only
        overlay_staff = base.copy()
        draw_staff_bounds(overlay_staff, bands)
        put_text_block(
            overlay_staff,
            [
                f"Variant={vname}, Blue=staff bounds",
                f"base: {args.base}",
                f"staff: {args.staff_mask}",
            ],
            origin=(8, 18),
        )
        cv2.imwrite(str(variant_dir / f"{args.page_id}_{vname}_staff_bounds.png"), overlay_staff)

        (variant_dir / f"{args.page_id}_{vname}_probe_scores.json").write_text(
            json.dumps(band_results, indent=2)
        )


if __name__ == "__main__":
    main()
