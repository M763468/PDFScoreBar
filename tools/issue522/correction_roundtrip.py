#!/usr/bin/env python3
"""Issue #522 (harness from #519): identical manual correction save/apply/resume on control and no_omr runs.

Uses the production review backend without a browser: the manual-correction review
package is materialized from each variant's Phase-C run, an identical staged correction
is written into the package (as the GUI save step does), ``apply_corrections_and_rerun``
applies it with final PDF generation, and the same saved staging is applied a second
time into a fresh output (resume) to check determinism.  Only copies under
``--out`` are written; the variant runs are copied first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODE))

from src.pipeline.review.apply_corrections import apply_corrections_and_rerun  # noqa: E402
from src.pipeline.review.manual_correction_materializer import (  # noqa: E402
    materialize_manual_correction_review_package,
)


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def finals(run: Path):
    return {
        p.parent.name: read(p)
        for p in sorted((run / "outputs").glob("page_*/numbering_final.json"))
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--downstream", type=Path, required=True)
    ap.add_argument("--score", required=True)
    ap.add_argument("--correction", type=Path, required=True, help="staged correction JSON")
    ap.add_argument("--page-id", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reference", default="control")
    ap.add_argument("--candidate", default="no_omr")
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to reuse {a.out}")
    results = {}
    for variant in (a.reference, a.candidate):
        run = a.out / variant / "source_run"
        shutil.copytree(a.downstream / variant / a.score, run, symlinks=True)
        # The materializer requires per-page artifacts inside the run; stage copies of
        # externally referenced files into the copied run and rewrite only the copy.
        manifest = read(run / "manifest.json")
        relocated = []
        for page in manifest["pages"]:
            for field in ("barlines_json",):
                raw = page.get(field)
                if not raw:
                    continue
                path = Path(raw)
                try:
                    path.resolve().relative_to(run.resolve())
                    continue
                except ValueError:
                    pass
                target = run / "staged_inputs" / page["page_id"] / f"{field}{path.suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, target)
                page[field] = str(target)
                relocated.append(
                    dict(page=page["page_id"], field=field, source=str(path), sha256=sha(path))
                )
        (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (run / "staged_inputs" / "relocation.json").write_text(
            json.dumps(relocated, indent=1) + "\n"
        )
        review = run / "review_package"
        package = materialize_manual_correction_review_package(run_root=run, review_root=review)
        handoff_path = Path(
            package.get("handoff")
            or package.get("manual_correction_input")
            or review / "manual_correction_input.json"
        )
        handoff = read(handoff_path)
        # Save exactly where the GUI saves staged corrections for this package.
        from src.pipeline.review.manual_correction_handoff import GUI_OUTPUT_KEYS

        kind = read(a.correction)["correction_type"]
        staged = review / "corrections" / GUI_OUTPUT_KEYS[kind]
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(a.correction, staged)
        runs = {}
        for attempt in ("apply", "resume"):
            corrected = apply_corrections_and_rerun(
                handoff_path,
                output_root=a.out / variant / attempt,
                run_id=f"issue519_{variant}_{attempt}",
                overwrite=attempt == "resume",  # re-apply after resume replaces canonical files
                generate_final_pdf=True,
                output_name=f"{a.score}_{variant}_{attempt}",
            )
            corrected = Path(corrected)
            pdfs = sorted(corrected.rglob("*.pdf"))
            runs[attempt] = dict(
                run=str(corrected),
                finals=finals(corrected),
                pdf=[str(p) for p in pdfs],
                pdf_sha256=[sha(p) for p in pdfs],
            )
        results[variant] = dict(
            package=str(handoff_path), handoff=handoff, runs=runs, base_finals=finals(run)
        )
    c, n = results[a.reference], results[a.candidate]

    def numbers(f):
        return {
            k: [[m["number"] for m in s["measures"]] for s in v["pages"][0]["systems"]]
            for k, v in f.items()
        }

    def geometry(f):
        return {
            k: [[m["bbox"] for m in s["measures"]] for s in v["pages"][0]["systems"]]
            for k, v in f.items()
        }

    changed = {
        k
        for k in numbers(c["base_finals"])
        if numbers(c["base_finals"])[k] != numbers(c["runs"]["apply"]["finals"])[k]
    }
    summary = dict(
        correction=read(a.correction),
        package_pages_equal=[p["page_id"] for p in c["handoff"]["pages"]]
        == [p["page_id"] for p in n["handoff"]["pages"]],
        correction_changed_pages_control=sorted(changed),
        apply_numbers_equal=numbers(c["runs"]["apply"]["finals"])
        == numbers(n["runs"]["apply"]["finals"]),
        apply_geometry_equal=geometry(c["runs"]["apply"]["finals"])
        == geometry(n["runs"]["apply"]["finals"]),
        resume_equal_control=c["runs"]["apply"]["finals"] == c["runs"]["resume"]["finals"],
        resume_equal_no_omr=n["runs"]["apply"]["finals"] == n["runs"]["resume"]["finals"],
        pdf_count=[len(c["runs"]["apply"]["pdf"]), len(n["runs"]["apply"]["pdf"])],
    )
    (a.out / "report.json").write_text(
        json.dumps(dict(summary=summary, results=results), indent=1) + "\n"
    )
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
