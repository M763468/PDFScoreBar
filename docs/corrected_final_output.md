# Corrected Final Output Helper

This document describes the helper-level corrected final output connection added for
Issue #236.

This is not the full #226/#227 public `pdfscorebar run INPUT.pdf --output-dir
OUTPUT_DIR` output profile materializer. It is a narrow connection from the
manual-correction `apply_corrections` rerun path to a clean final PDF artifact
for the corrected run.

## Entry point

`src.pipeline.review.apply_corrections.apply_corrections_and_rerun()` accepts:

```python
generate_final_pdf=True
output_name="optional-name"
```

The minimal CLI wrapper also accepts:

```bash
python -m src.pipeline.review.apply_corrections \
  path/to/review/manual_correction_input.json \
  --overwrite \
  --generate-final-pdf \
  --output-name optional-name
```

The flag is opt-in so the PR #240 rerun behavior remains backward-compatible by
default.

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

## Non-goals

This helper does not implement:

- the full `OUTPUT_DIR/{final,review,debug}` public output materializer;
- public CLI polish around `pdfscorebar run` / `pdfscorebar apply-corrections`;
- GUI launch workflow;
- #215 real-artifact GUI retry;
- detector / OCR / MMR accuracy changes;
- barline or measure override algorithm changes.
