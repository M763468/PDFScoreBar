#!/usr/bin/env python3
"""Issue #519: Full68 MMR replay on a replay variant's numbering_base outputs.

Builds the production MMR support sidecar (``build_mmr_support_data``) from the
variant's per-page ``numbering_base.json`` and the retained x4 HOMR staff mask, then runs
the production ``MMRProcessor`` (CUDA classifier + CUDA RapidOCR, rotation TTA false,
threshold 0.5 / rescue 0.1 defaults) and scores against the reviewed #415 GT with the
#264 scorer.  Evaluation only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
ROOT = Path("/workspace")
sys.path.insert(0, str(CODE))
os.chdir(ROOT)

import cv2  # noqa: E402
import torch  # noqa: E402

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor  # noqa: E402
from src.measure_numbering.rapidocr_provider import (  # noqa: E402
    collect_rapidocr_providers,
    create_mmr_rapidocr,
)
from src.pipeline.mmr_support_reuse import build_mmr_support_data  # noqa: E402
from tools.issue264.run_phase_c_mmr_regression import score_overrides  # noqa: E402

SOURCE_RUN = ROOT / "logs/issue409/full68-numbering-20261009/candidate"
ACCEPTED = {"tp": 171, "fn": 3, "wrong_skip": 3, "fp": 0}


def read(p):
    return json.loads(Path(p).read_text())


def write(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2) + "\n")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to reuse {a.out}")
    assert torch.cuda.is_available()
    model = CODE / "models/mmr/mmr_classifier_best.pth"
    if not model.is_file():
        model = ROOT / "models/mmr/mmr_classifier_best.pth"
    engine = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(engine)
    assert providers and all("CUDAExecutionProvider" in v for v in providers.values()), providers
    device = torch.device("cuda")
    classifier = MMRClassifier(model, device)
    processor = MMRProcessor(
        Path("unused"), device, classifier=classifier, ocr_engine=MMROCREngine(ocr_engine=engine)
    )
    gt = {
        (p["score"], p["page"]): p for p in read(CODE / "tools/issue415/reviewed_gt.json")["pages"]
    }
    summary = read(SOURCE_RUN / "variant_summary.json")
    totals: dict[str, int] = {}
    pages = []
    started = time.monotonic()
    for s in summary["scores"]:
        hybrid = ROOT / Path(s["hybrid_run"]).relative_to("/workspace")
        for pi, page in enumerate(s["pages"]):
            base = read(a.variant_root / "candidate" / s["score"] / page / "numbering_base.json")
            support_result = read(hybrid / "current_support" / s["score"] / page / "result.json")
            mask = Path(support_result["current_homr_staff_mask"])
            support = build_mmr_support_data(base, mask)
            image_path = ROOT / "data/evaluation2/images" / s["score"] / f"{page}.png"
            image = cv2.imread(str(image_path))
            h, w = image.shape[:2]
            result = processor._process_page_with_support(
                page_data=base,
                support=support,
                image=image,
                page_num=pi + 1,
                image_width=w,
                image_height=h,
                debug_img=None,
            )
            expected = [
                dict(page=pi, system=e["system"], measure=e["measure"], skip=e["skip"])
                for e in gt[(s["score"], page)]["events"]
            ]
            scoring = score_overrides(expected, dict(measure_overrides=result))
            for k, v in scoring["counts"].items():
                totals[k] = totals.get(k, 0) + v
            rec = dict(
                score=s["score"],
                page=page,
                scoring=scoring,
                overrides=result,
                mask_sha256=sha(mask),
            )
            pages.append(rec)
            write(a.out / s["score"] / f"{page}.json", rec)
            print(s["score"], page, scoring["counts"], flush=True)
    report = dict(
        variant_root=str(a.variant_root),
        counts=totals,
        providers=providers,
        model_sha256=sha(model),
        mmr_source_sha256=sha(CODE / "src/measure_numbering/mmr.py"),
        runner_sha256=sha(__file__),
        elapsed=time.monotonic() - started,
        support_stats=processor.support_stats,
        pages=pages,
        accepted=ACCEPTED,
    )
    write(a.out / "report.json", report)
    print("COMPLETE", totals, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
