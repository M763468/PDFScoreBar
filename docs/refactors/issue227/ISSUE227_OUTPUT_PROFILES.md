# Issue 227: User-facing Output Profile Contract

## Status

- Parent epic: #225
- Task issue: #227
- Base branch: `develop`
- Depends on: #226 for the formal user-facing entrypoint and profile names
- Scope of this document: output profile and directory contract design for `pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR`.

This document records the design outcome for #227. It intentionally does not implement the final overlay renderer or manual correction GUI integration. The goal is to define a stable output contract that follow-up implementation issues can target without continuing to expose experiment and debug artifacts as normal user-facing output.

## Document lifecycle

This file is an issue-scoped design handoff, not the permanent home for user documentation.

After the user-facing CLI and profile materialization are implemented and accepted, the stable parts of this contract should move into formal documentation such as the root `README.md`, `docs/ENVIRONMENTS.md`, a future user guide, or other standing operational docs. At that point, this issue-specific file and its `docs/README.md` index entry should be removed.

Permanent repository behavior must not depend on a document whose only discoverable name is tied to a completed issue number.

## Implementation status in this PR

This PR includes an initial implementation of the profile materialization layer:

- `src/pipeline/output_profiles.py` defines the `final`, `review`, and `debug` profile materializer.
- `src/pipeline/main.py` exposes optional config-first flags:

```bash
python -m src.pipeline.main --config CONFIG.yaml \
  --output-profile final|review|debug \
  [--profile-output-dir OUTPUT_DIR]
```

This is not the final #226 user-facing `pdfscorebar run` CLI. It is a reusable implementation layer that the future user-facing CLI can call after running the existing config-driven pipeline.

The implementation deliberately does not implement #228 final overlay rendering or #229 GUI launch behavior. It only maps artifacts that the current pipeline already produces.

## Decision summary

The user-facing command from #226 writes a single run directory selected by the user:

```bash
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR
```

`OUTPUT_DIR` is the public run directory. A normal user should be able to open that directory and immediately find the useful output without inspecting `logs/`, issue-specific directories, or current internal pipeline layout.

The public output contract is separated into three profile directories:

```text
OUTPUT_DIR/
  run_summary.json
  resolved_config.yaml
  final/
  review/
  debug/
```

Only directories required by the selected profile are created:

| Selected profile | Directories created | Intent |
| --- | --- | --- |
| `final` | `final/` | User-facing deliverables only. This is the default. |
| `review` | `final/`, `review/` | Final deliverables plus enough review artifacts for inspection and correction. |
| `debug` | `final/`, `review/`, `debug/` | Full troubleshooting and reproduction artifacts. |

The profile relationship is intentionally cumulative. `debug` contains or references the artifacts needed for `review`, and `review` contains the final deliverables. The inverse is not true: `final` must remain clean and must not receive review or debug artifacts.

## `--output-dir` and `--run-id` semantics

For the user-facing CLI, `--output-dir` is the exact public run directory. It is not a parent directory to which an implicit timestamp or run identifier is appended.

A user running:

```bash
pdfscorebar run score.pdf --output-dir out/score_a
```

expects the final artifacts under:

```text
out/score_a/final/
```

not under a later nested directory such as `out/score_a/20260628_120000/final/`.

`--run-id`, if accepted by the implementation, is metadata for reproducibility and artifact indexing. It must not silently move the public output directory. If the current `run_pipeline()` implementation requires `output_root/run_id`, the first CLI implementation should adapt that internally by mapping `OUTPUT_DIR.parent` and `OUTPUT_DIR.name`, or by using a private working directory followed by profile materialization. It should not expose the legacy `output_root/run_id` nesting as the user contract.

## Common root files

The root of `OUTPUT_DIR` is deliberately small. It may contain only files that help users and tools understand the run as a whole.

| Path | Required | Profile(s) | Purpose |
| --- | --- | --- | --- |
| `run_summary.json` | Yes | all | Stable user-facing summary: input PDF, selected/effective profile, pages processed, final artifact paths, warnings, and correction status. |
| `resolved_config.yaml` | Yes | all | Resolved execution config after profile defaults, optional config override, and explicit CLI arguments are applied. Required by #226 for reproducibility. |
| `artifact_index.json` | Optional | `review`, `debug` | Machine-readable index of non-final artifacts. Required when debug artifacts are referenced rather than copied into `debug/`. |
| `README.txt` or `README.md` | Optional | all | Short human-readable pointer to the most important files. |

The root must not contain raw pipeline logs, current internal `manifest.json`, issue-specific evaluation contracts, generated zip files, or large intermediate directories. Those belong under `debug/` or outside the user-facing output contract.

## `final` profile

### Purpose

`final` is the default profile for normal use. It contains the artifacts a user would keep, attach, or pass to another program after a successful run.

### Directory contract

```text
OUTPUT_DIR/
  run_summary.json
  resolved_config.yaml
  final/
    score_numbered.pdf
    score_numbering.json
    pages/
      <page_id>.png
    warnings.json
```

### File contract

| Path | Required | Notes |
| --- | --- | --- |
| `final/score_numbered.pdf` | Required once #228 final overlay rendering is implemented | Preferred final deliverable: the original score pages with final measure-number overlay. Until PDF assembly exists, implementation may omit this and declare the transitional page PNG outputs in `run_summary.json`. |
| `final/pages/<page_id>.png` | Transitional required until `score_numbered.pdf` is implemented; optional afterward | Page-level final overlay images. These are final overlays, not the current review/debug overlay unless #228 explicitly accepts that format. |
| `final/score_numbering.json` | Yes | Stable machine-readable final numbering output. This should represent the final applied numbering, including accepted automatic MMR and manual corrections, without exposing raw detector/MMR internals. |
| `final/warnings.json` | Optional, but recommended when non-empty | User-actionable warnings only, such as skipped pages, missing inputs, or pages requiring review. Empty or purely diagnostic logs should not be written here. |

### Explicit exclusions

`final/` must not contain:

- source page renders used only for review or debugging;
- per-measure review overlays or geometry-heavy inspection overlays;
- raw barline detector JSON;
- staff, notehead, clef, or candidate masks;
- MMR crop images, OCR traces, classifier scores, or TTA diagnostics;
- `pipeline.log`, stdout/stderr captures, resource sampling logs, or stack traces;
- Issue #120 / Stage E evaluation contracts, benchmark reports, GT paths, or experiment zip files;
- current internal `intermediate/` or `outputs/` directory trees.

The final profile should optimize for “open the result and use it,” not “debug how it was produced.”

## `review` profile

### Purpose

`review` is for human inspection and correction. It should provide enough information to verify the final numbering and prepare manual corrections without exposing every low-level detector artifact.

### Directory contract

```text
OUTPUT_DIR/
  run_summary.json
  resolved_config.yaml
  final/
    ...
  review/
    manual_correction_input.json
    corrections/
      measure_overrides.json
    pages/
      <page_id>/
        source.png
        review_overlay.png
        numbering_final.json
        barlines_review.json
        mmr_overrides.json
        correction_template.json
```

### File contract

| Path | Required | Notes |
| --- | --- | --- |
| `review/manual_correction_input.json` | Yes | Stable handoff file for #229. It should point to the page images, review overlays, final numbering, and editable correction target paths. |
| `review/corrections/measure_overrides.json` | Reserved | Default save location for manual corrections. The pipeline must not overwrite an existing user-edited file without an explicit overwrite mode. It may create an empty/template file for first review. |
| `review/pages/<page_id>/source.png` | Yes for review | Rendered page image at the coordinate space used by review artifacts. If images are too large to duplicate, `manual_correction_input.json` may reference the actual stored path, but the path must be under `OUTPUT_DIR` or explicitly recorded as external. |
| `review/pages/<page_id>/review_overlay.png` | Yes | Inspection overlay. The current per-measure / measure-range overlay belongs here, not in `final/`, unless #228 later defines a separate final overlay format from it. |
| `review/pages/<page_id>/numbering_final.json` | Yes | Page-level final numbering used by the review overlay and GUI. |
| `review/pages/<page_id>/barlines_review.json` | Recommended | Review-level barline geometry after accepted barline overrides. It should be sufficient for GUI inspection but not include every detector candidate or model trace. |
| `review/pages/<page_id>/mmr_overrides.json` | Recommended when MMR is enabled | Proposed skip / span adjustments from MMR after normalization. This is review evidence, not final user output. |
| `review/pages/<page_id>/correction_template.json` | Optional | Per-page correction scaffold for manual editing or GUI initialization. |

### Review exclusions

`review/` should not contain heavy or highly internal artifacts unless a reviewer needs them for ordinary correction. In particular, avoid putting the full hybrid detector tree, CNN crops, OCR crop images, resource sampling logs, or large stdout/stderr captures in `review/`. Those belong in `debug/`.

## `debug` profile

### Purpose

`debug` is for developers and issue investigations. It may be noisy and large, but it must remain separated from the `final/` and ordinary `review/` surfaces.

### Directory contract

```text
OUTPUT_DIR/
  run_summary.json
  resolved_config.yaml
  final/
    ...
  review/
    ...
  debug/
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

### File contract

| Path | Required | Notes |
| --- | --- | --- |
| `debug/pipeline.log` | Yes when available | Pipeline logging at diagnostic level. |
| `debug/stdout_stderr.log` | Optional | Captured external tool stdout/stderr when available. |
| `debug/manifest.json` | Yes | Current or future internal manifest, including command traces and resolved raw paths. This is intentionally not the root `run_summary.json`. |
| `debug/filters.json` | Recommended | Page filter status and skip reasons. User-actionable subset may also appear in `final/warnings.json`. |
| `debug/environment.json` | Recommended | Python/package/runtime/GPU availability summary when available. |
| `debug/resource_samples.jsonl` and `debug/resource_summary.json` | Optional | Runtime/resource traces when explicitly captured. |
| `debug/artifact_index.json` | Yes when artifacts are referenced or relocated | Maps profile paths to internal, external, or legacy artifact locations. |
| `debug/inputs/images/` | Optional | Rendered source images when retained for reproduction. |
| `debug/intermediate/<page_id>/` | Recommended | Page-level base numbering, corrected barlines, combined overrides, and other intermediate JSON required to reproduce final numbering. |
| `debug/detection/` | Optional but recommended for detector investigations | Hybrid, probe scan, CNN scoring, masks, candidates, and model outputs. If not copied, record stable references in `debug/artifact_index.json`. |
| `debug/mmr/<page_id>/` | Optional but recommended for MMR investigations | Crops, OCR evidence, classifier scores, and TTA diagnostics. |
| `debug/legacy_current_layout/` | Transitional only | If the implementation initially uses the current pipeline layout as an internal working tree, it may be copied or moved here. This path must not become the long-term public contract. |

## Current pipeline output inventory and mapping

The current integrated pipeline writes useful artifacts, but their locations are implementation-oriented rather than user-oriented. The profile materializer should map them as follows.

| Current / legacy artifact | Public profile location | Notes |
| --- | --- | --- |
| `run_dir/pipeline.log` | `debug/pipeline.log` | Diagnostic only. |
| `run_dir/manifest.json` | `debug/manifest.json`; selected stable fields in `run_summary.json` | The internal manifest may include command traces and raw paths, so it is not a final artifact. |
| `run_dir/filters.json` | `debug/filters.json`; actionable subset in `final/warnings.json` | Keep detailed page filter data out of final unless it is user-actionable. |
| `run_dir/inputs/images/` | `review/pages/<page_id>/source.png` and/or `debug/inputs/images/` | Review needs a stable coordinate-space source image; final should not retain source renders unless required by the final deliverable format. |
| `run_dir/intermediate/<page_id>/numbering_base.json` | `debug/intermediate/<page_id>/numbering_base.json` | Base numbering before MMR/manual correction is debug evidence. |
| `run_dir/intermediate/<page_id>/barlines_corrected.json` | `review/pages/<page_id>/barlines_review.json` and/or `debug/intermediate/<page_id>/barlines_corrected.json` | Review may use a normalized, user-inspectable subset. |
| `run_dir/intermediate/<page_id>/overrides_mmr.json` | `review/pages/<page_id>/mmr_overrides.json`; debug copy if needed | MMR evidence is relevant for correction but should not appear in final. |
| `run_dir/intermediate/<page_id>/overrides_combined.json` | `debug/intermediate/<page_id>/overrides_combined.json` | Applied merge detail is debug evidence. Review should use a cleaner correction input. |
| `run_dir/outputs/<page_id>/numbering_final.json` | `review/pages/<page_id>/numbering_final.json`; aggregated into `final/score_numbering.json` | Page-level detail remains available in review. |
| `run_dir/outputs/<page_id>/numbering_overlay.png` | `review/pages/<page_id>/review_overlay.png` | Current overlay is review-oriented until #228 defines the final overlay format. |
| `run_dir/outputs/numbering_final.json` | `final/score_numbering.json` | This is the closest current artifact to the final machine-readable numbering. |
| `logs/hybrid_generalization/<run_id>/...` | `debug/detection/hybrid/` or `debug/artifact_index.json` reference | Detection internals must not leak into final/review by default. |
| `run_dir/intermediate/probe_scan/...` | `debug/detection/probe_scan/` | Detector evidence. |
| Issue-specific `logs/issue*/...`, evaluation contracts, GT reports, experiment zips | Outside user output; only `debug/` reference when needed for a specific investigation | These are not normal CLI output artifacts. |

## Profile selection and `--debug`

`--profile` is the primary public selector:

```bash
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR --profile final
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR --profile review
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR --profile debug
```

Default profile is `final`.

`--debug` should not add debug files into `final/`. If retained for compatibility with #226, it should be treated as a request to retain debug artifacts under `debug/`, either by selecting effective profile `debug` or by adding `debug/` alongside the explicitly selected profile. The effective profile and requested flags must be recorded in `run_summary.json`.

## Manual correction handoff for #229

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

The GUI should save corrections to `review/corrections/measure_overrides.json` by default. A corrected rerun should consume that file through a later CLI/config option without overwriting the original review evidence. If a future workflow writes a corrected final deliverable in the same `OUTPUT_DIR`, it should record the correction input path and correction timestamp in `run_summary.json`.

## Final overlay handoff for #228

#228 should define the actual visual content of the final score-number overlay and write it into the `final/` contract above.

Until #228 is complete, the current `numbering_overlay.png` should be considered a review overlay and placed under `review/pages/<page_id>/review_overlay.png`, not treated as the stable final overlay. A transitional implementation may write page PNGs under `final/pages/`, but it must clearly mark the renderer status in `run_summary.json`.

## Implementation guidance for follow-up PRs

The implementation should prefer one profile-materialization layer over scattering profile-specific paths throughout detector, MMR, numbering, and overlay code.

Recommended shape:

1. Execute the existing config-driven pipeline into a private or internal working layout.
2. Build a normalized artifact inventory from the manifest and known current paths.
3. Materialize the selected public profile directories from that inventory.
4. Write `run_summary.json`, `resolved_config.yaml`, and optional `artifact_index.json` last.
5. Keep `final/` clean even when the internal pipeline produces debug artifacts.

Existing experiment and evaluation routes may keep their current `logs/` layout. The user-facing CLI must not require users to inspect or understand those paths.

## Acceptance mapping

| #227 acceptance | Design outcome |
| --- | --- |
| final / review / debug profile の目的が定義されている | See the profile purpose sections and cumulative profile table. |
| 各 profile の出力ファイル一覧と directory contract がある | See the root, `final`, `review`, and `debug` directory/file contracts. |
| final output に含めるものと含めないものが明確になっている | See `final` file contract and explicit exclusions. |
| review / debug output が再現性や問題調査に必要な範囲で定義されている | See `review`, `debug`, and current-output mapping sections. |
| 後続の実装 issue に渡せる仕様になっている | See implementation guidance and #228/#229 handoff sections. |
