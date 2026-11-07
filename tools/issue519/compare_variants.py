#!/usr/bin/env python3
"""Issue #519: per-page semantic diff of control vs no_omr replay outputs.

Compares detector metrics, new/lost FN, ordered per-system measure counts, system
topology (system/staff membership), measure numbers and measure geometry from
``numbering_base.json``.  Geometry deltas are expressed in staff ``unit_size`` where
available.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def systems(base):
    return base["pages"][0]["systems"]


def bbox(obj):
    for key in ("bbox", "box"):
        if key in obj:
            b = obj[key]
            return [b["x1"], b["y1"], b["x2"], b["y2"]] if isinstance(b, dict) else list(b)
    return None


def page_diff(c_base, n_base):
    cs, ns = systems(c_base), systems(n_base)
    out = {
        "system_count": [len(cs), len(ns)],
        "measure_counts": [[len(s["measures"]) for s in cs], [len(s["measures"]) for s in ns]],
        "staff_counts": [
            [len(s.get("staves", [])) for s in cs],
            [len(s.get("staves", [])) for s in ns],
        ],
    }
    out["counts_equal"] = out["measure_counts"][0] == out["measure_counts"][1]
    out["topology_equal"] = (
        out["system_count"][0] == out["system_count"][1]
        and out["staff_counts"][0] == out["staff_counts"][1]
    )
    numbers = [[[m.get("number") for m in s["measures"]] for s in x] for x in (cs, ns)]
    out["numbers_equal"] = numbers[0] == numbers[1]
    geo = []
    if out["counts_equal"]:
        for si, (a, b) in enumerate(zip(cs, ns)):
            for mi, (ma, mb) in enumerate(zip(a["measures"], b["measures"])):
                ba, bb = bbox(ma), bbox(mb)
                if ba != bb:
                    geo.append(
                        {
                            "system": si,
                            "measure": mi,
                            "control": ba,
                            "no_omr": bb,
                            "max_abs_px": max(abs(x - y) for x, y in zip(ba, bb))
                            if ba and bb
                            else None,
                        }
                    )
    out["geometry_changes"] = geo
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--no-omr", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    cr, nr = read(a.control / "report.json"), read(a.no_omr / "report.json")
    crow = {(r["score"], r["page"]): r for r in cr["pages"]}
    pages = []
    for r in nr["pages"]:
        key = (r["score"], r["page"])
        c = crow[key]
        cb = read(a.control / "candidate" / key[0] / key[1] / "numbering_base.json")
        nb = read(a.no_omr / "candidate" / key[0] / key[1] / "numbering_base.json")
        cp = read(a.control / "candidate" / key[0] / key[1] / "predictions.json")
        np_ = read(a.no_omr / "candidate" / key[0] / key[1] / "predictions.json")
        cset, nset = set(map(tuple, cp)), set(map(tuple, np_))
        d = {
            "score": key[0],
            "page": key[1],
            "metrics": {"control": c["metrics"], "no_omr": r["metrics"]},
            "fn_new": [f for f in r["fn_gt"] if f not in c["fn_gt"]],
            "fn_recovered": [f for f in c["fn_gt"] if f not in r["fn_gt"]],
            "predictions_only_control": sorted(cset - nset),
            "predictions_only_no_omr": sorted(nset - cset),
            "hybrid": [c["hybrid"]["hybrid"], r["hybrid"]["hybrid"]],
        }
        if cb != nb:
            d.update(page_diff(cb, nb))
        d["changed"] = bool(
            d["predictions_only_control"] or d["predictions_only_no_omr"] or cb != nb
        )
        pages.append(d)
    changed = [d for d in pages if d["changed"]]
    summary = {
        "control_totals": cr["summary"]["totals"],
        "no_omr_totals": nr["summary"]["totals"],
        "control_measures": cr["summary"]["physical_measures"],
        "no_omr_measures": nr["summary"]["physical_measures"],
        "pages_changed": len(changed),
        "pages_prediction_changed": sum(
            bool(d["predictions_only_control"] or d["predictions_only_no_omr"]) for d in pages
        ),
        "pages_numbering_base_changed": sum("system_count" in d for d in pages),
        "pages_measure_count_changed": sum(
            ("counts_equal" in d) and not d["counts_equal"] for d in pages
        ),
        "pages_topology_changed": sum(
            ("topology_equal" in d) and not d["topology_equal"] for d in pages
        ),
        "pages_numbers_changed": sum(
            ("numbers_equal" in d) and not d["numbers_equal"] for d in pages
        ),
        "pages_geometry_only_changed": sum(
            ("counts_equal" in d) and d["counts_equal"] and bool(d["geometry_changes"])
            for d in pages
        ),
        "predictions_removed_total": sum(len(d["predictions_only_control"]) for d in pages),
        "predictions_added_total": sum(len(d["predictions_only_no_omr"]) for d in pages),
        "fn_new": [(d["score"], d["page"], f) for d in pages for f in d["fn_new"]],
        "fn_recovered": [(d["score"], d["page"], f) for d in pages for f in d["fn_recovered"]],
    }
    a.output.write_text(json.dumps({"summary": summary, "changed_pages": changed}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    for d in changed:
        print(
            d["score"],
            d["page"],
            "hybrid",
            d["hybrid"],
            "-pred",
            len(d["predictions_only_control"]),
            "+pred",
            len(d["predictions_only_no_omr"]),
            "counts",
            d.get("measure_counts"),
            "topo_eq",
            d.get("topology_equal"),
            "num_eq",
            d.get("numbers_equal"),
            "geo",
            len(d.get("geometry_changes", [])),
            "maxpx",
            max([g["max_abs_px"] or 0 for g in d.get("geometry_changes", [])] or [0]),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
