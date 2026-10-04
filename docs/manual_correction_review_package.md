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
      review_overlay.png        # optional pre-rendered evidence
      mmr_overrides.json
      barlines_review.json
    corrections/
```

`outputs.review.root` can override that package root:

- relative paths are resolved from `<run_dir>`;
- absolute paths are allowed for controlled callers that already own a review directory;
- the materializer still requires derived numbering/MMR/barline artifacts from the selected
  source run; the exact `image_path` recorded by that manifest may live outside the per-score
  run directory (for example, a shared batch `input_images/` directory) and is copied into the
  package without searching fallback runs.

The handoff records the page identity and coordinate-space relationship needed by the GUI. Normal
manual review must start from this handoff rather than assembling image, numbering, MMR, or barline
paths from unrelated `logs/` runs.

A review package faithfully displays the detector artifact produced by its source run; that does
not by itself make the source run production-accuracy evidence. Before interpreting visible misses
or false positives as production regressions, verify that the source manifest uses the current
`dense_full_pipeline` detector contract and production model manifest/threshold. The standard
`make verify-gpu-smoke` / `make run-smoke` path performs this check automatically and gates its
one-page detector result against canonical GT. Workflow-only or legacy smoke artifacts must not be used to
draw conclusions about production detector accuracy.

## 2. Open the user correction app from the handoff

When the review package was produced by the canonical Docker pipeline, launch the GUI in the same
maintained Docker runtime. Pipeline artifacts on the bind-mounted worktree may be owned by the
container user, so a host-side GUI process is not guaranteed to have write permission for
`review/corrections/`.

The Docker snippets below assume `<review_root>` is inside the repository mounted at
`/workspace` (the normal case, including the default `<run_dir>/review`). If a controlled caller
uses an absolute review root outside the repository, that directory must be bind-mounted separately
at a container path and the `--handoff` argument must use that container-visible path. Any retained
source artifacts referenced by the handoff must likewise remain reachable at the recorded paths.

```bash
docker run --rm -it --network host \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/review_correction/server.py \
  --handoff <review_root>/manual_correction_input.json \
  --port 8010
```

Then open `http://127.0.0.1:8010`.

For a review package that is already writable by the current host user, the lightweight host launch
remains valid:

```bash
python3 tools/review_correction/server.py \
  --handoff <review_root>/manual_correction_input.json \
  --port 8010
```

The user correction entry:

- validates the strict same-package review contract before serving the GUI;
- requires the source image, final numbering, MMR evidence, and review barlines to exist;
- accepts a pre-rendered review overlay when present, but does not require one because the manual
  GUI renders its active measure/barline/manual-state overlays from the underlying artifacts;
- uses the handoff's review directory as the GUI root;
- accepts only `--handoff` and `--port`, and binds to loopback;
- serves only artifacts declared by that handoff and writes only its declared outputs under
  `review/corrections/`, checking resolved paths again for each request;
- keeps the current page-local `manual_outputs` routing.

Issue #383 retired the legacy arbitrary-path `manual_config_builder.py`. The maintained manual
workflow starts from the package-local `review/manual_correction_input.json` handoff described above.

### Optional movement-boundary evidence

When movement-boundary review is needed, keep the same review package and attach
the review-only Issue #333 evidence artifact:

```bash
python -m tools.movement_boundary_review attach \
  --handoff <review_root>/manual_correction_input.json \
  --evidence <run>/movement_boundary_evidence.json
```

The attach step copies the evidence into the package and records package-local
paths in the handoff. It does not approve any candidate or change numbering.
The existing GUI then exposes a **Movement boundary** correction type. A
movement boundary always means **immediately before the target system**: the
first measure of that system starts the new movement. Reviewers can click
anywhere inside a system to target it; direct 1-based system entry remains
available. Movement decisions are persisted immediately when the reviewer
confirms **boundary** or **no boundary**; there is no separate Save step for
this correction type. The movement UI hides unrelated Select/Draw/Save controls
and only shows clearing controls when an existing saved decision is selected.
The canvas uses user-facing states: **Suggested boundary**, **Confirmed
boundary**, **Checked: no boundary**, and **Boundary used by current
numbering**. The Pages list also annotates pages with pending suggestions and
saved movement decisions so a whole-score review does not require opening pages
blindly. **Finish movement review** is enabled only after all suggested
boundaries have been reviewed; it creates the boundary input for the next
numbering run and does not change the score currently displayed in the GUI.

### Manual GUI quick guide

The user application places page navigation at the top, score display controls beside the canvas,
and correction tasks, saved/result status, and action buttons in the right context panel.

Initial overlay state:

| Overlay | Initial state | Purpose |
| --- | --- | --- |
| Measures | on | Show normal measure geometry. |
| Barlines | on | Show current barline geometry. |
| Labels | off | Show regular overlay labels. Keep this off for a less crowded score. |
| Original grouping | on | Show base/automatic MMR state. |
| Manual state | on | Show pending manual edits. |

Useful review views:

- **Barlines only:** Measures off, Barlines on, Labels off, Base MMR state off,
  Manual state off.
- **Measures only:** Measures on, Barlines off, Labels off, Base MMR state off,
  Manual state off.
- **Pending barline removals:** Barlines may be off while Manual state remains on; the pending
  removal remains visible independently of the normal barline layer.

The selected object and an active draft remain visible even when their normal overlay layer is
hidden. Selected objects are highlighted separately so reviewers can reduce overlay density without
losing the active target.

Typical correction flow for MMR/barline/measure corrections:

1. Choose a correction task and change in the right context panel.
2. Select the target object; barline editing additionally exposes Select/Draw modes.
3. Create an edit and inspect the pending change in both the canvas and **Current page changes**.
4. Clear the edit if the pending change is not wanted.
5. Use **Save changes** to record these correction types.

Movement-boundary review is deliberately simpler: select a system, confirm
**boundary** or **no boundary**, and the decision is saved immediately. After
all suggested boundaries are reviewed, use **Finish movement review** to create
the boundary data consumed by the next numbering run.

Visible Page / System / Measure identifiers are **1-based** for reviewer readability. Persisted
correction targets keep the existing internal **0-based** indices; the GUI must not translate the
saved schema.

Canvas navigation:

- zoom: mouse wheel;
- pan: Space + drag or middle-mouse drag;
- previous/next page: buttons in the sticky header or Left/Right arrow keys;
- Delete/Backspace removes the currently selected pending correction when applicable.

The user application separates page navigation, score display controls, task actions, and correction
status. Optional evidence, annotation reason, and provenance live under **Details and evidence**.
Destructive actions appear only when a removable correction is selected.

## 3. Save corrections

### Shared correction state

The review app reports state for each page and correction type, then gives package counts so a
mixed review stays visible. Its controlled labels are **Edit not recorded**, **No correction
recorded**, **Correction recorded**, **No corrected result yet**, **Corrected result is current**,
**Recorded corrections changed since this result**, **Generating corrected result**, and **Needs
attention**. The package summary uses **Review has different correction states** when its pages or
correction types do not share one state.

MMR measure-span, measure-construction, and barline edits stay pending until the reviewer records
them. Movement decisions become recorded as soon as the reviewer confirms a boundary or no
boundary; they do not have a separate record action. The finalized movement-boundary input is also
part of the correction identity.

Recording and generating a corrected result are separate. The app compares content identities for
the handoff, declared source artifacts, source manifest when available, and correction files. A
corrected result is current only while the source and complete recorded correction set match the
identities consumed by that run. Editing or removing a recorded correction makes the previous result
stale, even when an older corrected PDF still exists.

Failed recording or application is reported as an error while preserving the previous recorded
correction file and last successful corrected-result identity. State metadata is stored separately
from correction payloads in `corrections/.correction_state.json`; it does not change engine payload
schemas. The server exposes this contract through `GET /api/state`. The user app reports unrecorded
drafts to the server through `POST /api/state/pending` and clears them with
`POST /api/state/pending/clear`.

The existing GUI stages corrections under the review package's `corrections/` directory. The
current correction surfaces are:

```text
review/corrections/
  mmr_measure_spans.json
  measure_construction_overrides.json
  barline_construction_overrides.json
```

These are GUI staging files. Movement-boundary decisions do not use the
stage-then-save interaction; each decision is saved immediately. When movement
evidence is attached, the GUI also uses:

```text
review/
  movement_boundary_evidence.json
  corrections/
    movement_boundaries_review.json
    movement_boundaries.json
```

`movement_boundaries_review.json` retains explicit accepted/rejected/manual
review actions. **Finish movement review** writes
`movement_boundaries.json` as `issue268.movement_boundaries.v1`, containing
only confirmed boundaries. Checked no-boundary locations stay in the review
record and are not numbering inputs. This finalization step does not rerun
numbering or alter the score shown in the review GUI.

The pipeline consumes canonical:

```text
review/corrections/
  measure_overrides.json
  barline_overrides.json
```

The apply helper performs the staging-to-canonical conversion and refuses to replace existing
canonical files unless overwrite is explicitly requested.

## 4. Apply corrections, rerun, and generate the corrected final PDF

Use the existing apply helper in the maintained pipeline runtime. The command below has the same
workspace assumption as the GUI command: `<review_root>` is inside the repository mounted at
`/workspace`. For an absolute external review root, add an explicit bind mount for that package
and pass its container-visible handoff path; retained source-artifact paths in the handoff must also
be reachable inside the container.

When OMR-DLN is registered in the shared host cache, mount the selected verified artifact at its
manifest-declared runtime path:

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
  <review_root>/manual_correction_input.json \
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
- silently infer movement boundaries or convert unreviewed candidates into numbering resets; movement
  review is explicit and package-local, and its resolved export remains separate from ordinary correction reruns.


## Apply recorded corrections in the review application

Run the package-scoped server in the maintained Python runtime with the dependencies needed by
`src.pipeline.review.apply_corrections`:

```bash
python3 tools/review_correction/server.py --handoff /path/to/run/review/manual_correction_input.json
```

Record edits first. Movement decisions save immediately; finish movement review before applying
those decisions. Choose **Generate corrected PDF** to invoke the authoritative retained-artifact
engine and explicitly generate the final PDF. The browser polls application state while this runs.
A PDF link appears only after both the corrected engine run and final PDF succeed. Changing or
removing recorded corrections makes the previous result stale; its link remains available and is
identified as the previous result. A failed attempt preserves that last successful result.

The server accepts `POST /api/apply` with an empty JSON object. Paths, configuration, run names,
and overwrite options cannot be supplied by the browser. One application operation is allowed per
package; correction writes and duplicate apply requests are rejected while it runs. Attempts receive
monotonic names under `review/application_runs/attempt_NNNN/`. Existing attempts are never replaced.
Each contains copied declared review/correction inputs, consumed identity provenance, and the
corrected engine run. Generated canonical correction files stay in the copy, so an application retry
does not overwrite the recorded corrections. The final deliverable is `corrected/final/*.pdf`;
review/application evidence remains outside that directory. `GET /api/result` serves only the last
successful PDF after checking its stored content identity.

The engine validates finalized movement data against saved review decisions and evidence. An older
finalization, or saved decisions that have not been finalized, produces an actionable failure instead
of silently ignoring the latest movement review. When no reviewed movement data exists, source-run
movement inputs retain their existing meaning; unresolved candidates do not become resets.


### Reviewer-facing strings

The dedicated user UI is `tools/review_correction/index.html` and `app.js`. Primary action,
validation, and result messages are collected in `tools/review_correction/strings.js`; state labels
come from `tools/review_correction/state.py::LABELS`. These are the controlled English inputs for
#361. GT/developer presentation remains in `tools/gt_relabel_gui/` and is not a localization target.
The browser displays only current-page detail alongside package-wide pending/recorded/error counts.


## Acceptance and localization handoff

The real-artifact acceptance procedure and fixed observable result gates are documented in
[REVIEW_ACCEPTANCE.md](dev/REVIEW_ACCEPTANCE.md). Evidence is retained under
`logs/issue397/acceptance/`, separately from each clean corrected `final/` directory.

For #361, the stable user surface consists of `tools/review_correction/index.html`, `strings.js`,
`app.js`, `correction_state.js`, and the state labels in `state.py::LABELS`.
Primary copy is catalogued; some detail/status messages remain literal English in `app.js`
(for example measure/system summaries, removal feedback and artifact-load errors). Localization
should extract these within the user application and translate validation feedback displayed by
this application. GT/developer files are not part of that follow-up. The implementation surface is
ready for #361; integration into `develop` awaits review of the dependency PRs.
