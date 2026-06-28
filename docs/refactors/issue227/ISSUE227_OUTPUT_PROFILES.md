# Issue 227: User-facing Output Profile Contract

## Status

- Parent epic: #225
- Task issue: #227
- Base branch: `develop`
- Depends on: #226 for the formal user-facing entrypoint and profile names
- Scope of this document: output profile and directory contract for `pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR`

This document records the design outcome for #227. It intentionally does not implement the CLI, final overlay renderer, manual correction GUI, detector/OCR/MMR behavior, or a repository cleanup. The goal is to define a stable contract package that follow-up implementation issues can target without continuing to expose experiment and debug artifacts as normal user-facing output.

## Document lifecycle

This file is an issue-scoped design handoff, not the permanent home for user documentation.

After the user-facing CLI and profile materialization are implemented and accepted, the stable parts of this contract should move into formal documentation such as the root `README.md`, `docs/ENVIRONMENTS.md`, a future user guide, or other standing operational docs. At that point, this issue-specific file and its `docs/README.md` index entry should be removed.

Permanent repository behavior must not depend on a document whose only discoverable name is tied to a completed issue number.

## Contract package

#227 is not just a narrative design note. It produces a contract package that follow-up implementation issues can use as an input:

| File | Role |
| --- | --- |
| `ISSUE227_OUTPUT_PROFILES.md` | Primary decision record and profile directory contract. |
| `OUTPUT_PROFILE_CONTRACT_SPEC.yaml` | Structured contract summary for implementers and reviewers. |
| `CURRENT_OUTPUT_MAPPING.md` | Inventory of current pipeline artifacts and their target public profile locations. |
| `IMPLEMENTATION_HANDOFF.md` | Follow-up implementation boundaries and review checklist for CLI/materializer work. |
| `examples/run_summary.review.json` | Example run summary file for a review-profile run. |
| `examples/manual_correction_input.review.json` | Example review-profile handoff file for #229. |

This mirrors #226's split between a public decision, explicit non-goals, a minimal handoff, and follow-up implementation boundaries. #226 defined the user-facing command and deferred file layout to #227; this package defines that layout and defers CLI/materialization code to a follow-up implementation PR.

## Decision summary

The user-facing command from #226 writes a single output directory selected by the user:

```bash
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR
```

`OUTPUT_DIR` is the public output directory. A normal user should be able to open that directory and immediately find useful output without inspecting `logs/`, issue-specific directories, Stage E outputs, or the current internal pipeline layout.

The public output contract is separated into cumulative profile directories:

```text
OUTPUT_DIR/
  final/
  review/
  debug/
```

Only directories required by the selected profile are created:

| Selected profile | Directories created | Intent |
| --- | --- | --- |
| `final` | `final/` | Final PDF deliverable only. This is the default. |
| `review` | `final/`, `review/` | Final PDF plus enough review artifacts for inspection and correction. |
| `debug` | `final/`, `review/`, `debug/<debug-run-id>/` | Final/review artifacts plus timestamped troubleshooting and reproduction artifacts. |

The profile relationship is cumulative. `debug` contains or references artifacts needed for `review`, and `review` contains the final deliverable. The inverse is not true: `final` must remain clean and must not receive review or debug artifacts.

## `--output-dir`, output name, and debug run identity

For the user-facing CLI, `--output-dir` is the exact public output directory. It is not a parent directory to which an implicit timestamp or run identifier is appended for `final` or `review` outputs.

A user running:

```bash
pdfscorebar run score.pdf --output-dir out/score_a
```

expects the final PDF under:

```text
out/score_a/final/score_score_numbered.pdf
```

not under a nested directory such as `out/score_a/20260628_120000/final/...`.

The final PDF file name must be distinguishable across scores. The default final PDF name is:

```text
<output-name>_score_numbered.pdf
```

where `<output-name>` defaults to the sanitized input PDF stem. A later CLI implementation may provide an explicit output-name option or config key. If it does, that explicit name should replace the input stem while preserving the `_score_numbered.pdf` suffix unless a separate final-filename override is intentionally added.

`--run-id`, if accepted by the implementation, is metadata for reproducibility and artifact indexing. It must not silently move `final/` or `review/` outputs. Debug artifacts are the exception: debug output should be stored under a timestamped and/or run-id-bearing subdirectory, for example:

```text
OUTPUT_DIR/debug/20260629_010203_<run-id>/
```

This preserves multiple debug captures for repeated investigations without making normal final/review output paths unstable. If no explicit run id is provided, the debug directory name should still include a timestamp. The chosen debug run id must be recorded in the debug summary or artifact index.

If the current `run_pipeline()` implementation requires `output_root/run_id`, the user-facing CLI implementation should adapt that internally by mapping `OUTPUT_DIR` to the public contract, or by using a private working directory followed by profile materialization. It should not expose legacy `output_root/run_id` nesting as the user contract.

## Root files

The root of `OUTPUT_DIR` should remain small. For the `final` profile, it should contain only the `final/` directory. Metadata such as run summaries, resolved configs, warnings, and artifact indexes belongs in `review/` or `debug/`.

| Path | Required | Profile(s) | Purpose |
| --- | --- | --- | --- |
| `review/run_summary.json` | Yes | `review`, `debug` | Stable review-facing summary: input PDF, selected/effective profile, pages processed, final artifact paths, warnings, and correction status. |
| `review/resolved_config.yaml` | Yes | `review`, `debug` | Resolved execution config after profile defaults, optional config override, and explicit CLI arguments are applied. Required by #226 for reproducibility, but not part of the clean final deliverable. |
| `review/warnings.json` | Optional, recommended when non-empty | `review`, `debug` | User-actionable warnings, such as skipped pages, missing inputs, or pages requiring review. |
| `debug/<debug-run-id>/artifact_index.json` | Yes when artifacts are referenced or relocated | `debug` | Machine-readable index of debug artifacts and their source/retention locations. |
| `review/README.md` or `debug/<debug-run-id>/README.md` | Optional | `review`, `debug` | Short human-readable pointer to the most important files. |

The root must not contain raw pipeline logs, current internal `manifest.json`, issue-specific evaluation contracts, generated zip files, large intermediate directories, warning files, or page images.

## `final` profile

### Purpose

`final` is the default profile for normal use. It contains only the final score-numbered PDF that a user would keep, attach, print, or pass to another program after a successful run.

### Directory contract

```text
OUTPUT_DIR/
  final/
    <output-name>_score_numbered.pdf
```

### File contract

| Path | Required | Notes |
| --- | --- | --- |
| `final/<output-name>_score_numbered.pdf` | Yes once #228 final overlay rendering is implemented | Preferred and only final deliverable: original score pages with final measure-number overlay. `<output-name>` defaults to the sanitized input PDF stem and may later be overridden by CLI/config. |

Until #228 implements final PDF assembly, a transitional implementation may be unable to satisfy the final profile fully. It should not fill `final/` with page PNGs or review overlays as a substitute unless a later issue explicitly accepts that as a temporary compatibility mode. Transitional page images belong in `review/` or `debug/`.

### Explicit exclusions

`final/` must not contain:

- page PNG images;
- warning files;
- run summaries or resolved configs;
- machine-readable numbering JSON;
- source page renders used only for review or debugging;
- per-measure review overlays or geometry-heavy inspection overlays;
- raw barline detector JSON;
- staff, notehead, clef, or candidate masks;
- MMR crop images, OCR traces, classifier scores, or TTA diagnostics;
- `pipeline.log`, stdout/stderr captures, resource sampling logs, or stack traces;
- Issue #120 / Stage E evaluation contracts, benchmark reports, GT paths, or experiment zip files;
- current internal `intermediate/` or `outputs/` directory trees.

The final profile should optimize for “open the result and use the PDF,” not “inspect how it was produced.”

## `review` profile

### Purpose

`review` is for human inspection and correction. It should provide enough information to verify the final numbering and prepare manual corrections without exposing every low-level detector artifact.

### Directory contract

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

### File contract

| Path | Required | Notes |
| --- | --- | --- |
| `review/run_summary.json` | Yes | Review-facing summary and artifact pointers. |
| `review/resolved_config.yaml` | Yes | Resolved execution config for reproducibility. |
| `review/warnings.json` | Optional, recommended when non-empty | User-actionable warnings. All warning output belongs in `review` or `debug`, not `final`. |
| `review/score_numbering.json` | Yes | Stable machine-readable final numbering output. It represents final applied numbering, including accepted automatic MMR and manual corrections, but is review/tooling output rather than final deliverable. |
| `review/manual_correction_input.json` | Yes | Stable handoff file for #229. It should point to page images, review overlays, final numbering, and editable correction target paths. |
| `review/corrections/measure_overrides.json` | Reserved | Default save location for manual corrections. The pipeline must not overwrite an existing user-edited file without explicit overwrite mode. It may create an empty/template file for first review. |
| `review/pages/<page_id>/source.png` | Yes for review | Rendered page image in the coordinate space used by review artifacts. If images are too large to duplicate, `manual_correction_input.json` may reference the stored path, but the path must be under `OUTPUT_DIR` or explicitly recorded as external. |
| `review/pages/<page_id>/review_overlay.png` | Yes | Inspection overlay. Current per-measure / measure-range overlay belongs here, not in `final/`, unless #228 later defines a separate final overlay format from it. |
| `review/pages/<page_id>/final_page.png` | Optional until final PDF assembly is implemented | Page-level final visual artifact for review. This is not part of `final/`; it is a review aid. |
| `review/pages/<page_id>/numbering_final.json` | Yes | Page-level final numbering used by the review overlay and GUI. |
| `review/pages/<page_id>/barlines_review.json` | Recommended | Review-level barline geometry after accepted barline overrides. It should be sufficient for GUI inspection but not include every detector candidate or model trace. |
| `review/pages/<page_id>/mmr_overrides.json` | Recommended when MMR is enabled | Proposed skip / span adjustments from MMR after normalization. This is review evidence, not final user output. |
| `review/pages/<page_id>/correction_template.json` | Optional | Per-page correction scaffold for manual editing or GUI initialization. |

### Review exclusions

`review/` should not contain heavy or highly internal artifacts unless a reviewer needs them for ordinary correction. In particular, avoid putting the full hybrid detector tree, CNN crops, OCR crop images, resource sampling logs, or large stdout/stderr captures in `review/`. Those belong in timestamped debug output.

## `debug` profile

### Purpose

`debug` is for developers and issue investigations. It may be noisy and large, but it must remain separated from `final/` and ordinary `review/` surfaces. Unlike `final` and `review`, debug output should preserve a timestamp/run-id layer so repeated diagnostic captures do not overwrite each other.

### Directory contract

```text
OUTPUT_DIR/
  final/
    <output-name>_score_numbered.pdf
  review/
    ...
  debug/
    <debug-run-id>/
      pipeline.log
      stdout_stderr.log
      manifest.json
      filters.json
      environment.json
      resource_samples.jsonl
      resource_summary.json
      artifact_index.json
      inputs/
        images/
      intermediate/
        <page_id>/
          numbering_base.json
          barlines_corrected.json
          overrides_combined.json
      detection/
        hybrid/
        probe_scan/
        cnn_scoring/
      mmr/
        <page_id>/
      legacy_current_layout/
```

`<debug-run-id>` should include a timestamp and should include the explicit run id when one is provided. Example: `20260629_010203_issue227_probe`.

### File contract

| Path | Required | Notes |
| --- | --- | --- |
| `debug/<debug-run-id>/pipeline.log` | Yes when available | Pipeline logging at diagnostic level. |
| `debug/<debug-run-id>/stdout_stderr.log` | Optional | Captured external tool stdout/stderr when available. |
| `debug/<debug-run-id>/manifest.json` | Yes | Current or future internal manifest, including command traces and resolved raw paths. This is intentionally not the review `run_summary.json`. |
| `debug/<debug-run-id>/filters.json` | Recommended | Page filter status and skip reasons. User-actionable subset may also appear in `review/warnings.json`. |
| `debug/<debug-run-id>/environment.json` | Recommended | Python/package/runtime/GPU availability summary when available. |
| `debug/<debug-run-id>/resource_samples.jsonl` and `debug/<debug-run-id>/resource_summary.json` | Optional | Runtime/resource traces when explicitly captured. |
| `debug/<debug-run-id>/artifact_index.json` | Yes when artifacts are referenced or relocated | Maps profile paths to internal, external, or legacy artifact locations. |
| `debug/<debug-run-id>/inputs/images/` | Optional | Rendered source images when retained for reproduction. |
| `debug/<debug-run-id>/intermediate/<page_id>/` | Recommended | Page-level base numbering, corrected barlines, combined overrides, and other intermediate JSON required to reproduce final numbering. |
| `debug/<debug-run-id>/detection/` | Optional but recommended for detector investigations | Hybrid, probe scan, CNN scoring, masks, candidates, and model outputs. If not copied, record stable references in `artifact_index.json`. |
| `debug/<debug-run-id>/mmr/<page_id>/` | Optional but recommended for MMR investigations | Crops, OCR evidence, classifier scores, and TTA diagnostics. |
| `debug/<debug-run-id>/legacy_current_layout/` | Transitional only | If implementation initially uses the current pipeline layout as an internal working tree, it may be copied or moved here. This path must not become the long-term public contract. |

## Profile selection and `--debug`

`--profile` is the primary public selector:

```bash
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR --profile final
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR --profile review
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR --profile debug
```

Default profile is `final`.

`--debug` should not add debug files into `final/`. If retained for compatibility with #226, it should be treated as a request to retain debug artifacts under `debug/<debug-run-id>/`, either by selecting effective profile `debug` or by adding a debug capture alongside the explicitly selected profile. The effective profile, requested flags, and chosen `<debug-run-id>` must be recorded in `review/run_summary.json` and/or `debug/<debug-run-id>/artifact_index.json`.

## Handoffs

### #228 final overlay format

#228 should define the actual visual content of the final score-numbered PDF and write it into the `final/` contract above.

Until #228 is complete, the current `numbering_overlay.png` should be considered a review overlay and placed under `review/pages/<page_id>/review_overlay.png`, not treated as the stable final PDF. Transitional page images should remain in `review/` or `debug/`.

### #229 manual correction workflow

#229 should treat `review/manual_correction_input.json` as the primary pipeline-to-GUI handoff file.

Minimum required content:

- input PDF path or recorded source identifier;
- selected pages and page IDs;
- path to each review source image;
- path to each review overlay;
- path to each page-level `numbering_final.json`;
- path to review-level barline geometry if available;
- path to MMR override evidence if available;
- reserved correction output path, initially `review/corrections/measure_overrides.json`;
- coordinate-space metadata needed to interpret image and geometry paths.

The GUI should save corrections to `review/corrections/measure_overrides.json` by default. A corrected rerun should consume that file through a later CLI/config option without overwriting original review evidence. If a future workflow writes a corrected final deliverable in the same `OUTPUT_DIR`, it should record the correction input path and correction timestamp in `review/run_summary.json`.

## Non-goals for #227

#227 does not:

- implement the `pdfscorebar run` CLI;
- add console-script packaging;
- add config-first profile flags to `src/pipeline/main.py`;
- implement a profile materializer;
- define final overlay drawing details;
- launch or integrate the manual correction GUI;
- delete historical experiment artifacts;
- change detector, OCR, MMR, numbering, or overlay algorithms.

These boundaries keep #227 parallel to #226: it defines the public contract and implementation handoff, while code changes remain for follow-up PRs.

## Follow-up implementation split

The contract package is intended to support separate follow-up PRs rather than fold unrelated work into #227.

| Follow-up | Owns | Must reference |
| --- | --- | --- |
| Profile materializer | Convert current internal run layout into `final` / `review` / `debug/<debug-run-id>`. | `OUTPUT_PROFILE_CONTRACT_SPEC.yaml`, `CURRENT_OUTPUT_MAPPING.md`, and `IMPLEMENTATION_HANDOFF.md`. |
| User-facing CLI implementation | Connect #226 `pdfscorebar run` to the materializer and config resolution. | #226 CLI design plus this output contract. |
| #228 final overlay | Define and write final PDF artifacts under `final/`. | `final` profile contract and output naming rules. |
| #229 manual correction workflow | Consume review handoff and write correction output. | `review/manual_correction_input.json` example and overwrite policy. |

## Acceptance mapping

| #227 acceptance | Contract package outcome |
| --- | --- |
| The purposes of final / review / debug profiles are defined | Profile purpose sections and cumulative profile table. |
| The output file list and directory contract for each profile are provided | Root, `final`, `review`, and timestamped `debug` directory/file contracts plus `OUTPUT_PROFILE_CONTRACT_SPEC.yaml`. |
| What to include and exclude in the final output is clarified | `final` file contract and explicit exclusions: final contains only the score-numbered PDF. |
| Review / debug outputs are defined to the extent necessary for reproducibility and troubleshooting | `review`, timestamped `debug`, `CURRENT_OUTPUT_MAPPING.md`, and handoff examples. |
| The specification is ready to be handed off to follow-up implementation issues | Structured spec, examples, and `IMPLEMENTATION_HANDOFF.md`. |
