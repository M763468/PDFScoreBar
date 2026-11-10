#!/usr/bin/env python3
"""Issue #522 (harness from #519): compare control vs no_omr final numbering, row labels and rendered pages.

Physical identity is established geometrically, never by array index alone:
systems are paired by staff-bbox IoU (one-to-one), and measures inside paired systems
are paired by horizontal-interval IoU (one-to-one, >=0.5).  For every paired
measure the final number, applied increment (next - number - 1) and bbox delta (px and
staff unit) are compared.  Page start/next numbers, reviewed-GT error identities and
row-start labels (text and placement) are compared; rendered page PNGs are diffed.
Optionally the control finals are compared with an accepted reference run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def read(p):
    return json.loads(Path(p).read_text())


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def xiou(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    union = max(a[2], b[2]) - min(a[0], b[0])
    return inter / union if union else 0.0


def pair(xs, ys, score, minimum):
    cand = sorted(
        ((score(a, b), i, j) for i, a in enumerate(xs) for j, b in enumerate(ys)), reverse=True
    )
    used_i, used_j, out = set(), set(), []
    for s, i, j in cand:
        if s < minimum or i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        out.append((i, j, s))
    return sorted(out)


def sysbox(system):
    boxes = [s["bbox"] for s in system["staves"]]
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def flat_next(pages):
    """(page, system, measure) -> applied increment using score-wide next numbers."""
    seq = []
    for pi, page in enumerate(pages):
        for si, system in enumerate(page["pages"][0]["systems"]):
            for mi, m in enumerate(system["measures"]):
                seq.append(((pi, si, mi), m["number"]))
    out = {}
    for k, (key, number) in enumerate(seq):
        nxt = seq[k + 1][1] if k + 1 < len(seq) else pages[-1]["numbering_metadata"]["next_number"]
        out[key] = nxt - number - 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--control", type=Path, required=True)
    ap.add_argument("--no-omr", type=Path, required=True)
    ap.add_argument("--units", type=Path, required=True)
    ap.add_argument("--accepted-reference", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    units = read(a.units)["pages"]
    crep, nrep = read(a.control / "report.json"), read(a.no_omr / "report.json")
    pages_out, totals = (
        [],
        dict(
            pages=0,
            systems_control=0,
            systems_no_omr=0,
            systems_paired=0,
            staff_topology_diff_pages=0,
            measures_control=0,
            measures_no_omr=0,
            measures_paired=0,
            measures_unpaired=0,
            number_diffs=0,
            increment_diffs=0,
            page_start_next_diffs=0,
            bbox_changed=0,
            bbox_max_px=0,
            bbox_max_unit=0.0,
            row_label_text_diffs=0,
            row_label_moved=0,
            row_label_max_move_px=0,
            render_pixel_diff_pages=0,
            accepted_reference_diff_pages=0,
        ),
    )
    for cr, nr in zip(crep["reports"], nrep["reports"]):
        score = cr["score"]
        assert score == nr["score"]
        cfin = [
            read(a.control / score / "outputs" / r["page"] / "numbering_final.json")
            for r in cr["page_render"]
        ]
        nfin = [
            read(a.no_omr / score / "outputs" / r["page"] / "numbering_final.json")
            for r in nr["page_render"]
        ]
        cinc, ninc = flat_next(cfin), flat_next(nfin)
        cgt = sorted(json.dumps(e, sort_keys=True) for e in cr["audit"]["gt_increment_errors"])
        ngt = sorted(json.dumps(e, sort_keys=True) for e in nr["audit"]["gt_increment_errors"])
        for pi, (crow, nrow, cf, nf) in enumerate(
            zip(cr["page_render"], nr["page_render"], cfin, nfin)
        ):
            page = crow["page"]
            unit = units[f"{score}/{page}"]["unit_size"]
            cs, ns = cf["pages"][0]["systems"], nf["pages"][0]["systems"]
            sp = pair([sysbox(s) for s in cs], [sysbox(s) for s in ns], iou, 0.5)
            rec = dict(
                score=score,
                page=page,
                systems=[len(cs), len(ns)],
                systems_paired=len(sp),
                staff_topology_equal=[[st["bbox"] for st in s["staves"]] for s in cs]
                == [[st["bbox"] for st in s["staves"]] for s in ns],
                start_next=[
                    [
                        cf["numbering_metadata"]["start_number"],
                        cf["numbering_metadata"]["next_number"],
                    ],
                    [
                        nf["numbering_metadata"]["start_number"],
                        nf["numbering_metadata"]["next_number"],
                    ],
                ],
                measure_diffs=[],
                unpaired=[],
            )
            for si, sj, _ in sp:
                cm, nm = cs[si]["measures"], ns[sj]["measures"]
                mp = pair([m["bbox"] for m in cm], [m["bbox"] for m in nm], xiou, 0.5)
                totals["measures_paired"] += len(mp)
                pi_set, pj_set = {i for i, _, _ in mp}, {j for _, j, _ in mp}
                rec["unpaired"] += [
                    ("control", si, i, cm[i]) for i in range(len(cm)) if i not in pi_set
                ]
                rec["unpaired"] += [
                    ("no_omr", sj, j, nm[j]) for j in range(len(nm)) if j not in pj_set
                ]
                for i, j, _ in mp:
                    ca, na = cm[i], nm[j]
                    delta = max(abs(x - y) for x, y in zip(ca["bbox"], na["bbox"]))
                    d = dict(
                        system=[si, sj],
                        measure=[i, j],
                        number=[ca["number"], na["number"]],
                        increment=[cinc[(pi, si, i)], ninc[(pi, sj, j)]],
                        bbox=[ca["bbox"], na["bbox"]],
                        max_px=delta,
                        max_unit=round(delta / unit, 4),
                    )
                    if ca["number"] != na["number"]:
                        totals["number_diffs"] += 1
                    if d["increment"][0] != d["increment"][1]:
                        totals["increment_diffs"] += 1
                    if delta:
                        totals["bbox_changed"] += 1
                        totals["bbox_max_px"] = max(totals["bbox_max_px"], delta)
                        totals["bbox_max_unit"] = max(totals["bbox_max_unit"], delta / unit)
                    if (
                        delta
                        or ca["number"] != na["number"]
                        or d["increment"][0] != d["increment"][1]
                    ):
                        rec["measure_diffs"].append(d)
            totals["measures_unpaired"] += len(rec["unpaired"])
            totals["pages"] += 1
            totals["systems_control"] += len(cs)
            totals["systems_no_omr"] += len(ns)
            totals["systems_paired"] += len(sp)
            totals["measures_control"] += sum(len(s["measures"]) for s in cs)
            totals["measures_no_omr"] += sum(len(s["measures"]) for s in ns)
            totals["staff_topology_diff_pages"] += not rec["staff_topology_equal"]
            totals["page_start_next_diffs"] += rec["start_next"][0] != rec["start_next"][1]
            # Row-start labels and rendered pixels.
            rec["render_status"] = [crow["status"], nrow["status"]]
            if crow["status"] == nrow["status"] == "rendered":
                moves = []
                for x, y in zip(crow["rows"], nrow["rows"]):
                    if x.get("text", x.get("row_start_measure_number")) != y.get(
                        "text", y.get("row_start_measure_number")
                    ):
                        totals["row_label_text_diffs"] += 1
                    bx, by = (
                        x.get("label_bbox") or x.get("bbox"),
                        y.get("label_bbox") or y.get("bbox"),
                    )
                    if bx and by and bx != by:
                        mv = max(abs(p - q) for p, q in zip(bx, by))
                        moves.append(dict(row=x.get("row_id"), control=bx, no_omr=by, max_px=mv))
                        totals["row_label_moved"] += 1
                        totals["row_label_max_move_px"] = max(totals["row_label_max_move_px"], mv)
                rec["row_label_moves"] = moves
                rec["row_count"] = [len(crow["rows"]), len(nrow["rows"])]
                ci = np.asarray(
                    Image.open(a.control / score / "review/page_render" / f"{page}.png").convert(
                        "L"
                    )
                )
                ni = np.asarray(
                    Image.open(a.no_omr / score / "review/page_render" / f"{page}.png").convert("L")
                )
                diff = np.argwhere(ci != ni)
                rec["render_pixel_diff"] = int(len(diff))
                if len(diff):
                    totals["render_pixel_diff_pages"] += 1
                    rec["render_diff_bbox"] = [
                        int(diff[:, 1].min()),
                        int(diff[:, 0].min()),
                        int(diff[:, 1].max()),
                        int(diff[:, 0].max()),
                    ]
            if a.accepted_reference:
                ref = read(a.accepted_reference / score / "outputs" / page / "numbering_final.json")
                rec["control_equals_accepted_final"] = ref == cf
                totals["accepted_reference_diff_pages"] += ref != cf
            if (
                rec["measure_diffs"]
                or rec["unpaired"]
                or not rec["staff_topology_equal"]
                or rec["start_next"][0] != rec["start_next"][1]
                or rec.get("render_pixel_diff")
                or rec.get("row_label_moves")
            ):
                pages_out.append(rec)
        totals.setdefault("gt_error_identity_diff_scores", 0)
        totals["gt_error_identity_diff_scores"] += cgt != ngt
    totals["bbox_max_unit"] = round(totals["bbox_max_unit"], 4)
    totals["downstream_totals"] = dict(control=crep["totals"], no_omr=nrep["totals"])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(dict(totals=totals, changed_pages=pages_out), indent=1) + "\n")
    print(json.dumps({k: v for k, v in totals.items() if k != "downstream_totals"}, indent=1))
    for r in pages_out:
        print(
            r["score"],
            r["page"],
            "measure_diffs",
            len(r["measure_diffs"]),
            "unpaired",
            len(r["unpaired"]),
            "row_moves",
            len(r.get("row_label_moves", [])),
            "pix",
            r.get("render_pixel_diff"),
            "nums_diff",
            sum(d["number"][0] != d["number"][1] for d in r["measure_diffs"]),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
