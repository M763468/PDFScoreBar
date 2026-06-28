# Issue 227: Implementation Handoff

This file defines what a follow-up implementation PR should and should not do when applying the #227 output profile contract.

#227 itself does not implement the CLI or materializer. It defines the target contract.

## Recommended follow-up split

### Follow-up A: profile materialization layer

Purpose: convert the current internal run layout into the public `final` / `review` / timestamped `debug` directory contract.

Suggested scope:

1. Add a materializer module that accepts an existing internal `run_dir`, a public `OUTPUT_DIR`, and an output name.
2. Default the output name to the sanitized input PDF stem; allow a later CLI/config override to supply another name.
3. Read current known artifacts from `manifest.json`, `filters.json`, `inputs/images`, `intermediate`, and `outputs`.
4. Materialize `final/<output-name>_score_numbered.pdf` only after #228 provides a final PDF artifact. Do not put page PNGs, warnings, summaries, configs, or JSON in `final/`.
5. Materialize `review/run_summary.json`, `review/resolved_config.yaml`, `review/warnings.json`, `review/score_numbering.json`, `review/manual_correction_input.json`, and curated per-page review artifacts.
6. Materialize debug artifacts under `debug/<debug-run-id>/` only for debug profile or effective-debug mode.
7. Make `<debug-run-id>` include a timestamp and include the explicit run id when one is provided.
8. Preserve existing `review/corrections/measure_overrides.json` unless explicit overwrite is requested.
9. Add tests using a fake internal run tree; do not run detector/OCR/MMR in these tests.

Out of scope for this follow-up:

- final overlay visual design;
- PDF assembly, unless the PR is explicitly the #228 implementation;
- GUI launch or edit workflow;
- algorithmic detector/OCR/MMR changes;
- repository cleanup of historical artifacts.

### Follow-up B: user-facing CLI integration

Purpose: connect #226's `pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR` command to the profile contract.

Suggested scope:

1. Add or update the user-facing CLI module and console script.
2. Resolve CLI arguments and optional config override into the existing pipeline config schema.
3. Ensure `--output-dir` is the exact public output directory for `final` and `review`, not a parent directory for an implicit run-id subdirectory.
4. Ensure debug captures go under `debug/<debug-run-id>/` and do not move `final/` or `review/`.
5. Decide whether the user-facing CLI should expose an explicit output-name option; if not, default to the input PDF stem.
6. Run the existing config-driven execution core.
7. Call the profile materializer from follow-up A.
8. Add lightweight CLI/config-resolution tests.

Out of scope for this follow-up:

- changing the profile contract;
- adding new detector/OCR/MMR flags;
- documenting config-first `src/pipeline/main.py` as the user-facing command.

### Follow-up C: #228 final overlay

Purpose: implement the final visual deliverable under `final/`.

Required alignment with #227:

- write exactly the final score-numbered PDF into `final/<output-name>_score_numbered.pdf`;
- do not reuse review overlays or page PNGs as final outputs unless #228 explicitly defines a temporary compatibility mode;
- keep page images and warning information under `review/` or `debug/`, not `final/`.

### Follow-up D: #229 manual correction workflow

Purpose: consume `review/manual_correction_input.json` and write corrections to `review/corrections/measure_overrides.json`.

Required alignment with #227:

- use `review/manual_correction_input.json` as the primary handoff;
- preserve source/review overlay coordinate-space assumptions;
- do not overwrite user-edited correction output without explicit user action;
- record correction input and correction timestamp in `review/run_summary.json` when a corrected final output is generated.

## Review checklist for implementation PRs

A PR implementing this contract should answer these questions before merge:

- Does `final` create only `final/<output-name>_score_numbered.pdf`?
- Does the final PDF name avoid collisions across different input scores by defaulting to the input PDF stem or an explicit output name?
- Does `final` exclude page images, warnings, summaries, configs, JSON, logs, raw detector artifacts, MMR crops, OCR traces, masks, and current internal trees?
- Does `review` include enough curated artifacts for human inspection and correction?
- Does `review/manual_correction_input.json` reference all files needed by #229?
- Does the implementation preserve existing `review/corrections/measure_overrides.json` by default?
- Does `debug` retain or index the artifacts needed to reproduce failures under `debug/<debug-run-id>/`?
- Does `<debug-run-id>` include a timestamp and the explicit run id when provided?
- Is `--debug` recorded as an effective debug profile without adding debug files to `final/`?
- Does `--output-dir` remain the exact public output directory for `final` and `review`?
- Are `review/run_summary.json` and `review/resolved_config.yaml` written for review/debug profiles?
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
