#!/usr/bin/env python3
"""Issue #522: audit every baseline box admitted or rejected by x4 staff-piece support (Full68).

For each multi-staff original-HOMR box not supported by x4 IoU it records the staff
pieces, the system membership of each piece (from the control final numbering
staves), the supporting x4 stroke height in staff units, and what the final
x4_staff_piece predictions contain at that x (GT-matched TP / extra / none).
Read-only on retained artifacts; no inference.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
ROOT = Path("/workspace")
sys.path.insert(0, str(CODE))

from src.common import barline_iou  # noqa: E402
from src.common.barline_strokes import normalize_staff_stroke  # noqa: E402
from src.pipeline.detection.profile_sources import _baseline_staff_mask  # noqa: E402
from src.pipeline.steps.hybrid_consensus import (  # noqa: E402
    X4_PIECE_CENTER_UNITS,
    X4_PIECE_MIN_CONTAINED,
    X4_PIECE_MIN_HEIGHT_UNITS,
    load_json_boxes,
    staff_regions_from_mask,
    x4_staff_piece_support,
)
from tools.issue120.eval_full68_from_intermediates import SCORES  # noqa: E402

RUN = ROOT / "logs/issue409/full68-numbering-20261009/candidate"
X4 = ROOT / "logs/issue522/full68/x4_staff_piece_prodhelpers/candidate"
FINAL = ROOT / "logs/issue519/downstream-20261108/control"


def supporting(piece, sr, unit):
    cx = (piece[0] + piece[2]) / 2
    best = None
    for s in sr:
        h = s[3] - s[1]
        if abs((s[0] + s[2]) / 2 - cx) > X4_PIECE_CENTER_UNITS * unit:
            continue
        ov = min(piece[3], s[3]) - max(piece[1], s[1])
        contained = ov / h if h else 0
        cand = dict(
            stroke=list(s),
            height_units=round(h / unit, 2),
            contained=round(contained, 2),
            piece_coverage=round(max(0, ov) / max(1, piece[3] - piece[1]), 2),
        )
        if h >= X4_PIECE_MIN_HEIGHT_UNITS * unit and contained >= X4_PIECE_MIN_CONTAINED:
            return cand
        best = best or cand
    return dict(none=True, nearest=best)


def system_of(piece, systems):
    for si, staves in enumerate(systems):
        for st in staves:
            if min(piece[3], st[3]) - max(piece[1], st[1]) > 0:
                return si
    return None


def main() -> int:
    out = []
    for score, pages in SCORES.items():
        hyb = next((RUN / score / "hybrid_output").iterdir())
        for page in pages:
            sup = json.loads((hyb / "current_support" / score / page / "result.json").read_text())
            base = load_json_boxes(hyb / "baseline/batch" / page / f"{page}_detections.json")
            sr = load_json_boxes(Path(sup["current_sr_detection"]))
            image = ROOT / "data/evaluation2/images" / score / f"{page}.png"
            regions = staff_regions_from_mask(
                _baseline_staff_mask(hyb / "baseline/batch" / page, page), image
            )
            final = json.loads(
                (FINAL / score / "outputs" / page / "numbering_final.json").read_text()
            )
            systems = [[st["bbox"] for st in s["staves"]] for s in final["pages"][0]["systems"]]
            preds = json.loads((X4 / score / page / "predictions.json").read_text())
            gt = [
                g["barline_location"]
                for g in json.loads(
                    (
                        ROOT / f"data/evaluation2/annotations/{score}/{page}/boxes_sorted.json"
                    ).read_text()
                )
            ]
            for b in base:
                if any(barline_iou(b, r) > 0.5 for r in sr):
                    continue
                pieces = normalize_staff_stroke(tuple(b), regions)
                if pieces == [(-1, tuple(b))]:
                    continue
                admitted = x4_staff_piece_support(b, sr, regions)
                rows = []
                for i, p in pieces:
                    unit = regions[i].unit_size
                    final_hits = [
                        q
                        for q in preds
                        if abs((q[0] + q[2]) / 2 - (p[0] + p[2]) / 2) <= 0.5 * unit
                        and min(q[3], p[3]) - max(q[1], p[1]) > 0
                    ]
                    gt_hits = [
                        g
                        for g in gt
                        if abs((g[0] + g[2]) / 2 - (p[0] + p[2]) / 2) <= 0.5 * unit
                        and min(g[3], p[3]) - max(g[1], p[1]) > 0
                    ]
                    rows.append(
                        dict(
                            staff=i,
                            piece=list(p),
                            unit=unit,
                            system=system_of(p, systems),
                            support=supporting(p, sr, unit),
                            final_preds=final_hits,
                            gt=gt_hits,
                        )
                    )
                out.append(
                    dict(
                        score=score,
                        page=page,
                        box=list(b),
                        admitted=admitted,
                        staves=len(pieces),
                        systems=sorted({r["system"] for r in rows}, key=str),
                        pieces=rows,
                    )
                )
    adm = [o for o in out if o["admitted"]]
    summary = dict(
        multi_staff_boxes_without_iou_support=len(out),
        admitted=len(adm),
        admitted_by_staff_count={
            k: sum(o["staves"] == k for o in adm) for k in sorted({o["staves"] for o in adm})
        },
        admitted_cross_system=[
            (o["score"], o["page"], o["box"], o["systems"])
            for o in adm
            if len(o["systems"]) != 1 or None in o["systems"]
        ],
        admitted_pieces_without_gt=[
            (o["score"], o["page"], r["piece"], r["final_preds"])
            for o in adm
            for r in o["pieces"]
            if not r["gt"]
        ],
        admitted_min_support_height_units=min(
            r["support"]["height_units"] for o in adm for r in o["pieces"]
        ),
        admitted_min_piece_coverage=min(
            r["support"]["piece_coverage"] for o in adm for r in o["pieces"]
        ),
        rejected_partial_support=sum(
            1
            for o in out
            if not o["admitted"] and any("none" not in r["support"] for r in o["pieces"])
        ),
    )
    path = ROOT / "logs/issue522/risk/staff_piece_audit.json"
    path.write_text(json.dumps(dict(summary=summary, boxes=out), indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
