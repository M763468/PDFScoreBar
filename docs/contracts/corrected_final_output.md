# Corrected Final Output Helper

[日本語](corrected_final_output.ja.md)

This internal helper reference is for developers and maintainers. It describes the narrow
connection from the manual-correction `apply_corrections` rerun path to a clean final PDF
artifact for the corrected run. For the supported user-facing distribution workflow, see the
[User Guide](../USER_GUIDE.md).

## Entry point

`src.pipeline.review.apply_corrections.apply_corrections_and_rerun()` accepts:

```python
generate_final_pdf = True
output_name = "optional-name"
```

The minimal CLI wrapper also accepts:

```bash
python -m src.pipeline.review.apply_corrections \
  path/to/review/manual_correction_input.json \
  --overwrite \
  --generate-final-pdf \
  --output-name optional-name
```

The flag is opt-in; by default the rerun does not generate a final PDF.

## Output

When enabled after a non-dry corrected rerun, the helper writes:

```text
<corrected_run_dir>/
  final/
    <output-name>_score_numbered.pdf
  review/
    correction_summary.json
    corrected_final_summary.json
```

`final/` is reserved for the clean final PDF artifact. Correction provenance,
row-label metadata, and warnings are written under `review/`.

## Rendering contract

The renderer consumes:

- source page images from the same manual-correction review package coordinate
  space;
- corrected rerun `outputs/<page_id>/numbering_final.json` files.

The final PDF renders one row-start measure number per final numbering row. It
does not render review-only geometry such as staff shading, barline boxes,
measure-range ticks, MMR evidence, correction provenance, or warnings into the
final PDF.

## Output name and saved-attempt compatibility

`output_name` is optional filename metadata. It does not define page correspondence, detection
results, or the meaning of corrections. A job without it is valid: generation applies the existing
naming rules and fallback, and sanitizes any given value before using it in a path.

Each operation checks something different:

| Operation | Requires | Does not require |
| --- | --- | --- |
| Open a review | Readable files and structure | Any saved attempt to verify; an unverifiable one is listed as unavailable |
| Import a pre-checkpoint attempt | Its recorded source and corrections identities reproduce | A matching job `output_name` |
| Resume from a checkpoint | Checkpoint and blob integrity, dependencies, and the PDF correspondence checks in `resume.py` | Checking the original attempt again |

**Import.** These attempts hash the whole handoff file, so their identities are not rewritten and
stay byte-based. When only the job's name differs, `tools/review_correction/legacy.py` rebuilds the
recorded handoff from the attempt's saved copy and accepts it only if the recorded source identity
reproduces. This covers one format: the key order saved by the attempt, and
`prepare_local_review`'s serialization for the job file. Anything else stays unavailable, including:

- changed sources, manifests, or corrections;
- a changed saved attempt, including its saved `output_name`;
- an attempt whose saved name was added only when it was applied, because its recorded handoff
  cannot be told apart from a changed copy.

Importing confirms saved inputs only. It does not show that an earlier PDF generation succeeded.

**Name priority at import:** the attempt's valid saved name, then the job's current valid name, then
the existing naming rules. A valid name is a string that is non-empty after sanitization. Import
never changes the saved attempt, the job handoff, or an existing checkpoint; importing an attempt
again returns its existing checkpoint, even if the job's name has changed since. The checkpoint's
handoff provides the name when a session resumes, because a session has no `final/` to recover from.

## Versioned identity

The review package has two identity rules. `tools/review_correction/state.py` computes both, and a
stored record is always compared under its own rule:

| | Identity v1 | Identity v2 |
| --- | --- | --- |
| Written by | Checkpoint schema 1, older results and pre-checkpoint attempts | Checkpoint schema 2 and new results |
| Marked by | No `identity_version` | `identity_version: 2` |
| Handoff input | SHA-256 of the whole file | Digest of the parsed JSON object without top-level `output_name` |

Everything else is the same under both rules: declared source files, the source manifest, the resume
PDFs, and the corrections. Under v2, handoff content such as page order and the `resume` block still
changes the identity. JSON formatting and key order do not. A handoff that is not a JSON object is
hashed by its exact bytes. `corrections_identity` has one value under both rules.

**No migration.** Schema 1 checkpoints, their blobs, and their `cp_...` IDs are never rewritten, and
they can still be listed, materialized, and resumed. Unknown schema or identity versions, and records
whose version or digests are inconsistent, are rejected. Code from before this change cannot read
schema 2 checkpoints.

**Reuse and status:**

- Saving reuses the newest checkpoint whose identity matches under its own rule, so changing only
  `output_name` does not add a v2 checkpoint or make a v2 result stale.
- A v1 record stores digests only and cannot be converted. It matches only while the handoff bytes
  are unchanged, so after a name change the next save writes one v2 checkpoint, and a v1 result shows
  as stale until the next successful application.
- `current_identity` in the state response is always v2. A matching v1 result keeps its recorded
  digests in `current_result`.

**Integrity is separate.** A checkpoint still retains the complete handoff, including `output_name`,
in a content-addressed blob. The blob hash and the `cp_...` manifest hash cover those bytes, and a
schema 2 checkpoint without the handoff blob is rejected.

**Name after reuse:**

- Generating a corrected result uses the job's current `output_name`, or the existing naming rules
  when it has none, even if a checkpoint with another name was reused.
- Resuming uses the name retained in the selected checkpoint. To resume with a changed name, save a
  new checkpoint explicitly first, because an explicit save never reuses one.

Identity does not replace the operation checks listed under
[Output name and saved-attempt compatibility](#output-name-and-saved-attempt-compatibility).
Pre-checkpoint import keeps reproducing its recorded v1 identities, and resume keeps its PDF, page,
image, and annotation checks.

## Non-goals

This helper does not implement:

- the full `OUTPUT_DIR/{final,review,debug}` public output materializer;
- a public `pdfscorebar run` / `pdfscorebar apply-corrections` CLI;
- GUI launch workflow;
- a real-artifact GUI retry workflow;
- detector / OCR / MMR accuracy changes;
- barline or measure override algorithm changes.
