"""Issue #506: semantic comparison of two review packages (Docker vs native, or run vs run).

Compares, per page: page geometry, source render, barline boxes, measure numbering
(system/measure count, numbers, bboxes), MMR overrides, and final PDF page geometry.
Prints a JSON report; exit 0 only when every gate is equal (or within tolerance).

Page-set gate (fail-fast, review of PR #531): both sides must expose the same non-empty
set of review page IDs, optionally exactly ``--expected-pages N`` of them, and both final
PDFs must have that many pages. Missing files raise instead of being skipped.

Usage: compare_semantic.py <job_a> <job_b> [--expected-pages N]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF

TOL_PX = 0  # exact by default; differences are reported, never hidden


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def max_abs(a, b):
    return max((abs(x - y) for x, y in zip(a, b)), default=0)


def compare_page(a: Path, b: Path) -> dict:
    out: dict = {}
    out["source_png_sha_equal"] = sha(a / "source.png") == sha(b / "source.png")

    ba, bb = load(a / "barlines_review.json"), load(b / "barlines_review.json")
    out["barline_count"] = [len(ba), len(bb)]
    if len(ba) == len(bb):
        diffs = [max_abs(x, y) for x, y in zip(sorted(ba), sorted(bb))]
        out["barline_max_bbox_delta_px"] = max(diffs, default=0)
        out["barline_boxes_differing"] = sum(d > TOL_PX for d in diffs)

    na, nb = load(a / "numbering_final.json"), load(b / "numbering_final.json")
    pa, pb = na["pages"][0], nb["pages"][0]
    out["page_size"] = [[pa["width"], pa["height"]], [pb["width"], pb["height"]]]
    out["system_count"] = [len(pa["systems"]), len(pb["systems"])]
    seq_a = [[m["number"] for m in s["measures"]] for s in pa["systems"]]
    seq_b = [[m["number"] for m in s["measures"]] for s in pb["systems"]]
    out["measure_numbers_equal"] = seq_a == seq_b
    out["measure_count"] = [sum(map(len, seq_a)), sum(map(len, seq_b))]
    if seq_a == seq_b:
        deltas = [
            max_abs(ma["bbox"], mb["bbox"])
            for sa, sb in zip(pa["systems"], pb["systems"])
            for ma, mb in zip(sa["measures"], sb["measures"])
        ]
        out["measure_max_bbox_delta_px"] = max(deltas, default=0)
    out["numbering_metadata_equal"] = na["numbering_metadata"] == nb["numbering_metadata"]
    out["mmr_overrides_equal"] = load(a / "mmr_overrides.json") == load(b / "mmr_overrides.json")
    return out


def compare_pdf(a: Path, b: Path) -> dict:
    da, db = fitz.open(a), fitz.open(b)
    out = {"page_count": [len(da), len(db)]}
    out["page_rects_equal"] = [tuple(p.rect) for p in da] == [tuple(p.rect) for p in db]
    out["rotation_equal"] = [p.rotation for p in da] == [p.rotation for p in db]
    out["drawings_count"] = [sum(len(p.get_drawings()) for p in da), sum(len(p.get_drawings()) for p in db)]
    out["byte_equal"] = sha(a) == sha(b)
    return out


def page_ids(job: Path) -> set[str]:
    root = job / "review" / "pages"
    if not root.is_dir():
        raise SystemExit(f"missing review pages directory: {root}")
    return {p.name for p in root.iterdir() if p.is_dir()}


def single_pdf(job: Path) -> Path:
    found = sorted((job / "final").glob("*_score_numbered.pdf"))
    if len(found) != 1:
        raise SystemExit(f"expected exactly one numbered PDF under {job / 'final'}, found {len(found)}")
    return found[0]


def main() -> int:
    args = sys.argv[1:]
    expected = None
    if "--expected-pages" in args:
        i = args.index("--expected-pages")
        expected = int(args[i + 1])
        del args[i : i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    ja, jb = Path(args[0]), Path(args[1])
    ids_a, ids_b = page_ids(ja), page_ids(jb)
    report = {
        "a": str(ja),
        "b": str(jb),
        "expected_pages": expected,
        "page_ids": {"a_only": sorted(ids_a - ids_b), "b_only": sorted(ids_b - ids_a), "common": len(ids_a & ids_b)},
        "pages": {},
    }
    page_set_ok = bool(ids_a) and ids_a == ids_b and (expected is None or len(ids_a) == expected)
    report["page_set_equal"] = page_set_ok
    for name in sorted(ids_a & ids_b):
        report["pages"][name] = compare_page(ja / "review/pages" / name, jb / "review/pages" / name)
    report["final_pdf"] = compare_pdf(single_pdf(ja), single_pdf(jb))
    pdf = report["final_pdf"]
    pdf_ok = (
        pdf["page_count"][0] == pdf["page_count"][1] == len(ids_a)
        and pdf["page_rects_equal"]
        and pdf["rotation_equal"]
        and pdf["drawings_count"][0] == pdf["drawings_count"][1]
    )
    ok = page_set_ok and pdf_ok and all(
        p["source_png_sha_equal"]
        and p["barline_count"][0] == p["barline_count"][1]
        and p.get("barline_boxes_differing", 1) == 0
        and p["measure_numbers_equal"]
        and p.get("measure_max_bbox_delta_px", 1) <= TOL_PX
        and p["numbering_metadata_equal"]
        and p["mmr_overrides_equal"]
        and p["page_size"][0] == p["page_size"][1]
        and p["system_count"][0] == p["system_count"][1]
        for p in report["pages"].values()
    )
    report["semantic_equal"] = ok
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
