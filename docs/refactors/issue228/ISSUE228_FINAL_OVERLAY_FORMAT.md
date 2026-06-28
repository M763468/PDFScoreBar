# Issue 228: Final Score-Number Overlay Format

## Status

- Parent epic: #225
- Task issue: #228
- Base branch: `develop`
- Depends on: #226 for the user-facing command surface
- Depends on: #227 for the public `final` / `review` / `debug` output profile contract
- Scope of this document: visual and semantic contract for `final/<output-name>_score_numbered.pdf`

This document records the design outcome for #228. It intentionally does not implement the renderer, PDF assembly, CLI wiring, profile materializer, detector/OCR/MMR behavior, system grouping behavior, or manual correction GUI integration.

## Document lifecycle

This file is an issue-scoped design handoff, not the permanent home for user documentation.

After the final overlay renderer and user-facing materialization are implemented and accepted, the stable parts of this contract should move into formal documentation such as the root `README.md`, a future user guide, or another standing operational document. At that point, this issue-specific file and its `docs/README.md` index entry should be removed.

Permanent repository behavior must not depend on a document whose only discoverable name is tied to a completed issue number.

## Relationship to #226 and #227

#226 defines the formal user-facing command shape:

```bash
pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR
```

#227 defines the public output profile contract. In that contract, the final deliverable is exactly:

```text
OUTPUT_DIR/final/<output-name>_score_numbered.pdf
```

where `<output-name>` defaults to the sanitized input PDF stem unless a later CLI/config option explicitly overrides it.

#228 defines what that final PDF should visually show. It does not change the directory contract from #227.

## Decision summary

The final score-numbered PDF is a normal-use deliverable. A user should be able to open, keep, print, attach, or pass the PDF to another program without seeing detector, review, or debug information.

The final overlay must therefore be minimal:

1. Display one measure-number label at the left edge of each numbering row.
2. Do not display a number on every measure.
3. Do not display measure-range brackets, barline boxes, staff shading, OCR traces, skip evidence, confidence scores, warnings, or correction UI markers.
4. Use final applied numbering after accepted automatic processing and manual correction.
5. Treat current per-measure / geometry-heavy overlays as review artifacts, not final artifacts.

The purpose of the final overlay is to answer: “What measure number starts this row?” It is not to explain how that number was inferred.

## Terms

### Final applied numbering

Final applied numbering is the numbering after all accepted transformations have been applied:

1. detected or corrected barlines;
2. system grouping;
3. base sequential numbering;
4. accepted MMR skip/span overrides;
5. user-provided manual measure overrides.

When review profile artifacts exist, the final overlay should be derived from the same semantic payload as:

```text
review/score_numbering.json
review/pages/<page_id>/numbering_final.json
```

Those JSON files are review/tooling artifacts, not final deliverables. The final PDF consumes their semantics but must not copy the JSON files into `final/`.

### Numbering row

A numbering row is the final grouped horizontal music row that shares one logical measure progression.

In the current code model this is closest to `page.systems[]` after system grouping. It may contain one staff, a grand staff, an orchestral system, or a divisi group, depending on the score and grouping result.

The renderer should not infer independent row labels from raw staff boxes alone. It should use the same final system grouping that produced final applied numbering.

### Row-start number

The row-start number is the measure number of the first visible or performed measure in that numbering row according to final applied numbering.

The label should be read as:

```text
this row starts at measure N
```

It is not a range label, not a count of visible measures, and not a detector index.

## Displayed number meaning

### Default rule

For each numbering row with at least one final measure, display the first measure's final applied number.

If a row has no final measures, do not display a label for that row. Missing or skipped rows should be surfaced through `review/warnings.json` or debug artifacts, not by placing warning text in the final PDF.

### Page and row boundaries

A new label is displayed at each numbering row, including the first row on each page.

No extra page-level label is added. The page does not need a separate “starts at measure N” header if the first row already has its row-start label.

### Pickup / anacrusis / measure 0

The renderer must display the number supplied by final applied numbering.

If a pickup measure is represented by an explicit `set_number: 0`, the label may display `0`. If the numbering starts at `1`, it displays `1`. The final renderer should not independently decide whether a visible pickup should be renumbered or suppressed.

A later UX issue may add a style/config option for suppressing `0` or labeling pickup measures differently. That is not part of #228.

### Repeats, volta, and rehearsal marks

The final label represents the sequential measure number used by PDFScoreBar's applied numbering model. It does not encode repeat playback order, volta alternatives, rehearsal marks, or score-form analysis unless those semantics have already been expressed as manual corrections in final applied numbering.

## Display granularity and update rules

The final overlay uses row-level granularity.

| Situation | Final display |
| --- | --- |
| A row contains ordinary measures 1-4 | Display `1` at the row's left edge only. Do not display `2`, `3`, or `4` in final. |
| The next row starts with measure 5 | Display `5` at that row's left edge. |
| A page starts at measure 17 | Display `17` at the first row's left edge. No separate page header. |
| A row begins with an MMR span whose first logical measure is 41 | Display `41`. Do not display the span length in final. |
| A manual correction changes the first measure of the row to 32 | Display `32`. Do not mark it as corrected in final. |

The row label is updated only at row boundaries. It is not repeated per staff within the same row and is not repeated for every visible measure.

## Placement and anchor rules

### Primary anchor

For each numbering row, compute a row anchor from the final grouped row geometry:

- `row_music_x1`: the left edge of the grouped music row, normally the minimum left edge of the staves participating in the row;
- `top_staff_bbox`: the topmost staff in the grouped row;
- `row_bbox`: the union of staves and, when available, normalized measure geometry for the row.

Place the label in the left gutter of the row:

```text
[label]  | first staff/system content ...
```

The preferred layout is:

- text right edge slightly left of `row_music_x1`;
- vertical position aligned with the top staff of the row, preferably centered against the top staff's vertical extent;
- a small padding gap between the label and the music content;
- no overlap with staff lines, clefs, notes, barlines, brackets, braces, or existing printed text when avoidable.

The exact padding and font metrics are implementation details, but they should be scale-aware rather than fixed to one DPI.

The illustrative mock created during #228 intentionally demonstrates the row-level labeling concept, not exact pixel spacing. In that mock, the labels sit farther away from the music rows than is likely desirable for final implementation. A renderer should tune the horizontal offset against actual page geometry so labels remain visually associated with their target row while still avoiding collisions.

### Style

Default final label style:

- plain Arabic integer, e.g. `17`;
- neutral text color suitable for print and screen use;
- no review colors such as red/green/magenta detector markers;
- no measure boxes, staff shading, or range ticks;
- optional light background/halo is allowed only to preserve readability and must remain visually unobtrusive.

The label should not look like a detector annotation. It should look like a small score annotation.

### Fallback when left margin is insufficient

If the left gutter cannot fit the label without collision, use this fallback order:

1. Place the label above-left of the row, near the first measure start, outside the staff-line area.
2. If above-left placement collides with existing notation, place the label just inside the row start with a small readability halo/background.
3. If no collision-free placement exists, still place the best available minimal label and record the placement issue in review/debug artifacts. Do not place warning text in `final/`.

A future implementation should record fallback placement decisions in review/debug metadata so a reviewer can inspect problematic pages without polluting the final PDF.

## MMR / skip / measure span handling

MMR affects final labels only through final applied numbering.

If accepted MMR evidence says a visible rest spans multiple measures, the numbering increment for later measures and rows must reflect that span. The final label still displays only the row-start measure number.

Example:

```text
Row A starts at measure 41 and contains an 8-measure rest span.
Row B starts at measure 49.
```

Final display:

```text
41  [Row A music]
49  [Row B music]
```

The final display does not show:

- `41-48` range labels;
- `MMR=8`;
- OCR text;
- classifier confidence;
- crop images;
- skip evidence markers.

Those belong in `review/pages/<page_id>/mmr_overrides.json` or `debug/<debug-run-id>/mmr/<page_id>/` according to the #227 output profile contract.

If MMR is rejected, disabled, unavailable, or overridden by a manual correction, the final overlay follows the resulting final applied numbering. The renderer must not read raw OCR or detector traces independently to change labels.

## Manual correction handling

Manual corrections are applied before final rendering.

If `review/corrections/measure_overrides.json` or a later equivalent correction input is supplied to the pipeline, the final PDF must reflect the corrected numbering.

The final PDF must not display correction provenance:

- no “corrected” markers;
- no before/after numbers;
- no override comments;
- no GUI handles;
- no warning badges.

Before/after comparison, editable correction UI state, and override comments belong to `review/` or `debug/`, not `final/`.

Manual correction precedence is semantic, not visual: when user corrections and MMR both affect a measure, the final applied numbering resolver decides the final number, and the final renderer displays that result.

## Divisi and system grouping handling

The final overlay should avoid duplicate labels for staves that share the same measure progression.

Rules:

1. A grouped system row receives one label.
2. A grand staff receives one label, not one label per staff.
3. A divisi group that shares the same measure progression receives one label for the grouped row, not duplicate labels for each divisi staff.
4. Separate independent numbering rows on the same page each receive their own label.
5. System grouping evidence, connector evidence, bracket/brace inference, and grouping uncertainty are not drawn in final.

The anchor should be computed from the grouped row geometry, not from each individual staff. For a divisi or multi-staff group, place the label at the left edge of the group in a way that visually identifies the whole row.

If grouping is incorrect, the fix belongs in system grouping or manual correction workflow. The final renderer should not independently split or merge rows based on low-level detector evidence.

## Current overlay split

The current `tools/add_measure_numbers.py` overlay renderer is review-oriented. It draws or may draw:

- staff-region shading;
- one number per measure centered above the measure;
- measure start/end tick marks;
- detected barline rectangles;
- ghost/detected barline color differences.

The current integrated pipeline writes page-level `numbering_overlay.png` during the final numbering phase. Under the #227/#228 contract, that artifact maps to:

```text
review/pages/<page_id>/review_overlay.png
```

not to:

```text
final/<output-name>_score_numbered.pdf
```

A later implementation should add a distinct final renderer rather than reusing the current review overlay as the final deliverable.

## Final / review / debug boundary

| Artifact or visual element | Target profile | Notes |
| --- | --- | --- |
| Final score-numbered PDF with row-start labels only | `final/<output-name>_score_numbered.pdf` | Only final deliverable. |
| Current per-measure `numbering_overlay.png` | `review/pages/<page_id>/review_overlay.png` | Human inspection and correction. |
| Page-level final visual preview image, if generated | `review/pages/<page_id>/final_page.png` | Review aid only; not the final deliverable. |
| Final applied numbering JSON | `review/score_numbering.json`, `review/pages/<page_id>/numbering_final.json` | Machine-readable review/tooling output. |
| MMR normalized overrides | `review/pages/<page_id>/mmr_overrides.json` | Review evidence. |
| MMR crops, OCR trace, classifier scores, TTA diagnostics | `debug/<debug-run-id>/mmr/<page_id>/` | Developer/debug evidence. |
| System grouping / connector evidence | `review/` subset or `debug/` full trace | Not drawn in final. |
| Warnings and placement fallback notes | `review/warnings.json` and/or debug metadata | Not drawn in final. |

## Mock examples

These examples are intentionally textual. #228 does not require storing generated image artifacts in Git.

### Note on generated mock spacing and implementation tuning

The generated mock image created from a representative score page is illustrative, not normative, with respect to exact spacing, offset, or font scale.

In that mock, the left-side row-start labels are placed farther from the music rows than is likely desirable for final implementation. The accepted design intent is that labels should remain visually associated with the target row while avoiding overlap with notation.

A follow-up renderer should tune placement against actual rendered geometry, including:

- horizontal distance from the grouped row start;
- label size and readability;
- available left margin width;
- collision avoidance against clefs, dynamics, tempo text, divisi text, rehearsal marks, braces, brackets, and other printed symbols;
- fallback placement behavior when the preferred gutter position is too tight.

The mock should be read as a semantic example of row-start numbering, not as the exact final spacing specification.

### Example 1: ordinary two-row page

Final applied numbering:

```text
page 1
  row 1: measures 1, 2, 3, 4
  row 2: measures 5, 6, 7, 8
```

Final visual intent:

```text
1   |================ row 1 music ================|

5   |================ row 2 music ================|
```

Do not show `2`, `3`, `4`, `6`, `7`, or `8` in the final PDF.

### Example 2: page boundary

Final applied numbering:

```text
page 1 row 4 starts at 25
page 2 row 1 starts at 31
```

Final visual intent:

```text
page 2
31  |================ first row on page 2 =========|
```

No extra page-start banner is added.

### Example 3: MMR span

Final applied numbering:

```text
row 1 first measure: 41
row 1 contains an accepted 8-measure rest span
row 2 first measure: 49
```

Final visual intent:

```text
41  |==== multi-measure rest row ==================|
49  |==== next row ================================|
```

The final PDF does not show `41-48`, OCR evidence, or skip diagnostics.

### Example 4: divisi group

Final applied numbering:

```text
row 3 is grouped as one divisi system
  staff A: shared measure progression
  staff B: shared measure progression
  first measure number: 72
```

Final visual intent:

```text
72  |==== divisi staff A ==========================|
    |==== divisi staff B ==========================|
```

Only one `72` label is drawn for the grouped row.

### Example 5: manual correction

Base/automatic numbering would start a row at `90`, but the accepted manual correction sets it to `89`.

Final visual intent:

```text
89  |==== corrected row ===========================|
```

The final PDF does not show both `90` and `89`, and does not mark the label as corrected.

## Implementation handoff

A later final overlay implementation should treat this document as the semantic contract.

Recommended implementation inputs:

- source PDF or high-fidelity rendered page image with coordinate metadata;
- final applied numbering payload, equivalent to `review/score_numbering.json` / `review/pages/<page_id>/numbering_final.json`;
- final grouped row geometry;
- page dimensions and coordinate transform metadata;
- optional style/config defaults for label size and padding;
- optional review/debug sink for placement fallback decisions.

The renderer should treat mock/example visuals as conceptual only and must perform final placement tuning against real page geometry. In particular, row-start labels should usually be placed closer to the target row than in the illustrative mock, provided that readability and collision avoidance are preserved.

Recommended internal label model:

```yaml
final_overlay_rows:
  - page_id: <page_id>
    page_number: <1-based page number>
    row_id: <stable row id or row index>
    row_bbox: [x1, y1, x2, y2]
    top_staff_bbox: [x1, y1, x2, y2]
    row_start_measure_number: <integer>
    source_measure_index: <0-based index in row>
    placement: primary_left_gutter | above_left_fallback | inside_left_fallback
```

The implementation may render directly into PDF or render page-level previews before assembling the PDF, but only the assembled PDF belongs in `final/`. Any intermediate page images belong in `review/` or `debug/` according to #227.

### Implementation non-goals

A final overlay implementation PR should not:

- change detector, OCR, MMR, or system grouping algorithms;
- change manual correction semantics;
- change the `final` / `review` / `debug` directory contract;
- make current per-measure review overlays the final deliverable;
- add broad CLI or package restructuring unless explicitly scoped by another issue.

### Suggested validation for a future implementation PR

The renderer should be testable with small fixture numbering payloads and synthetic page geometry. It should not need to run the full detector/OCR/MMR stack for unit tests.

Suggested checks for the future implementation:

```bash
PYTHONPATH=. python3 -m pytest tests/test_final_overlay_format.py
PYTHONPATH=. python3 -m py_compile <final_overlay_renderer_module>.py
uvx ruff check <final_overlay_renderer_module>.py tests/test_final_overlay_format.py
uvx ruff format --check <final_overlay_renderer_module>.py tests/test_final_overlay_format.py
```

Full visual review may additionally use representative score pages, but those generated artifacts should remain outside Git unless a later issue defines a narrow fixture retention rule.

## Non-goals for #228

#228 does not:

- implement final PDF rendering;
- assemble PDFs;
- implement or change `pdfscorebar run`;
- implement profile materialization;
- change detector/OCR/MMR/system grouping accuracy behavior;
- integrate the manual correction GUI;
- change output directory contracts already defined by #227;
- delete or migrate historical experiment artifacts;
- promote `develop` to `main`.

## Acceptance mapping

| #228 acceptance | Design outcome |
| --- | --- |
| final overlay の表示仕様が文書化されている | Decision summary, displayed-number meaning, granularity, placement, style, and mock examples. |
| 現行 overlay のうち final に残すもの、review/debug に移すものが明確になっている | Current overlay split and final/review/debug boundary tables. |
| 各段左端に付ける番号の意味と算出元が説明されている | Final applied numbering, numbering row, row-start number, and update rules. |
| MMR / manual correction が反映された場合の扱いが定義されている | MMR / skip / measure span handling and manual correction handling sections. |
| 後続の描画実装 issue に渡せる仕様になっている | Implementation handoff, recommended label model, implementation non-goals, and suggested validation. |
