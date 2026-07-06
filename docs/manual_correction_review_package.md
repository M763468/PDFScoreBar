# Manual Correction Review Package Output

This document describes the config-first production connection that emits a
manual correction review package from `run_pipeline()`.

This is not the full #226/#227 user-facing `OUTPUT_DIR/{final,review,debug}`
profile materializer. The public output profile contract is still defined in
`docs/refactors/issue227/ISSUE227_OUTPUT_PROFILES.md` and remains a later
integration surface. This connection only lets the current pipeline run emit
the #229 manual-correction handoff from the current internal run layout.

## Config

Enable review package output explicitly:

```yaml
outputs:
  review:
    manual_correction_package: true
    # optional; relative paths are resolved from the internal run_dir
    root: review
```

When `manual_correction_package` is missing or false, the pipeline does not
create a review package.

## Output Location

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
- absolute paths are allowed for controlled callers that already own a public
  review directory;
- the materializer still reads only artifacts from the current `run_dir` and
  rejects run artifacts resolved outside that root.

The current internal pipeline layout keeps implementation artifacts in
`<run_dir>/outputs/<page_id>/` and `<run_dir>/intermediate/<page_id>/`.
The review package is a curated handoff copied from those artifacts, not a
replacement for the internal working tree and not the final public profile
contract.

## Source Command Metadata

`outputs.review.source_pipeline_command` is optional. When present, it is copied
into `manual_correction_input.json` as trace metadata. The current config-first
entrypoint does not reconstruct the shell command automatically; a future
user-facing CLI can pass execution context when it owns argument resolution.

## Non-goals

This connection does not implement:

- corrected rerun;
- applying canonical manual overrides back into the pipeline;
- corrected final PDF regeneration;
- the full `final/review/debug` public output materializer.
