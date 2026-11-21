#!/usr/bin/env python3
"""Issue #545: MMR-only replay of y-geometry candidates on retained production jobs (evaluation only).

The P0/C1/C2 candidates require the pre-#545 support implementation (schema v1), selected with
``PDFSCORE_CODE``; other trees are rejected unless ``--production-only`` replays P0 alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# PDFSCORE_CODE selects the code tree under test (default: this checkout).
CODE = Path(os.environ.get("PDFSCORE_CODE") or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(CODE))
# The compatibility check lives next to this script, which may differ from the tree under test.
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(CODE)
import cv2  # noqa: E402
import torch  # noqa: E402
from issue545_support_compat import require_geometry_support  # noqa: E402

import src.pipeline.mmr_support_reuse as msr  # noqa: E402
from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor  # noqa: E402
from src.measure_numbering.rapidocr_provider import collect_rapidocr_providers, create_mmr_rapidocr  # noqa: E402
from tools.issue264.run_phase_c_mmr_regression import score_overrides  # noqa: E402

ORIG_RAW = msr._raw_mapped_bbox


def raw_phase_a(base, candidates):
    return list(base), "single_current_staff"


def raw_union(base, candidates):
    mapped, mode = ORIG_RAW(base, candidates)
    return [
        min(base[0], mapped[0]),
        min(base[1], mapped[1]),
        max(base[2], mapped[2]),
        max(base[3], mapped[3]),
    ], mode


GEOM = {"P0": ORIG_RAW, "C1": raw_phase_a, "C2": raw_union}


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def score_of(o):
    return float(re.search(r"OCR\((-?[0-9.]+)\)", o["comment"]).group(1))


def merge(a, b, keep_singletons):
    A = {(o["system"], o["measure"]): o for o in a}
    B = {(o["system"], o["measure"]): o for o in b}
    out = []
    for k in sorted(set(A) | set(B)):
        x, y = A.get(k), B.get(k)
        if x and y:
            out.append(x if x["skip"] == y["skip"] or score_of(x) >= score_of(y) else y)
        elif keep_singletons:
            out.append(x or y)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", required=True, help="name=root:score[,score]")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--production-only",
        action="store_true",
        help="replay only P0 (this tree's production MMR); required for #545+ support (schema v2)",
    )
    a = ap.parse_args()
    require_geometry_support(msr, production_only=a.production_only)
    geom = {"P0": ORIG_RAW} if a.production_only else GEOM
    if a.out.exists():
        raise SystemExit(f"refusing to reuse {a.out}")
    assert torch.cuda.is_available()
    engine = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(engine)
    assert providers and all("CUDAExecutionProvider" in v for v in providers.values()), providers
    dev = torch.device("cuda")
    model = CODE / "models/mmr/mmr_classifier_best.pth"
    proc = MMRProcessor(
        Path("unused"),
        dev,
        classifier=MMRClassifier(model, dev),
        ocr_engine=MMROCREngine(ocr_engine=engine),
    )
    gt = {
        (p["score"], p["page"]): p for p in read(CODE / "tools/issue415/reviewed_gt.json")["pages"]
    }
    report = dict(
        providers=providers,
        model_sha256=sha(model),
        mmr_sha256=sha(CODE / "src/measure_numbering/mmr.py"),
        support_sha256=sha(CODE / "src/pipeline/mmr_support_reuse.py"),
        runner_sha256=sha(__file__),
        code_root=str(CODE),
        support_schema=msr.SCHEMA_VERSION,
        production_only=a.production_only,
        sets={},
    )
    for spec in a.set:
        name, rest = spec.split("=", 1)
        root, scores = rest.split(":", 1)
        totals, pages = {}, []
        for score in scores.split(","):
            job = next((Path(root) / score).glob("job-*"))
            run = job / ".engine-retained/runs" / job.name
            hyb = next((run / "hybrid_output").glob("job-*"))
            for pi, page in enumerate(
                sorted(p.name for p in (run / "intermediate").glob("page_*"))
            ):
                if (score, page) not in gt:
                    continue
                base_path = run / "intermediate" / page / "numbering_base.json"
                base = read(base_path)
                mask = (
                    hyb
                    / "current_support/images"
                    / page
                    / "artifacts/current_homr/batch"
                    / page
                    / f"{page}_staff_mask.png"
                )
                img = run / "inputs/images" / f"{page}.png"
                image = cv2.imread(str(img))
                h, w = image.shape[:2]
                exp = [
                    dict(page=pi, system=e["system"], measure=e["measure"], skip=e["skip"])
                    for e in gt[(score, page)]["events"]
                ]
                ov = {}
                for g, fn in geom.items():
                    msr._raw_mapped_bbox = fn
                    try:
                        sup = msr.build_mmr_support_data(base, mask)
                    finally:
                        msr._raw_mapped_bbox = ORIG_RAW
                    ov[g] = proc._process_page_with_support(
                        page_data=base,
                        support=sup,
                        image=image,
                        page_num=pi + 1,
                        image_width=w,
                        image_height=h,
                        debug_img=None,
                    )
                retained = read(run / "intermediate" / page / "overrides_mmr.json").get(
                    "measure_overrides", []
                )
                ov["retained"] = retained
                if "C1" in ov:
                    ov["C3u"] = merge(ov["P0"], ov["C1"], True)
                    ov["C3i"] = merge(ov["P0"], ov["C1"], False)
                ov["F"] = [o for o in ov["P0"] if score_of(o) > 0]
                rec = dict(
                    score=score,
                    page=page,
                    p0_equals_retained=sorted(map(str, ov["P0"])) == sorted(map(str, retained)),
                    inputs=dict(numbering_base=sha(base_path), mask=sha(mask), image=sha(img)),
                    combos={},
                )
                for k, v in ov.items():
                    s = score_overrides(exp, dict(measure_overrides=v))
                    neg = sum(1 for o in v if score_of(o) <= 0)
                    rec["combos"][k] = dict(counts=s["counts"], neg_accepted=neg, overrides=v)
                    t = totals.setdefault(k, {})
                    for kk, n in {**s["counts"], "neg_accepted": neg}.items():
                        t[kk] = t.get(kk, 0) + n
                pages.append(rec)
                print(name, score, page, "P0==retained", rec["p0_equals_retained"], flush=True)
        report["sets"][name] = dict(root=root, totals=totals, pages=pages)
        print("TOTALS", name, json.dumps(totals), flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
