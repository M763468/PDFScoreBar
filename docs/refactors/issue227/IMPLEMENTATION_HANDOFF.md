# Issue 227: Implementation Handoff

This file defines what a follow-up implementation PR should and should not do when applying the #227 output profile contract.

#227 itself does not implement the CLI or materializer. It defines the target contract.

## Recommended follow-up split

### Follow-up A: profile materialization layer

Purpose: convert the current internal run layout into the public `final` / `review` / `debug` directory contract.

Suggested scope:

1. Add a materializer module that accepts an existing internal `run_dir` and a public `OUTPUT_DIR`.
2. Read current known artifacts from `manifest.json`, `filters.json`, `inputs/images`, `intermediate`, and `outputs`.
3. Write root `run_summary.json` and `resolved_config.yaml` for all profiles.
4. Materialize `final/score_numbering.json` from `outputs/numbering_final.json` or page-level outputs.
5. Materialize `review/manual_correction_input.json` and curated per-page review artifacts.
6. Materialize `debug/` only for debug profile or effective-debug mode.
7. Preserve existing `review/corrections/measure_overrides.json` unless explicit overwrite is requested.
8. Add tests using a fake internal run tree; do not run detector/OCR/MMR in these tests.

Out of scope for this follow-up:

- final overlay visual design;
- PDF assembly;
- GUI launch or edit workflow;
- algorithmic detector/OCR/MMR changes;
- repository cleanup of historical artifacts.

### Follow-up B: user-facing CLI integration

Purpose: connect #226's `pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR` command to the profile contract.

Suggested scope:

1. Add or update the user-facing CLI module and console script.
2. Resolve CLI arguments and optional config override into the existing pipeline config schema.
3. Ensure `--output-dir` is the exact public output directory, not a parent directory for an implicit run-id subdirectory.
4. Run the existing config-driven execution core.
5. Call the profile materializer from follow-up A.
6. Add lightweight CLI/config-resolution tests.

Out of scope for this follow-up:

- changing the profile contract;
- adding new detector/OCR/MMR flags;
- documenting config-first `src/pipeline/main.py` as the user-facing command.

### Follow-up C: #228 final overlay

Purpose: implement the final visual deliverable under `final/`.

Required alignment with #227:

- write final deliverables into `final/`;
- do not reuse review overlays as final outputs unless #228 explicitly defines and accepts that format;
- update `run_summary.json` with final overlay renderer status and artifact paths.

### Follow-up D: #229 manual correction workflow

Purpose: consume `review/manual_correction_input.json` and write corrections to `review/corrections/measure_overrides.json`.

Required alignment with #227:

- use `review/manual_correction_input.json` as the primary handoff;
- preserve source/review overlay coordinate-space assumptions;
- do not overwrite user-edited correction output without explicit user action;
- record correction input and correction timestamp in `run_summary.json` when a corrected final output is generated.

## Review checklist for implementation PRs

A PR implementing this contract should answer these questions before merge:

- Does `final` create only final user-facing deliverables?
- Does `final` exclude logs, raw detector artifacts, MMR crops, OCR traces, masks, and current internal trees?
- Does `review` include enough curated artifacts for human inspection and correction?
- Does `review/manual_correction_input.json` reference all files needed by #229?
- Does the implementation preserve existing `review/corrections/measure_overrides.json` by default?
- Does `debug` retain or index the artifacts needed to reproduce failures?
- Is `--debug` recorded as an effective debug profile without polluting `final/`?
- Does `--output-dir` remain the exact public run directory?
- Are `run_summary.json` and `resolved_config.yaml` written for every profile?
- Are issue-specific logs, Stage E outputs, and experiment zips kept out of normal user output?

## Suggested local checks for a materializer PR

A materializer PR should be testable without running the full OCR/detector stack. Suggested tests:

```bash
PYTHONPATH=. python3 -m pytest tests/test_output_profiles.py
PYTHONPATH=. python3 -m py_compile <materializer_module>.py
uvx ruff check <materializer_module>.py tests/test_output_profiles.py
uvx ruff format --check <materializer_module>.py tests/test_output_profiles.py
```

A CLI integration PR should additionally test argument parsing/config resolution and one dry-run or minimal fixture-backed pipeline invocation, if available.
