# Issue 229: Manual Correction GUI Pipeline Workflow

## Status

- Parent epic: #225
- Task issue: #229
- Base branch: `develop`
- Depends on: #226 user-facing CLI entrypoint, #227 output profile contract, #228 final overlay contract
- Related smoke issue: #215
- Scope of this document: workflow boundary from review-profile pipeline output to manual correction GUI and back to corrected final applied numbering.

This document records the design outcome for #229. It intentionally does not implement the profile materializer, GUI adapter, correction-application command, final renderer, detector/OCR/MMR behavior, or a real-artifact smoke test. The goal is to define the boundary that those follow-up implementation issues should target.

## Document lifecycle

This file is an issue-scoped design handoff, not the permanent home for user documentation.

After the user-facing review/correction workflow is implemented and accepted, the stable parts of this design should move into formal documentation such as the root `README.md`, `docs/ENVIRONMENTS.md`, a future user guide, or a standing correction-workflow document. At that point, this issue-specific file and its `docs/README.md` index entry should be removed.

Permanent repository behavior must not depend on a document whose only discoverable name is tied to a completed issue number.

## Decision summary

The normal manual-correction workflow must start from a review output package, not from arbitrary `logs/` paths or page-number-only matching.

Primary handoff:

```text
OUTPUT_DIR/review/manual_correction_input.json
```

Default correction location:

```text
OUTPUT_DIR/review/corrections/
```

The handoff file must bind all page artifacts to the same score identity, run identity, rendered page image, and coordinate space. The GUI should consume this handoff, or an adapter generated from it, rather than independently discovering `page_003` artifacts from unrelated log roots.

Corrected final output is produced by applying saved corrections before final applied numbering is rendered. The final PDF remains governed by #228: it contains only user-facing row-start labels and must not display correction provenance, MMR evidence, barline geometry, warnings, or GUI state.

## Current implementation inventory

### Current pipeline run layout

The current config-driven pipeline writes an implementation-oriented run directory:

```text
run_dir/
  pipeline.log
  manifest.json
  filters.json
  inputs/
    images/
  intermediate/
    <page_id>/
      numbering_base.json
      barlines_corrected.json        # only retained in some debug/apply paths
      overrides_mmr.json
      overrides_combined.json        # debug only
  outputs/
    numbering_final.json
    <page_id>/
      numbering_final.json
      numbering_overlay.png
```

Important current behavior:

- `run_pipeline()` still exposes `output_root/run_id` as its internal execution layout.
- Rendered source images are written under `run_dir/inputs/images/` when image persistence is enabled.
- Page-level base numbering is written under `run_dir/intermediate/<page_id>/numbering_base.json`.
- Review-level barline geometry should be materialized from `run_dir/intermediate/<page_id>/barlines_corrected.json` when available, or from explicitly resolved raw barline geometry retained by the pipeline.
- MMR evidence is written under `run_dir/intermediate/<page_id>/overrides_mmr.json`.
- Page-level final numbering is written under `run_dir/outputs/<page_id>/numbering_final.json`.
- Combined final numbering is written under `run_dir/outputs/numbering_final.json` when multiple pages are present.
- The current `numbering_overlay.png` is a review overlay, not the #228 final PDF.
- `manifest.json` and `filters.json` are internal/debug-oriented sources from which a review-facing summary and warning subset can be materialized.

### Current correction inputs consumed by the pipeline

The current pipeline already has narrow correction hooks, but they are config-first and not yet user-workflow-first:

- `inputs.measure_overrides` is loaded before final numbering and merged with auto MMR overrides during final numbering.
- `inputs.barline_overrides` is loaded before base numbering when `steps.apply_barline_overrides` is enabled.
- MMR measure-span corrections, measure-construction `force_measure`, and barline add/remove corrections are represented by separate helper concepts.
- Manual corrections are applied semantically before the final applied numbering is rendered.

This is enough for a correction workflow, but not enough for a clean user boundary because a user still has to know internal config keys and artifact paths.

### Current manual GUI entrypoints

Current manual GUI implementation:

```text
tools/gt_relabel_gui/manual_config_builder.py
tools/gt_relabel_gui/server.py --mode manual --config CONFIG --root ROOT
```

Current manual GUI page config shape:

```json
{
  "pages": [
    {
      "name": "page_003",
      "page": 3,
      "image": ".../source.png",
      "numbering": ".../numbering_final.json",
      "mmr": ".../overrides_mmr.json",
      "barlines": ".../barlines.json"
    }
  ],
  "manual_outputs": {
    "mmr_measure_span": ".../mmr_measure_spans.json",
    "barline_construction": ".../barline_construction_overrides.json",
    "measure_construction": ".../measure_construction_overrides.json"
  }
}
```

Current GUI behavior:

- loads the configured source image;
- loads measure boxes from the configured numbering artifact;
- optionally loads base MMR records and barline boxes;
- displays MMR rows as `base=<span>` and `effective=<span>`;
- supports `set_measure_span` / `suppress` for MMR measure-span correction;
- supports `add_barline` / `remove_barline` for barline construction correction;
- supports `force_measure` for narrow measure-construction correction;
- saves correction JSON only; evaluation or rerun is explicitly separate;
- allows `manual_outputs` to override the default legacy save paths.

Current limitations for #229:

- `manual_config_builder.py` only packages paths supplied by the caller. It does not validate same score, same run, same page, or same coordinate space.
- The GUI consumes a one-off config shape, not `review/manual_correction_input.json` directly.
- The GUI does not currently treat `review_overlay.png` as a first-class layer. It redraws boxes from JSON on top of the source image.
- The GUI default output paths still point at `data/evaluation2/manual_corrections/` unless overridden.
- There is no user-facing command that starts from `review/manual_correction_input.json`, saves under `review/corrections/`, and then regenerates corrected final applied numbering.

## Comparison with #227 review profile contract

#227 defines the desired review profile surface:

```text
OUTPUT_DIR/
  final/
    <output-name>_score_numbered.pdf
  review/
    run_summary.json
    resolved_config.yaml
    warnings.json
    score_numbering.json
    manual_correction_input.json
    corrections/
      measure_overrides.json
    pages/
      <page_id>/
        source.png
        review_overlay.png
        final_page.png
        numbering_final.json
        barlines_review.json
        mmr_overrides.json
        correction_template.json
```

### Directly adopt from #227

#229 should adopt these #227 decisions without renaming them:

- `review/manual_correction_input.json` is the primary pipeline-to-GUI handoff.
- `review/corrections/` is the default user-editable correction area.
- `review/corrections/measure_overrides.json` remains the #227-compatible `correction_output` target.
- `review/pages/<page_id>/source.png` is the source image used by GUI coordinates.
- `review/pages/<page_id>/numbering_final.json` is the GUI measure/numbering source.
- `review/pages/<page_id>/barlines_review.json` is the GUI barline geometry source when available.
- `review/pages/<page_id>/mmr_overrides.json` is MMR evidence for correction.
- `review/pages/<page_id>/review_overlay.png` is the user inspection overlay.
- `coordinate_space` metadata is required.
- `final/` remains clean and contains only the #228 final score-numbered PDF.

### Missing from current pipeline output

The current internal pipeline output does not yet directly provide the #227 review package. A materializer or adapter must fill the gap.

Required materialization gaps:

| Required review artifact | Current source | Gap |
| --- | --- | --- |
| `review/run_summary.json` | `manifest.json`, `filters.json`, final paths | Needs stable user-facing summary extraction. |
| `review/resolved_config.yaml` | loaded config + CLI/profile defaults | Needs config-resolution materialization. |
| `review/warnings.json` | `filters.json`, page statuses, pipeline warnings | Needs curated warning subset. |
| `review/score_numbering.json` | `outputs/numbering_final.json` | Needs copy/normalization into review. |
| `review/manual_correction_input.json` | no direct current equivalent | Needs new materializer output. |
| `review/pages/<page_id>/source.png` | `inputs/images/<page_id>.png` or original input image path | Needs stable package-local copy/reference and image metadata. |
| `review/pages/<page_id>/review_overlay.png` | `outputs/<page_id>/numbering_overlay.png` | Needs rename/copy; current overlay is review-only. |
| `review/pages/<page_id>/numbering_final.json` | `outputs/<page_id>/numbering_final.json` | Needs package-local copy/reference. |
| `review/pages/<page_id>/barlines_review.json` | `intermediate/<page_id>/barlines_corrected.json` or explicitly resolved raw barlines | Needs normalized review-level barline geometry; must not be guessed from unrelated logs roots. |
| `review/pages/<page_id>/mmr_overrides.json` | `intermediate/<page_id>/overrides_mmr.json` | Needs package-local copy/reference. |
| coordinate-space metadata | implicit in image size / render config | Needs explicit metadata. |
| correction output target | legacy defaults or ad hoc paths | Needs package-local `review/corrections/` paths and overwrite policy. |

## GUI input boundary

### Required handoff properties

`review/manual_correction_input.json` must be self-contained enough for a GUI or adapter to open review artifacts without path guessing.

Required top-level fields:

```json
{
  "schema": "pdfscorebar.manual_correction_input.v1",
  "input_pdf": "score.pdf",
  "output_dir": ".",
  "output_name": "score",
  "run_id": "optional-run-id",
  "final_pdf": "final/score_score_numbered.pdf",
  "score_numbering": "review/score_numbering.json",
  "coordinate_space": {
    "type": "rendered_page_image",
    "origin": "top_left",
    "units": "pixels",
    "dpi": 300,
    "image_size_source": "per_page"
  },
  "correction_output": "review/corrections/measure_overrides.json",
  "correction_outputs": {
    "measure_overrides": "review/corrections/measure_overrides.json",
    "barline_overrides": "review/corrections/barline_overrides.json",
    "mmr_measure_span": "review/corrections/mmr_measure_spans.json",
    "measure_construction": "review/corrections/measure_construction_overrides.json",
    "barline_construction": "review/corrections/barline_construction_overrides.json"
  },
  "save_policy": {
    "default": "keep_existing_user_edits",
    "overwrite_requires_explicit_user_action": true
  },
  "pages": []
}
```

`correction_output` preserves the #227 singular field for the canonical measure-correction file. `correction_outputs` is the #229 extension that carries barline-correction and GUI staging targets. A transitional adapter should accept #227-style handoffs that only contain `correction_output`, but #229 review packages should emit both fields so implementation code can start without guessing output paths.

Required per-page fields:

```json
{
  "page_id": "page_003",
  "page_number": 3,
  "source_image": "review/pages/page_003/source.png",
  "source_image_size": {"width": 3600, "height": 4680},
  "review_overlay": "review/pages/page_003/review_overlay.png",
  "numbering_final": "review/pages/page_003/numbering_final.json",
  "barlines_review": "review/pages/page_003/barlines_review.json",
  "mmr_overrides": "review/pages/page_003/mmr_overrides.json",
  "coordinate_space": {
    "same_as": "source_image",
    "origin": "top_left",
    "units": "pixels"
  }
}
```

The per-page `source_image`, `review_overlay`, `numbering_final`, `mmr_overrides`, and `barlines_review` entries must all refer to artifacts from the same review package and same rendered image coordinate space. For the #215 smoke path, `review_overlay`, `mmr_overrides`, and `barlines_review` are required, not merely recommended, because that smoke must verify both MMR and barline correction paths.

### Prohibited normal workflow

The normal user workflow must not do any of the following:

- infer source image, numbering, MMR, and barline paths by matching only `page_003`;
- mix artifacts from different `logs/issue*/` roots;
- mix different scores or different rendered image sizes in one GUI page config;
- require a user to inspect `manifest.json` or Stage E output directories to find correction inputs;
- write normal correction output to `data/evaluation2/manual_corrections/` unless the user explicitly chooses a legacy/developer path;
- overwrite existing user correction files without explicit user action.

### Transitional adapter

The current GUI does not have to be rewritten before #215 can be re-smoked. A small adapter can translate `review/manual_correction_input.json` into the current GUI config shape.

Adapter responsibility:

1. Read `OUTPUT_DIR/review/manual_correction_input.json`.
2. Validate every referenced page artifact is under the same `OUTPUT_DIR` or explicitly recorded as external.
3. Validate coordinate metadata is present and image sizes match expected page geometry when the data is available.
4. Validate that the correction-smoke path has same-package `source_image`, `numbering_final`, `mmr_overrides`, `barlines_review`, and `review_overlay` entries.
5. Produce the current GUI config shape with `image`, `numbering`, `mmr`, and `barlines` fields mapped from the review package.
6. Override GUI manual outputs to package-local correction paths under `review/corrections/` using current GUI keys: `mmr_measure_span`, `measure_construction`, and `barline_construction`.
7. Accept the #227 singular `correction_output` as the canonical measure override target, prefer #229 `correction_outputs` when present, and generate package-local staging defaults only when that can be done without overwriting user edits.
8. Refuse or warn on missing required smoke artifacts rather than silently substituting unrelated `logs/` paths.

The adapter is transitional. The long-term GUI may read `manual_correction_input.json` directly.

## Correction output design

Manual correction storage has two levels:

1. GUI staging files, matching the current #201 GUI/helper categories.
2. Canonical pipeline correction inputs consumed by rerun/corrected-final generation.

Recommended package layout:

```text
review/corrections/
  mmr_measure_spans.json
  measure_construction_overrides.json
  barline_construction_overrides.json
  measure_overrides.json
  barline_overrides.json
  correction_summary.json
```

Roles:

| File | Role |
| --- | --- |
| `mmr_measure_spans.json` | GUI staging file for `mmr_measure_span` items. Current helper can translate `set_measure_span` and `suppress`. |
| `measure_construction_overrides.json` | GUI staging file for narrow `force_measure` items. Future grouping/divisi operations remain out of scope. |
| `barline_construction_overrides.json` | GUI staging file for `add_barline` / `remove_barline` items. |
| `measure_overrides.json` | Canonical measure-numbering correction input for final numbering rerun. Produced by merging/normalizing MMR measure-span and measure-construction staging files with existing automatic MMR evidence as needed. |
| `barline_overrides.json` | Canonical barline correction input consumed before base numbering when barline correction is applied. |
| `correction_summary.json` | Optional review metadata: saved files, corrected pages, timestamps, warnings, and whether canonical files are up to date. |

The #227-reserved `review/corrections/measure_overrides.json` remains the default canonical measure correction path and is exposed as the singular `correction_output` field. Barline corrections require a separate canonical `barline_overrides.json` because they are applied earlier than measure numbering and are not measure overrides.

## Corrected final output regeneration

The corrected pipeline path should be explicit and reproducible.

Conceptual command shape for a later implementation:

```bash
pdfscorebar apply-corrections OUTPUT_DIR \
  --corrections review/corrections/measure_overrides.json \
  --barline-corrections review/corrections/barline_overrides.json \
  --profile review
```

A later implementation may instead use a `pdfscorebar run ... --corrections ...` form, but it must preserve these semantics:

1. Read the original review package metadata, including input PDF, pages, render settings, output name, and resolved config.
2. Read saved manual correction staging/canonical files from `review/corrections/`.
3. Apply barline corrections before base measure construction when `barline_overrides.json` is present.
4. Apply measure corrections before final applied numbering is rendered.
5. Regenerate `review/score_numbering.json` and `review/pages/<page_id>/numbering_final.json` from the corrected applied numbering.
6. Regenerate `final/<output-name>_score_numbered.pdf` using the #228 final overlay renderer.
7. Record correction input paths, correction timestamp, and corrected-output status in `review/run_summary.json`.
8. Keep correction provenance, before/after details, MMR evidence, and debug geometry out of `final/`.

The workflow may either update the same `OUTPUT_DIR` or create a separate corrected output directory. If it updates the same directory, it must not silently discard previous correction files or hide which correction set produced the current final PDF.

## User operation flow

Intended user flow:

1. Run the pipeline with review artifacts enabled:

   ```bash
   pdfscorebar run score.pdf --output-dir out/score --profile review
   ```

2. Inspect `out/score/review/run_summary.json`, `out/score/review/README.md`, or the review overlay pages to find pages requiring correction.

3. Start the correction GUI from the review handoff:

   ```bash
   pdfscorebar correct out/score/review/manual_correction_input.json
   ```

   Transitional implementation may run an adapter first and then launch:

   ```bash
   python3 tools/gt_relabel_gui/server.py --mode manual --config <adapted-config.json> --root out/score
   ```

4. In the GUI, review the source image, optional review overlay, final numbering boxes, MMR base/effective spans, and review-level barline geometry.

5. Stage corrections:

   - `set_measure_span` or `suppress` for MMR span mistakes;
   - `add_barline` or `remove_barline` for barline construction mistakes;
   - `force_measure` only for the currently supported narrow measure-construction exception.

6. Save correction JSON under `review/corrections/`.

7. Materialize or validate canonical correction inputs:

   ```text
   review/corrections/measure_overrides.json
   review/corrections/barline_overrides.json
   ```

8. Regenerate corrected final applied numbering and the final score-numbered PDF.

9. Open:

   ```text
   final/<output-name>_score_numbered.pdf
   ```

The final PDF shows only row-start labels from corrected final applied numbering. It does not show correction provenance or review/debug geometry.

## Minimum conditions for returning to #215

#215 can be re-smoked once there is a same-package input that avoids the artifact mismatch found in the first attempt.

Minimum conditions:

1. One review package contains matching `source.png`, `review_overlay.png`, `numbering_final.json`, `mmr_overrides.json`, and `barlines_review.json` for the same score, run, page, and rendered image coordinate space.
2. `review/manual_correction_input.json` or a deterministic adapter config references only those same-package artifacts.
3. The GUI output paths are redirected to `review/corrections/`, not the legacy `data/evaluation2/manual_corrections/` defaults.
4. Coordinate-space metadata is present and can be checked by the adapter or smoke script.
5. At least one page can load MMR base/effective rows from same-package MMR evidence.
6. At least one `set_measure_span` or `suppress` item can be staged and saved.
7. At least one barline `add_barline` or `remove_barline` item can be staged and saved.
8. Saved correction JSON can be translated or passed to the current helper layer as canonical `measure_overrides.json` and `barline_overrides.json` inputs.
9. The rerun/corrected-final handoff is documented even if final PDF regeneration is implemented in a later issue.

The first #215 attempt confirmed GUI startup and MMR base/effective display, but did not validate stage/save because the image, numbering, MMR, and barline artifacts came from mismatched score/run/page roots. That issue should remain open until the corrected same-package smoke test is completed.

## Follow-up implementation split

This design should be implemented in small follow-up issues/PRs.

| Follow-up | Scope | Notes |
| --- | --- | --- |
| Profile materializer for correction handoff | Create `review/manual_correction_input.json`, copy/reference page artifacts, write coordinate metadata, preserve correction files. | Must emit #227-compatible `correction_output`, #229 `correction_outputs`, and `barlines_review.json` from retained corrected/raw barline geometry. |
| Manual GUI handoff adapter | Convert `review/manual_correction_input.json` to current GUI config or teach GUI to read it directly. | Must reject arbitrary logs path matching as the normal route and map current GUI output keys without `_staging` suffix. |
| Correction canonicalizer | Convert GUI staging files into `measure_overrides.json` and `barline_overrides.json`. | Should use existing #201 helper semantics and unit tests. |
| Corrected rerun / apply-corrections command | Apply saved corrections and regenerate corrected final applied numbering and final PDF. | Must keep final PDF clean per #228. |
| #215 re-smoke | Run the real-artifact GUI smoke using same-package artifacts. | Confirms stage/save and rerun handoff; does not replace #229 design. |

## Non-goals for #229

#229 does not:

- replace #215 real-artifact smoke testing;
- perform GUI large-scale UI redesign;
- change detector, OCR, MMR classifier, or system grouping algorithms;
- implement #228 final overlay rendering;
- make the current per-measure review overlay a final deliverable;
- make arbitrary `logs/` path discovery a supported user workflow;
- promise backwards compatibility for all legacy experiment paths.

## Acceptance mapping

| #229 acceptance | Design outcome |
| --- | --- |
| #215 result is considered | The first attempt is classified as blocked by mismatched artifacts, so #229 defines same-package handoff conditions and leaves #215 open for re-smoke. |
| Required GUI artifacts are defined | `manual_correction_input.json` top-level and per-page requirements define source image, numbering, MMR, barlines, overlays, coordinate metadata, and correction targets. |
| Correction output path is defined | `review/corrections/` layout separates GUI staging files from canonical `measure_overrides.json` and `barline_overrides.json`, while preserving #227 `correction_output`. |
| Corrected final output path is defined | Saved corrections are applied before final applied numbering and #228 final PDF rendering. |
| User workflow is documented | The operation flow covers review run, page inspection, GUI launch, save, canonicalization, and corrected final output. |
| Follow-up implementation can be split | Materializer, adapter, canonicalizer, corrected rerun, and #215 re-smoke are listed separately. |
