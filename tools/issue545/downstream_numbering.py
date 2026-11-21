#!/usr/bin/env python3
"""Issue #545: final measure-number impact of MMR override candidates (evaluation only).

Reads a ``replay_mmr_variants.py`` report and the retained jobs it names, rebuilds each
score's final numbers per candidate (page start = previous page ``next_number``; each
measure advances by ``1 + skip``), and compares them with

* GT-implied numbers: the same chaining with reviewed #415 GT skips on the job topology;
* independently read printed row starts (``tools/issue415/row_start_samples.json``).

``--validate`` first checks that the rebuild reproduces every retained ``numbering_final.json``
from the retained ``overrides_mmr.json``.  Standard library only; no inference.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text())


def run_dir(root: Path, score: str) -> Path:
    job = next((root / score).glob("job-*"))
    return job / ".engine-retained" / "runs" / job.name


def png_width(path: Path) -> int:
    with open(path, "rb") as handle:
        header = handle.read(24)
    return struct.unpack(">I", header[16:20])[0]


def page_layout(run: Path) -> list[tuple[str, list[tuple[int, int, list[int]]]]]:
    layout = []
    for page in sorted(p.name for p in (run / "intermediate").glob("page_*")):
        base = read(run / "intermediate" / page / "numbering_base.json")
        keys = [
            (si, mi, m["bbox"])
            for si, system in enumerate(base["pages"][0]["systems"])
            for mi, m in enumerate(system["measures"])
        ]
        layout.append((page, keys))
    return layout


def chain(layout, skips_by_page) -> tuple[dict, dict]:
    numbers, next_by_page, current = {}, {}, 1
    for page, keys in layout:
        skips = skips_by_page.get(page, {})
        for si, mi, _bbox in keys:
            numbers[(page, si, mi)] = current
            current += 1 + skips.get((si, mi), 0)
        next_by_page[page] = current
    return numbers, next_by_page


def skips(overrides) -> dict:
    return {(o["system"], o["measure"]): o["skip"] for o in overrides}


def validate(run: Path, layout) -> list[str]:
    by_page = {
        page: skips(
            read(run / "intermediate" / page / "overrides_mmr.json").get("measure_overrides", [])
        )
        for page, _ in layout
    }
    numbers, next_by_page = chain(layout, by_page)
    errors = []
    for page, keys in layout:
        final = read(run / "outputs" / page / "numbering_final.json")
        actual = [m["number"] for s in final["pages"][0]["systems"] for m in s["measures"]]
        if actual != [numbers[(page, si, mi)] for si, mi, _ in keys]:
            errors.append(f"{page}: numbers")
        if final.get("numbering_metadata", {}).get("next_number") != next_by_page[page]:
            errors.append(f"{page}: next_number")
    return errors


def segments(ordered, offsets) -> list[dict]:
    out, cur = [], None
    for key in ordered:
        off = offsets[key]
        if off and cur is None:
            cur = dict(start=list(key), measures=0, max_abs_offset=0, offsets=set())
        if off:
            cur["measures"] += 1
            cur["max_abs_offset"] = max(cur["max_abs_offset"], abs(off))
            cur["offsets"].add(off)
            cur["end"] = list(key)
        elif cur is not None:
            cur["recovery"] = list(key)
            out.append(cur)
            cur = None
    if cur is not None:
        cur["recovery"] = None
        out.append(cur)
    for seg in out:
        seg["offsets"] = sorted(seg["offsets"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--candidates", default="P0,C1,C3i")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument(
        "--data-root", type=Path, default=CODE, help="checkout holding data/evaluation2/images"
    )
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    report = read(a.report)
    cands = a.candidates.split(",")
    gt = {
        (p["score"], p["page"]): p for p in read(CODE / "tools/issue415/reviewed_gt.json")["pages"]
    }
    samples = read(CODE / "tools/issue415/row_start_samples.json")["samples"]
    result = dict(report=str(a.report), candidates=cands, sets={})
    for set_name, data in report["sets"].items():
        root = Path(data["root"])
        by_score: dict[str, dict] = {}
        for rec in data["pages"]:
            by_score.setdefault(rec["score"], {})[rec["page"]] = rec
        set_out = dict(scores={}, totals={c: dict(measures=0, wrong_number=0) for c in cands})
        for score, pages in by_score.items():
            run = run_dir(root, score)
            layout = page_layout(run)
            score_out = dict(validation=validate(run, layout) if a.validate else None)
            gt_skips = {
                page: {(e["system"], e["measure"]): e["skip"] for e in gt[(score, page)]["events"]}
                for page, _ in layout
                if (score, page) in gt
            }
            expected, _ = chain(layout, gt_skips)
            ordered = [(page, si, mi) for page, keys in layout for si, mi, _ in keys]
            finals = {}
            for cand in cands:
                ov = {page: skips(rec["combos"][cand]["overrides"]) for page, rec in pages.items()}
                numbers, _ = chain(layout, ov)
                finals[cand] = numbers
                offsets = {k: numbers[k] - expected[k] for k in ordered}
                wrong = sum(1 for k in ordered if offsets[k])
                rows = []
                for s in samples:
                    if s["score"] != score:
                        continue
                    keys = dict(layout).get(s["page"])
                    first = (
                        next(
                            ((si, mi, b) for si, mi, b in keys if si == s["system"] and mi == 0),
                            None,
                        )
                        if keys
                        else None
                    )
                    if first is None:
                        rows.append(dict(page=s["page"], system=s["system"], identity="missing"))
                        continue
                    scale = png_width(run / "inputs/images" / f"{s['page']}.png") / png_width(
                        a.data_root / s["source_image"]
                    )
                    ref = [v * scale for v in s["first_measure_bbox"]]
                    b = first[2]
                    ix = max(0, min(b[2], ref[2]) - max(b[0], ref[0]))
                    iy = max(0, min(b[3], ref[3]) - max(b[1], ref[1]))
                    union = (
                        (b[2] - b[0]) * (b[3] - b[1])
                        + (ref[2] - ref[0]) * (ref[3] - ref[1])
                        - ix * iy
                    )
                    actual = numbers[(s["page"], s["system"], 0)]
                    rows.append(
                        dict(
                            page=s["page"],
                            system=s["system"],
                            expected=s["expected_row_start"],
                            actual=actual,
                            matches=actual == s["expected_row_start"],
                            identity_iou=round(ix * iy / union, 3) if union else 0.0,
                        )
                    )
                # Each local skip error (vs GT) and how far its cumulative offset carries:
                # until the next local error or the end of the score.
                local = []
                for page, keys in layout:
                    cand_page = ov.get(page, {})
                    gt_page = gt_skips.get(page, {})
                    for si, mi, _ in keys:
                        delta = cand_page.get((si, mi), 0) - gt_page.get((si, mi), 0)
                        if delta:
                            local.append(dict(at=[page, si, mi], delta=delta))
                index = {k: i for i, k in enumerate(ordered)}
                for i, ev in enumerate(local):
                    start = index[tuple(ev["at"])] + 1
                    stop = (
                        index[tuple(local[i + 1]["at"])] + 1 if i + 1 < len(local) else len(ordered)
                    )
                    ev["affected_following_measures"] = stop - start
                    ev["offset_after"] = offsets[ordered[start]] if start < len(ordered) else None
                    ev["next_error_or_end"] = list(ordered[stop - 1]) if stop > start else None
                score_out[cand] = dict(
                    measures=len(ordered),
                    wrong_number=wrong,
                    local_errors=local,
                    segments=segments(ordered, offsets),
                    row_samples=rows,
                )
                set_out["totals"][cand]["measures"] += len(ordered)
                set_out["totals"][cand]["wrong_number"] += wrong
            # Events where candidates disagree, with the downstream numbers they produce.
            diff_events = []
            for page, rec in pages.items():
                cand_skips = {c: skips(rec["combos"][c]["overrides"]) for c in cands}
                keys = set().union(*cand_skips.values()) | set(gt_skips.get(page, {}))
                for key in sorted(keys):
                    vals = {c: cand_skips[c].get(key) for c in cands}
                    if len({str(v) for v in vals.values()}) > 1:
                        diff_events.append(
                            dict(
                                page=page,
                                system=key[0],
                                measure=key[1],
                                gt_skip=gt_skips.get(page, {}).get(key),
                                skips=vals,
                            )
                        )
            score_out["candidate_disagreements"] = diff_events
            score_out["measures_differing_vs_first"] = {
                c: sum(1 for k in ordered if finals[c][k] != finals[cands[0]][k]) for c in cands[1:]
            }
            score_out["segments_vs_first"] = {
                c: segments(ordered, {k: finals[c][k] - finals[cands[0]][k] for k in ordered})
                for c in cands[1:]
            }
            set_out["scores"][score] = score_out
        result["sets"][set_name] = set_out
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=1) + "\n")
    for set_name, s in result["sets"].items():
        print(set_name, json.dumps(s["totals"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
