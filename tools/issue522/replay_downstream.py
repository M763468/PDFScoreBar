#!/usr/bin/env python3
"""Issue #522 (harness from #519): Full68 final numbering, PDF and reviewed-GT audit for one replay variant.

Evaluation-only.  For every score, the production Phase-C path
(``PipelineOrchestrator`` with detection/Phase-A disabled, existing ``overrides_mmr.json``
reused through ``skip_existing``, ``apply_measure_overrides=true``) is executed on the
variant's barlines, numbering_base and MMR overrides, following the accepted
``tools/issue413/replay_phase_c.py`` procedure.  The correction-apply path
(``_final_numbering_from_retained_geometry``) is computed on the same inputs and must
agree exactly.  The final PDF is materialized with the production review/final output
code and its embedded pixels are verified.  Reviewed #415 GT is audited with
``audit_pages``.  No upstream producer, CNN or MMR inference is executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
ROOT = Path("/workspace")
sys.path.insert(0, str(CODE))
os.chdir(ROOT)

from src.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from src.pipeline.review.apply_corrections import (  # noqa: E402
    _final_numbering_from_retained_geometry,
)
from src.pipeline.review.final_output import (  # noqa: E402
    CorrectedFinalOutputError,
    _physical_page_size,
    _render_final_page_image,
    materialize_corrected_final_outputs,
)
from tools.issue415.audit_numbering import audit_pages  # noqa: E402

SOURCE = ROOT / "logs/issue409/full68-numbering-20261009/candidate"
ABLATION = ROOT / "logs/issue519/ablation"


def read(p):
    return json.loads(Path(p).read_text())


def write(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2) + "\n")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def local(raw) -> Path:
    p = Path(raw)
    return p if p.is_relative_to("/workspace") else ROOT / p


def verify_pdf_images(summary: dict) -> list[dict]:
    """#413 pixel check adapted to the current renderer signature (page_width_points)."""
    import io

    import fitz
    from PIL import Image

    results = []
    with fitz.open(summary["final_pdf"]) as pdf:
        assert len(pdf) == len(summary["pages"])
        for index, page in enumerate(summary["pages"]):
            expected, _ = _render_final_page_image(
                source_image_path=Path(page["source_image"]),
                numbering_path=Path(page["corrected_numbering_final"]),
                page_id=page["page_id"],
                page_number=page["page_number"],
                page_width_points=page["page_size_points"][0],
            )
            buffer = io.BytesIO()
            expected.save(buffer, format="JPEG")
            expected.close()
            images = pdf[index].get_images()
            assert len(images) == 1, (page["page_id"], "PDF image count")
            embedded = pdf.extract_image(images[0][0])
            with (
                Image.open(io.BytesIO(buffer.getvalue())) as reference,
                Image.open(io.BytesIO(embedded["image"])) as actual,
            ):
                assert actual.size == reference.size
                a = hashlib.sha256(actual.convert("RGB").tobytes()).hexdigest()
                b = hashlib.sha256(reference.convert("RGB").tobytes()).hexdigest()
                assert a == b, (page["page_id"], "PDF pixel mismatch")
            results.append({"page_id": page["page_id"], "decoded_rgb_sha256": a})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--variant-root", type=Path, required=True)
    ap.add_argument("--mmr-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists():
        raise SystemExit(f"refusing to reuse {out}")
    variant_root = a.variant_root.resolve()
    mmr_root = a.mmr_root.resolve()
    gt = {
        (p["score"], p["page"]): p for p in read(CODE / "tools/issue415/reviewed_gt.json")["pages"]
    }
    hashes: dict[str, str] = {}

    def consume(p):
        p = Path(p)
        hashes[str(p)] = sha(p)
        return p

    write(
        out / "provenance.json",
        dict(
            variant=a.variant,
            code_root=str(CODE),
            runner_sha256=sha(__file__),
            source_commit=os.environ.get("PDFSCORE_HOST_SOURCE_COMMIT"),
            image_id=os.environ.get("PDFSCORE_DOCKER_IMAGE_ID"),
            reviewed_gt_sha256=sha(CODE / "tools/issue415/reviewed_gt.json"),
            inputs=dict(variant_root=str(variant_root), mmr_root=str(mmr_root), source=str(SOURCE)),
            upstream_inference_reexecuted=False,
        ),
    )
    summary = read(SOURCE / "variant_summary.json")
    reports = []
    for s in summary["scores"]:
        name = s["score"]
        old_run = local(s["pipeline_run"])
        manifest = read(consume(old_run / "manifest.json"))
        pages = manifest["pages"]
        assert [p["page_id"] for p in pages] == s["pages"]
        run = out / name
        images = run / "inputs/images"
        images.mkdir(parents=True)
        config = deepcopy(manifest["config"])
        config["steps"].update(
            pdf_to_images=False,
            detection=False,
            filter_pages=False,
            numbering_base=False,
            mmr_overrides=True,
            apply_measure_overrides=True,
            overlay=False,
        )
        config["detection"]["detector_route"] = "standard"  # bypass fresh MMR support prep
        first = pages[0]
        barline_pattern = str(variant_root / "candidate" / name / "{page_id}" / "predictions.json")
        config["inputs"].update(
            pdf_to_images={"output_dir": str(images), "image_glob": "page_*.png"},
            barlines_root=str(ROOT),
            barlines_pattern=barline_pattern,
            staff_mask_pattern=str(local(first["staff_mask"])).replace(
                first["page_id"], "{page_id}"
            ),
        )
        handoff, entries, start, gui_finals = [], [], 1, []
        for pi, page in enumerate(pages):
            page_id = page["page_id"]
            inter = run / "intermediate" / page_id
            inter.mkdir(parents=True)
            src_image = consume(ROOT / "data/evaluation2/images" / name / f"{page_id}.png")
            shutil.copyfile(src_image, images / f"{page_id}.png")
            base = read(
                consume(variant_root / "candidate" / name / page_id / "numbering_base.json")
            )
            overrides = read(consume(mmr_root / name / f"{page_id}.json"))["overrides"]
            write(inter / "numbering_base.json", base)
            write(inter / "overrides_mmr.json", {"measure_overrides": overrides})
            barlines = read(consume(barline_pattern.replace("{page_id}", page_id)))
            mask = consume(local(page["staff_mask"]))
            final_gui, terminal = _final_numbering_from_retained_geometry(
                page_id=page_id,
                page_number=pi + 1,
                page_index=pi,
                source_image=src_image,
                staff_mask=mask,
                barlines=barlines,
                force_single_system=bool(config["numbering"].get("force_single_system", False)),
                start_number=start,
                overrides=overrides,
                page_boundaries=[],
            )
            gui_finals.append((final_gui, terminal))
            start = terminal
            handoff.append(
                dict(
                    page_id=page_id, page_number=pi + 1, source_image=f"inputs/images/{page_id}.png"
                )
            )
            entries.append(
                dict(
                    page=page_id, base=base, recognized=overrides, gt=gt[(name, page_id)]["events"]
                )
            )
        write(run / "replay_config.json", config)
        PipelineOrchestrator(config, f"issue519_{a.variant}_{name}", run, skip_existing=True).run()
        finals = [read(run / "outputs" / p["page_id"] / "numbering_final.json") for p in pages]
        gui_equal = []
        prev = 1
        for (gui, terminal), fin, e in zip(gui_finals, finals, entries):
            e["final"] = fin
            gui_equal.append(
                gui["pages"] == fin["pages"]
                and fin["numbering_metadata"]["next_number"] == terminal
            )
            assert fin["numbering_metadata"]["start_number"] == prev, (name, e["page"])
            prev = fin["numbering_metadata"]["next_number"]
            assert [[m["bbox"] for m in x["measures"]] for x in fin["pages"][0]["systems"]] == [
                [m["bbox"] for m in x["measures"]] for x in e["base"]["pages"][0]["systems"]
            ], (name, e["page"], "final geometry differs from Phase-A base")
        write(run / "handoff.json", {"pages": handoff})
        pdf_status, pdf, pixels = "completed", None, []
        try:
            pdf = materialize_corrected_final_outputs(
                handoff_path=run / "handoff.json", corrected_run_dir=run, output_name=name
            )
            pixels = verify_pdf_images(pdf)
            write(run / "review/pdf-pixel-verification.json", pixels)
            write(run / "review/final-summary.json", pdf)
        except CorrectedFinalOutputError as error:
            pdf_status = f"failed: {error}"
        # Per-page render with the same production renderer, so a score-level PDF
        # failure still yields comparable page images, row labels and failure sets.
        page_render = []
        for h in handoff:
            final_path = run / "outputs" / h["page_id"] / "numbering_final.json"
            try:
                from PIL import Image

                with Image.open(run / h["source_image"]) as probe:
                    size = _physical_page_size(h, probe, [])
                image, rows = _render_final_page_image(
                    source_image_path=run / h["source_image"],
                    numbering_path=final_path,
                    page_id=h["page_id"],
                    page_number=h["page_number"],
                    page_width_points=size[0],
                )
                target = run / "review/page_render" / f"{h['page_id']}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target)
                image.close()
                page_render.append(
                    dict(page=h["page_id"], status="rendered", rows=rows, png_sha256=sha(target))
                )
            except CorrectedFinalOutputError as error:
                page_render.append(dict(page=h["page_id"], status=f"failed: {error}"))
        write(run / "review/page-render.json", page_render)
        audit = audit_pages(entries)
        reports.append(
            dict(
                score=name,
                pages=len(pages),
                audit=audit,
                gui_path_equal_pages=sum(gui_equal),
                pdf_status=pdf_status,
                pdf=pdf["final_pdf"] if pdf else None,
                pdf_sha256=sha(pdf["final_pdf"]) if pdf else None,
                pdf_pages=len(pixels),
                page_render=page_render,
                next_number=prev,
            )
        )
        print(
            a.variant,
            name,
            "measures",
            audit["physical_measures"],
            "app_err",
            len(audit["application_errors"]),
            "cont_err",
            len(audit["continuity_errors"]),
            "gt_err",
            len(audit["gt_increment_errors"]),
            "gui_eq",
            sum(gui_equal),
            "/",
            len(pages),
            "pdf_pages",
            len(pixels),
            flush=True,
        )
    for p, h in hashes.items():
        assert sha(p) == h, p
    write(out / "input-sha256.json", hashes)
    totals = dict(
        physical_measures=sum(r["audit"]["physical_measures"] for r in reports),
        application_errors=sum(len(r["audit"]["application_errors"]) for r in reports),
        continuity_errors=sum(len(r["audit"]["continuity_errors"]) for r in reports),
        gt_increment_errors=sum(len(r["audit"]["gt_increment_errors"]) for r in reports),
        pdf_pages=sum(r["pdf_pages"] for r in reports),
        page_render_failures=[
            (r["score"], x["page"], x["status"])
            for r in reports
            for x in r["page_render"]
            if x["status"] != "rendered"
        ],
        gui_path_equal_pages=sum(r["gui_path_equal_pages"] for r in reports),
    )
    write(out / "report.json", dict(variant=a.variant, totals=totals, reports=reports))
    print("COMPLETE", a.variant, json.dumps(totals), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
