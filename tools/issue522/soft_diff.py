#!/usr/bin/env python3
"""Issue #522: identify soft-match predictions that differ between control and x4_staff_piece.

Uses the accepted #416 matcher (center_anchor, vov 0.5, xdist 0.5 unit) on retained
predictions only.  For every soft prediction present in one variant but not the other it
records the nearest GT, the nearest prediction in the other variant, the staff region and
the final measure boundary at that x, so the change can be judged semantically.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
ROOT = Path("/workspace")
sys.path.insert(0, str(CODE))

from src.common.barline_evaluation import greedy_barline_match  # noqa: E402
from tools.issue120 import eval_full68_from_intermediates as ev  # noqa: E402

CONTROL = ROOT / "logs/issue519/ablation/control/candidate"
X4 = ROOT / "logs/issue522/full68/x4_staff_piece_prodhelpers/candidate"
FINAL = {
    "control": ROOT / "logs/issue519/downstream-20261108/control",
    "x4": ROOT / "logs/issue522/downstream/x4_staff_piece",
}


def softs(preds, gt, unit):
    m = greedy_barline_match(
        preds,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        unit_size=unit,
        xdist_unit_ratio=0.5,
    )
    return [tuple(preds[item.pred_index]) for item in m.soft_matches], {
        tuple(preds[item.pred_index]): item.reason for item in m.soft_matches
    }


def main() -> int:
    units = ev.load_page_staff_units(ROOT / "data/evaluation2/staff_units.json")
    rows, totals = [], {"control": 0, "x4": 0}
    for score, pages in ev.SCORES.items():
        for page in pages:
            unit = ev.require_page_staff_unit(units, score, page).unit_size
            gt = ev.boxes_from_gt(
                json.loads(
                    (
                        ROOT / f"data/evaluation2/annotations/{score}/{page}/boxes_sorted.json"
                    ).read_text()
                )
            )
            pc = json.loads((CONTROL / score / page / "predictions.json").read_text())
            px = json.loads((X4 / score / page / "predictions.json").read_text())
            sc, mc = softs(pc, gt, unit)
            sx, mx = softs(px, gt, unit)
            totals["control"] += len(sc)
            totals["x4"] += len(sx)
            for name, mine, other_preds in (
                ("only_control", set(sc) - set(sx), px),
                ("only_x4", set(sx) - set(sc), pc),
            ):
                for b in sorted(mine):
                    cx = (b[0] + b[2]) / 2
                    near_gt = min(
                        gt, key=lambda g: abs((g[0] + g[2]) / 2 - cx) + abs(g[1] - b[1]) / 4
                    )
                    near_other = min(
                        other_preds,
                        key=lambda q: abs((q[0] + q[2]) / 2 - cx) + abs(q[1] - b[1]) / 4,
                    )
                    fin = json.loads(
                        (
                            FINAL["control"] / score / "outputs" / page / "numbering_final.json"
                        ).read_text()
                    )
                    boundary = None
                    for si, s in enumerate(fin["pages"][0]["systems"]):
                        for m in s["measures"]:
                            for edge in (m["bbox"][0], m["bbox"][2]):
                                if (
                                    abs(edge - cx) <= unit
                                    and m["bbox"][1] <= b[3]
                                    and m["bbox"][3] >= b[1]
                                ):
                                    boundary = dict(system=si, number=m["number"], edge=edge)
                    reason = (mc if name == "only_control" else mx).get(b)
                    rows.append(
                        dict(
                            kind=name,
                            score=score,
                            page=page,
                            box=list(b),
                            unit=unit,
                            soft_reason=reason,
                            nearest_gt=list(near_gt),
                            nearest_gt_dx_units=round(
                                abs((near_gt[0] + near_gt[2]) / 2 - cx) / unit, 2
                            ),
                            nearest_other=list(near_other),
                            nearest_other_dx_units=round(
                                abs((near_other[0] + near_other[2]) / 2 - cx) / unit, 2
                            ),
                            final_boundary=boundary,
                        )
                    )
    out = dict(totals=totals, rows=rows)
    path = ROOT / "logs/issue522/risk/soft_diff.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(totals))
    for r in rows:
        print(
            r["kind"],
            r["score"],
            r["page"],
            r["box"],
            "gt_dx",
            r["nearest_gt_dx_units"],
            "other_dx",
            r["nearest_other_dx_units"],
            r["nearest_other"],
            "boundary",
            r["final_boundary"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
