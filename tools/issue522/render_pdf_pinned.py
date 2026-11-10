#!/usr/bin/env python3
"""Issue #522 (harness from #519): materialize final PDFs with an explicitly pinned renderer checkout.

Run with PYTHONPATH pointing at the pinned renderer checkout (e.g. the #416-accepted
``b51c9f6f``).  For each variant score, the handoff, staged images and final numbering
produced by ``replay_downstream.py`` are copied into a fresh directory and passed to
that checkout's ``materialize_corrected_final_outputs``.  Decoded embedded page pixels
of each PDF are hashed so variants and the accepted reference can be compared.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
from pathlib import Path

import fitz
from PIL import Image

from src.pipeline.review.final_output import materialize_corrected_final_outputs


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def page_pixels(pdf_path):
    out = []
    with fitz.open(pdf_path) as pdf:
        for page in pdf:
            images = page.get_images()
            assert len(images) == 1
            data = pdf.extract_image(images[0][0])["image"]
            with Image.open(io.BytesIO(data)) as im:
                out.append(hashlib.sha256(im.convert("RGB").tobytes()).hexdigest())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--downstream", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--accepted-reference", type=Path)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to reuse {a.out}")
    report = json.loads((a.downstream / "report.json").read_text())
    scores = []
    for r in report["reports"]:
        name = r["score"]
        src, dst = a.downstream / name, a.out / name
        dst.mkdir(parents=True)
        shutil.copy(src / "handoff.json", dst / "handoff.json")
        shutil.copytree(src / "inputs", dst / "inputs")
        shutil.copytree(src / "outputs", dst / "outputs")
        rec = dict(score=name)
        try:
            summary = materialize_corrected_final_outputs(
                handoff_path=dst / "handoff.json", corrected_run_dir=dst, output_name=name
            )
            rec.update(
                status="completed",
                pdf=summary["final_pdf"],
                pdf_sha256=sha(summary["final_pdf"]),
                page_pixels=page_pixels(summary["final_pdf"]),
                row_labels=[p.get("row_labels") for p in summary["pages"]],
            )
            if a.accepted_reference:
                ref = next((a.accepted_reference / name / "final").glob("*.pdf"))
                rec["accepted_pdf"] = str(ref)
                rec["accepted_page_pixels_equal"] = page_pixels(ref) == rec["page_pixels"]
        except Exception as error:  # noqa: BLE001 - recorded as evidence, not suppressed
            rec.update(status=f"failed: {type(error).__name__}: {error}")
        scores.append(rec)
        print(name, rec["status"], rec.get("accepted_page_pixels_equal"), flush=True)
    (a.out / "report.json").write_text(json.dumps(dict(scores=scores), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
