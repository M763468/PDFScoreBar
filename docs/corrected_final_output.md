# Corrected Final Output Helper

[日本語](corrected_final_output.ja.md)

This internal helper reference is for developers and maintainers. It describes the narrow
connection from the manual-correction `apply_corrections` rerun path to a clean final PDF
artifact for the corrected run. For the supported user-facing distribution workflow, see the
[User Guide](USER_GUIDE.md).

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

## Non-goals

This helper does not implement:

- the full `OUTPUT_DIR/{final,review,debug}` public output materializer;
- a public `pdfscorebar run` / `pdfscorebar apply-corrections` CLI;
- GUI launch workflow;
- a real-artifact GUI retry workflow;
- detector / OCR / MMR accuracy changes;
- barline or measure override algorithm changes.
