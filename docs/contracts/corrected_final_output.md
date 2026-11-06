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

Checkpoint identities still include the whole handoff. Separating `output_name` from them would need
a new schema and migration, and is not part of this contract.

## Non-goals

This helper does not implement:

- the full `OUTPUT_DIR/{final,review,debug}` public output materializer;
- a public `pdfscorebar run` / `pdfscorebar apply-corrections` CLI;
- GUI launch workflow;
- a real-artifact GUI retry workflow;
- detector / OCR / MMR accuracy changes;
- barline or measure override algorithm changes.
