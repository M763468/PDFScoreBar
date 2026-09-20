# Manual Correction Review Workflow

This document describes the current config-first manual-correction workflow. It connects one
pipeline run to the existing manual GUI, saves package-local corrections, reruns the pipeline with
those corrections, and can materialize the corrected final score-numbered PDF.

This is still not a new public `pdfscorebar` console surface. Normal pipeline execution remains
config-first through `make run-pipeline` / `src.pipeline.main`, and the correction workflow reuses
the existing review helpers and GUI.

## 1. Emit the review package

Enable manual-correction review output explicitly:

```yaml
outputs:
  review:
    manual_correction_package: true
    # optional; relative paths are resolved from the internal run_dir
    root: review
```

Run the normal pipeline:

```bash
make run-pipeline CONFIG=<config.yaml>
```

By default, the package is written under the internal pipeline run directory:

```text
<run_dir>/
  review/
    manual_correction_input.json
    pages/<page_id>/
      source.png
      numbering_final.json
      review_overlay.png
      mmr_overrides.json
      barlines_review.json
    corrections/
```

`outputs.review.root` can override that package root:

- relative paths are resolved from `<run_dir>`;
- absolute paths are allowed for controlled callers that already own a review directory;
- the materializer still reads current-run artifacts deterministically and rejects run artifacts
  resolved outside the source run.

The handoff records the page identity and coordinate-space relationship needed by the GUI. Normal
manual review must start from this handoff rather than assembling image, numbering, MMR, or barline
paths from unrelated `logs/` runs.

## 2. Open the existing manual GUI from the handoff

When the review package was produced by the canonical Docker pipeline, launch the GUI in the same
maintained Docker runtime. Pipeline artifacts on the bind-mounted worktree may be owned by the
container user, so a host-side GUI process is not guaranteed to have write permission for
`review/corrections/`.

```bash
docker run --rm -it \
  -p 127.0.0.1:8010:8010 \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/gt_relabel_gui/server.py \
  --mode manual \
  --handoff <run_dir>/review/manual_correction_input.json \
  --host 0.0.0.0 \
  --port 8010
```

Then open `http://127.0.0.1:8010`.

For a review package that is already writable by the current host user, the lightweight host launch
remains valid:

```bash
python3 tools/gt_relabel_gui/server.py \
  --mode manual \
  --handoff <run_dir>/review/manual_correction_input.json \
  --host 127.0.0.1 \
  --port 8010
```

The `--handoff` route:

- validates the strict same-package review contract before serving the GUI;
- requires the source image, final numbering, review overlay, MMR evidence, and review barlines to
  exist;
- uses the handoff's review directory as the GUI root;
- rejects a separate `--root` or `--config`, preventing normal use from substituting unrelated
  artifacts;
- keeps the current page-local `manual_outputs` routing.

The legacy one-page `manual_config_builder.py` remains available for development/legacy uses, but
it is not the normal #236 review workflow because it accepts arbitrary artifact paths.

## 3. Save corrections

The existing GUI stages corrections under the review package's `corrections/` directory. The
current correction surfaces are:

```text
review/corrections/
  mmr_measure_spans.json
  measure_construction_overrides.json
  barline_construction_overrides.json
```

These are GUI staging files. The pipeline consumes canonical:

```text
review/corrections/
  measure_overrides.json
  barline_overrides.json
```

The apply helper performs the staging-to-canonical conversion and refuses to replace existing
canonical files unless overwrite is explicitly requested.

## 4. Apply corrections, rerun, and generate the corrected final PDF

Use the existing apply helper in the maintained pipeline runtime. When OMR-DLN is registered
in the shared host cache, mount the selected verified artifact at its manifest-declared runtime
path:

```bash
OMR_HOST="$HOME/.cache/pdfscorebar/models/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt"
OMR_RUNTIME="/opt/pdfscore-external/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt"

docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -v "$OMR_HOST:$OMR_RUNTIME:ro" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e OMR_DLN_MODEL_PATH="$OMR_RUNTIME" \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python -m src.pipeline.review.apply_corrections \
  <run_dir>/review/manual_correction_input.json \
  --generate-final-pdf
```

Use `--output-name <name>` when an explicit final output name is needed. If canonical correction
files already exist and replacing them is intentional, add `--overwrite`.

The helper:

1. validates the handoff;
2. canonicalizes the GUI staging files;
3. carries forward existing correction inputs when applicable;
4. fixes the rerun to the retained artifacts from the reviewed source run;
5. applies new barline corrections to the reviewed barline artifact without rerunning PDF rendering,
   HOMR, Real-ESRGAN, OMR-DLN, probe generation, or CNN scoring;
6. reuses the previous automatic MMR result everywhere except measures directly touched by a changed
   barline;
7. selectively reruns MMR only for those touched measures, excluding any measure that already has an
   explicit manual MMR correction;
8. regenerates final numbering only where required, while copying an unchanged reviewed final page
   verbatim when its start number is still valid;
9. when `--generate-final-pdf` is set, renders the corrected final PDF from the corrected final
   numbering.

For a removed barline, the selective MMR boundary is the two reviewed measures touching that
barline and the merged corrected measure. For an added barline, it is the reviewed measure being
split and the two corrected measures created around the new barline. Measures outside that local
topology change keep their previous MMR result.

The corrected-run config records `correction_rerun.mode=retained_artifacts_selective` and disables
fresh `pdf_to_images` / `detection` steps for provenance. A correction apply must therefore not
depend on detector/SR/CNN inference merely to regenerate numbering.

The corrected run writes:

```text
<corrected_run_dir>/
  final/
    <output-name>_score_numbered.pdf
  review/
    correction_summary.json
    corrected_final_summary.json
```

The final PDF is the clean row-start-number deliverable. Correction provenance and review/debug
metadata remain outside `final/`.

## Source command metadata

`outputs.review.source_pipeline_command` is optional. When present, it is copied into
`manual_correction_input.json` as trace metadata. The current config-first entrypoint does not
reconstruct the shell command automatically.

## Scope boundary

This workflow intentionally reuses the existing review package, GUI, correction helpers, rerun path,
and final renderer. It does not:

- add a second correction workflow or a new `pdfscorebar` public CLI;
- change detector, HOMR, MMR, grouping, barline, or numbering accuracy behavior;
- implement movement-boundary review; future movement review should extend the same review/correction
  UX rather than create a disconnected path.
