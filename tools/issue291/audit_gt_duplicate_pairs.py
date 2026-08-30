#!/usr/bin/env python3
"""Temporary Issue #291 audit: reproduce #274 P1/P3 pair classification."""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GT_ROOT = ROOT / "data/evaluation2/annotations"
DECLARED_MULTI_TYPES = {"double_barline", "end_barline", "repeat"}
HIGH_Y_OVERLAP = 0.70
SAME_INK_X_OVERLAP = 0.25
CLOSE_X_CENTER_REVIEW = 15.0
GUI_X_CENTER_TOL = 3.0


def bbox(row):
    return tuple(int(round(float(v))) for v in row["barline_location"][:4])


def overlap(a1, a2, b1, b2):
    return max(0, min(a2, b2) - max(a1, b1))


def metrics(a, b):
    ax1, ay1, ax2, ay2 = bbox(a)
    bx1, by1, bx2, by2 = bbox(b)
    aw, bw = max(1, ax2 - ax1), max(1, bx2 - bx1)
    ah, bh = max(1, ay2 - ay1), max(1, by2 - by1)
    xo = overlap(ax1, ax2, bx1, bx2)
    yo = overlap(ay1, ay2, by1, by2)
    return {
        "x_center_delta": abs((ax1 + ax2) / 2 - (bx1 + bx2) / 2),
        "x_overlap_over_min_width": xo / min(aw, bw),
        "y_overlap_over_min_height": yo / min(ah, bh),
    }


def main():
    p1, p3 = [], []
    raw_gt_count = 0
    pages = sorted(GT_ROOT.glob("*/page_*/boxes_sorted.json"))
    for path in pages:
        score, page = path.parent.parent.name, path.parent.name
        rows = json.loads(path.read_text(encoding="utf-8"))
        raw_gt_count += len(rows)
        for (ia, a), (ib, b) in combinations(enumerate(rows), 2):
            m = metrics(a, b)
            ta = str(a.get("barline_type") or "barline")
            tb = str(b.get("barline_type") or "barline")
            both_plain = ta == tb == "barline"
            if (
                both_plain
                and m["x_overlap_over_min_width"] >= SAME_INK_X_OVERLAP
                and m["y_overlap_over_min_height"] >= HIGH_Y_OVERLAP
            ):
                p1.append({
                    "score": score,
                    "page": page,
                    "gt_file": str(path.relative_to(ROOT)),
                    "a": {"index": ia, "bbox": list(bbox(a)), "measure_number": a.get("measure_number"), "barline_type": ta},
                    "b": {"index": ib, "bbox": list(bbox(b)), "measure_number": b.get("measure_number"), "barline_type": tb},
                    "metrics": m,
                    "matches_existing_gui_auto_dedup": m["x_center_delta"] <= GUI_X_CENTER_TOL and m["y_overlap_over_min_height"] >= HIGH_Y_OVERLAP,
                })
            elif (
                ({ta, tb} & DECLARED_MULTI_TYPES)
                and m["x_center_delta"] <= CLOSE_X_CENTER_REVIEW
                and m["y_overlap_over_min_height"] >= HIGH_Y_OVERLAP
            ):
                p3.append({
                    "score": score,
                    "page": page,
                    "gt_file": str(path.relative_to(ROOT)),
                    "a": {"index": ia, "bbox": list(bbox(a)), "measure_number": a.get("measure_number"), "barline_type": ta},
                    "b": {"index": ib, "bbox": list(bbox(b)), "measure_number": b.get("measure_number"), "barline_type": tb},
                    "metrics": m,
                })
    payload = {
        "raw_gt_count": raw_gt_count,
        "page_count": len(pages),
        "p1_count": len(p1),
        "p1_page_count": len({(r["score"], r["page"]) for r in p1}),
        "p1": p1,
        "p3_pair_count": len(p3),
        "p3": p3,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if (len(pages), raw_gt_count, len(p1), payload["p1_page_count"], len(p3)) != (68, 3580, 12, 10, 51):
        raise SystemExit("Issue #274 audit invariant mismatch")


if __name__ == "__main__":
    main()
