#!/usr/bin/env python3
"""Issue #545: MMR-only replay that swaps Phase-A numbering_base and x4 HOMR staff mask.

For every page of two retained job runs (baseline / candidate) this builds the production MMR
support sidecar (``build_mmr_support_data``) from each combination of
{baseline, candidate} numbering_base x {baseline, candidate} current-x4 HOMR staff mask, runs the
production ``MMRProcessor`` on the retained source page image, and scores each combination
against the reviewed #415 GT with the #264 scorer.  Evaluation only; production code is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODE))
os.chdir(CODE)

import cv2  # noqa: E402
import torch  # noqa: E402

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor  # noqa: E402
from src.measure_numbering.rapidocr_provider import (  # noqa: E402
    collect_rapidocr_providers,
    create_mmr_rapidocr,
)
from src.pipeline.mmr_support_reuse import build_mmr_support_data  # noqa: E402
from tools.issue264.run_phase_c_mmr_regression import score_overrides  # noqa: E402


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_dir(job_root: Path) -> Path:
    job = next(job_root.glob("job-*"))
    return job / ".engine-retained" / "runs" / job.name


def page_inputs(run: Path, page: str) -> dict:
    hybrid = next((run / "hybrid_output").glob("job-*"))
    mask = (
        hybrid
        / "current_support/images"
        / page
        / "artifacts/current_homr/batch"
        / page
        / f"{page}_staff_mask.png"
    )
    return dict(
        numbering_base=run / "intermediate" / page / "numbering_base.json",
        mask=mask,
        retained_overrides=run / "intermediate" / page / "overrides_mmr.json",
        image=run / "inputs/images" / f"{page}.png",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-root", type=Path, required=True, help="dir with <score>/job-*")
    ap.add_argument("--candidate-root", type=Path, required=True)
    ap.add_argument("--scores", nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to reuse {a.out}")
    assert torch.cuda.is_available()
    engine = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(engine)
    assert providers and all("CUDAExecutionProvider" in v for v in providers.values()), providers
    device = torch.device("cuda")
    model = CODE / "models/mmr/mmr_classifier_best.pth"
    processor = MMRProcessor(
        Path("unused"),
        device,
        classifier=MMRClassifier(model, device),
        ocr_engine=MMROCREngine(ocr_engine=engine),
    )
    gt = {
        (p["score"], p["page"]): p for p in read(CODE / "tools/issue415/reviewed_gt.json")["pages"]
    }
    combos = {"bN_bM": ("b", "b"), "bN_cM": ("b", "c"), "cN_bM": ("c", "b"), "cN_cM": ("c", "c")}
    totals = {k: {} for k in [*combos, "retained_b", "retained_c"]}
    pages = []
    for score in a.scores:
        runs = {"b": run_dir(a.baseline_root / score), "c": run_dir(a.candidate_root / score)}
        page_names = sorted(p.name for p in (runs["c"] / "intermediate").glob("page_*"))
        for pi, page in enumerate(page_names):
            inp = {k: page_inputs(r, page) for k, r in runs.items()}
            assert sha(inp["b"]["image"]) == sha(inp["c"]["image"]), page
            image = cv2.imread(str(inp["c"]["image"]))
            h, w = image.shape[:2]
            expected = [
                dict(page=pi, system=e["system"], measure=e["measure"], skip=e["skip"])
                for e in gt[(score, page)]["events"]
            ]
            rec = dict(score=score, page=page, combos={})
            for name, (n_src, m_src) in combos.items():
                base = read(inp[n_src]["numbering_base"])
                support = build_mmr_support_data(base, inp[m_src]["mask"])
                result = processor._process_page_with_support(
                    page_data=base,
                    support=support,
                    image=image,
                    page_num=pi + 1,
                    image_width=w,
                    image_height=h,
                    debug_img=None,
                )
                scoring = score_overrides(expected, dict(measure_overrides=result))
                rec["combos"][name] = dict(counts=scoring["counts"], overrides=result)
            for k in "bc":
                retained = read(inp[k]["retained_overrides"])
                scoring = score_overrides(expected, retained)
                rec["combos"][f"retained_{k}"] = dict(
                    counts=scoring["counts"], overrides=retained.get("measure_overrides", [])
                )
            for name, v in rec["combos"].items():
                for key, n in v["counts"].items():
                    totals[name][key] = totals[name].get(key, 0) + n
            rec["inputs"] = {
                k: {f: sha(p) for f, p in v.items() if f != "retained_overrides"}
                for k, v in inp.items()
            }
            pages.append(rec)
            print(score, page, {n: v["counts"] for n, v in rec["combos"].items()}, flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    report = dict(
        baseline_root=str(a.baseline_root),
        candidate_root=str(a.candidate_root),
        totals=totals,
        providers=providers,
        model_sha256=sha(model),
        mmr_source_sha256=sha(CODE / "src/measure_numbering/mmr.py"),
        runner_sha256=sha(__file__),
        pages=pages,
    )
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print("TOTALS", json.dumps(totals), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
