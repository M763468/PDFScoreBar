# Issue 226: User-facing PDF Pipeline Entrypoint Design

## Status

- Parent epic: #225
- Task issue: #226
- Base branch: `develop`
- Scope of this document: design decision and implementation handoff for the user-facing PDF pipeline entrypoint.

This document records the design outcome for #226. It intentionally does not implement the CLI. The goal is to define a clean user-facing surface, classify existing entrypoints, and prevent future implementation work from duplicating pipeline logic across Makefile targets, Python scripts, and package commands.

## Document lifecycle

This file is an issue-scoped design handoff, not the permanent home for the user-facing pipeline documentation.

After the user-facing CLI is implemented and accepted, the stable parts of this design must be moved into formal documentation such as the root `README.md`, `docs/ENVIRONMENTS.md`, a future user guide, and/or the relevant operational docs. At that point, this issue-specific document and its `docs/README.md` index entry should be removed.

Permanent repository behavior must not depend on a document whose only discoverable name is tied to a completed issue number.

## Decision

Adopt a new, thin user-facing CLI command as the formal public entrypoint:

```bash
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR
```

The command is PDF-first. A normal user should not need to identify an issue-specific config, Stage E runner, Makefile target, or artifact-replay script before running PDFScoreBar on a PDF.

Existing config-driven and Makefile-driven entrypoints remain available for development, experiment, evaluation, and artifact reproduction workflows. They are not the public user-facing command surface.

## Non-goals for #226

#226 does not change detector, OCR, MMR, CNN, final overlay, or manual correction behavior.

#226 does not implement the new CLI. Implementation should be done in a smaller follow-up PR after this design is accepted.

#226 does not define the complete output directory contract. That belongs to #227.

#226 does not define the final score-number overlay rendering details. That belongs to #228.

#226 does not connect the manual correction GUI workflow. That belongs to #229.

#226 does not classify the entire public repository surface. That belongs to #230.

## Entrypoint hierarchy

The repository should use one pipeline execution core and multiple thin entrypoint layers around it. Pipeline behavior must not be reimplemented in Makefile targets or CLI wrappers.

| Layer | Role | Audience | Status |
| --- | --- | --- | --- |
| `run_pipeline(config_path, ...)` | Core config-driven execution API | Internal / developer | Keep as the execution core |
| `src/pipeline/main.py --config ...` | Config-first Python entrypoint | Developer / advanced users | Keep, but do not present as the primary user command |
| `pdfscorebar run INPUT.pdf ...` | PDF-first official command | Users | New formal user-facing entrypoint |
| `make run-pipeline CONFIG=...` | Docker/local wrapper around config-driven execution | Developers / validation | Keep as environment wrapper |
| Stage E / Issue #120 make targets | Contract validation and artifact reproduction | Evaluation / debugging | Keep outside the user-facing surface |
| `src/pdf_to_images.py` | PDF rendering helper | Developer / helper | Keep as helper |
| `tools/add_measure_numbers.py` | Numbering/overlay helper for existing barline and staff-mask artifacts | Developer / debug | Keep as helper/debug |
| `tools/issue*` scripts | Issue-specific experiments and evaluations | Experiment / legacy / reproduction | Keep or archive according to #230 |

## Makefile role

The Makefile is not the formal user-facing product API.

Its role is to provide reproducible local development, Docker, validation, and evaluation wrappers. A Makefile target may later be added as a convenience wrapper around `pdfscorebar run`, for example:

```bash
make run-user PDF=input.pdf OUT=out/run1
```

If such a target is added, it must call `pdfscorebar run` or the same CLI module without duplicating pipeline configuration logic. Makefile variables must not become a second source of truth for profiles, output contracts, or pipeline steps.

Current `make run-pipeline CONFIG=...` remains a config-first developer/Docker wrapper. It should not be documented as the primary user command after the new user CLI exists.

## Packaging and command design

The formal command name is:

```bash
pdfscorebar
```

The first formal subcommand is:

```bash
pdfscorebar run
```

Short-term implementation may attach the console script to the current source layout to avoid a broad package refactor. A possible short-term shape is:

```toml
[project.scripts]
pdfscorebar = "src.pipeline.user_cli:main"
```

This is an implementation detail, not the desired long-term public import surface.

Longer term, #230 or a later repository-surface task should consider moving the public command module to a stable package namespace such as:

```toml
[project.scripts]
pdfscorebar = "pdfscorebar.cli:main"
```

and exposing a library-level API such as:

```python
from pdfscorebar import run_pdf
```

The library API should not be declared as stable in #226. The stable surface from this issue is the CLI command shape and its relationship to the existing config-driven pipeline.

## Minimal CLI specification

The initial user-facing command should be:

```bash
pdfscorebar run INPUT.pdf \
  --output-dir OUTPUT_DIR \
  [--pages PAGES] \
  [--profile final|review|debug] \
  [--config CONFIG.yaml] \
  [--run-id RUN_ID] \
  [--skip-existing] \
  [--debug]
```

### Required arguments

| Argument | Meaning |
| --- | --- |
| `INPUT.pdf` | PDF score to process |
| `--output-dir OUTPUT_DIR` | User-visible output root for the run |

`--output-dir` should be required in the first implementation to avoid ambiguous writes into issue-specific `logs/` paths. A later UX pass may introduce a safe default such as `outputs/<pdf-stem>/` after #227 defines the output contract.

### Optional arguments

| Option | Meaning | Maps to |
| --- | --- | --- |
| `--pages` | Page selection, e.g. `1`, `1,2,5`, or a later range syntax | `inputs.pdf_to_images.pages` |
| `--profile` | Output/profile mode; default `final` | #227-defined profile settings |
| `--config` | Advanced user/developer override config | Config merge layer |
| `--run-id` | Explicit run identifier | `run.run_id` / `run_pipeline(run_id=...)` |
| `--skip-existing` | Reuse existing outputs where safe | `run_pipeline(skip_existing=True)` |
| `--debug` | Emit debug artifacts | `run_pipeline(debug=True)` and profile-specific debug settings |

The first implementation should avoid adding many pipeline-specific flags. Advanced detector/OCR/MMR parameters should continue to live in config files unless a repeated user-facing need justifies promoting them to CLI options.

## Config layering

The CLI must not create an independent configuration system. It should generate or merge the same config schema already consumed by `run_pipeline()`.

Config resolution order:

```text
built-in profile defaults < optional --config override < explicit CLI arguments
```

Required behavior:

1. Start from a built-in user profile, initially `final`.
2. If `--config` is provided, merge it on top of the built-in profile.
3. Apply explicit CLI arguments last.
4. Write the resolved config into the run directory for reproducibility.
5. Call the existing config-driven execution core.

The CLI should at minimum set or override:

```yaml
run:
  output_root: <OUTPUT_DIR or parent according to #227>
  run_id: <RUN_ID if provided>

inputs:
  pdf_path: <INPUT.pdf>
  pdf_to_images:
    pages: <--pages if provided>

steps:
  pdf_to_images: true
  detection: true
  filter_pages: true
  numbering_base: true
  mmr_overrides: true
  apply_measure_overrides: true
  overlay: true
```

Exact output path semantics are deferred to #227. The implementation must avoid hard-coding the current issue-specific `logs/issue120_*` layout into the user CLI.

## Output profile handoff

#226 reserves the profile names:

- `final`
- `review`
- `debug`

Their exact file lists, directory names, retention rules, and artifact visibility belong to #227.

Expected intent:

| Profile | Intent |
| --- | --- |
| `final` | User-facing output only; no noisy experiment artifacts |
| `review` | Enough overlays and JSON to inspect and correct mistakes |
| `debug` | Developer/debug artifacts for reproducing failures |

The CLI should accept `--profile`, but the implementation should not finalize file layout beyond what #227 defines.

## Relationship to existing evaluation and experiment routes

Stage E and Issue #120 routes are retained as evaluation/contract routes. They validate the full pipeline and reproduce historical detector evidence, but they are not the normal user command.

The user-facing CLI must not require:

- Issue #120 artifact roots.
- Stage E output directories.
- Evaluation GT directories.
- Manual path discovery through `logs/`.
- Direct use of `tools/issue120/*`.

Experiment routes may continue using their existing Makefile targets and scripts. #230 can later decide which routes remain visible, move under `experiments/`, or become legacy-only.

## Implementation handoff

A follow-up implementation PR should be small and should not alter detection, OCR, MMR, or overlay semantics.

Suggested first implementation scope:

1. Add a user CLI module with `pdfscorebar run` parsing.
2. Add `[project.scripts] pdfscorebar = ...` to `pyproject.toml`.
3. Add a minimal built-in `final` profile or default config builder.
4. Resolve `INPUT.pdf`, `--output-dir`, `--pages`, `--config`, `--run-id`, `--skip-existing`, and `--debug` into the existing pipeline config schema.
5. Write the resolved config into the run output for reproducibility.
6. Call the existing `run_pipeline()` execution core.
7. Add lightweight tests for argument parsing and config resolution.
8. Document the user command without changing Stage E or evaluation docs into user-facing docs.

Implementation should not add new dependencies unless explicitly approved.

After that implementation is accepted, promote the stable user-facing behavior into permanent documentation and remove this issue-scoped design document. The implementation PR or its immediate follow-up should update `docs/README.md` accordingly so this file no longer appears as the only indexed source for the formal command.

## Acceptance mapping

| #226 acceptance | Design outcome |
| --- | --- |
| PDF を指定して実行する正式 entrypoint が 1 つに決まっている | `pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR` |
| 既存の実験用・評価用コマンドとの差が説明されている | Entrypoint hierarchy and evaluation-route sections |
| 利用者向け CLI/API の最小仕様案が残っている | Minimal CLI specification and packaging sections |
| 後続の output profile / final overlay / GUI workflow issue が参照できる | Handoff to #227, #228, #229, #230 |
| production code 変更を含む場合は小さく分離する判断ができている | Implementation handoff section |
