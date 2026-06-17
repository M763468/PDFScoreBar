# Issue #201 manual correction workflow

This document records the manual-correction boundary introduced for Issue #201.

## Scope

The workflow separates three correction layers:

1. MMR measure-span correction
2. Barline-construction correction
3. Measure-construction correction

It intentionally does not tune MMR OCR/CNN heuristics, redesign #197 grouping behavior, or change the full pipeline architecture.

GUI editing/export is part of #201, but it is handled after this JSON/helper contract is stable.

## Current non-GUI review flow

Until the GUI is added, the review flow is:

1. Run the relevant MMR or construction evaluation and open the page visualization.
2. Decide which layer is wrong.
3. Write a JSON correction item in the matching correction file.
4. Re-run the helper-level regression or the target evaluation.
5. Commit only durable correction files, tests, and docs. Do not commit generated overlays, logs, or temporary review files.

Suggested durable file layout:

```text
data/evaluation2/manual_corrections/
  mmr_measure_spans.json
  barline_construction_overrides.json
  measure_construction_overrides.json
```

The current regression fixtures are synthetic and live under `tests/fixtures/manual_corrections/`.

## MMR measure-span correction

MMR measure-span correction applies only after measures already exist. It may alter measure-numbering override records, but it must not alter barlines, staves, systems, or measure intervals.

`measure_span` means the number of measures represented by a visible multi-measure rest mark. It is not a count of rest glyphs.

Supported operations:

```json
{
  "schema_version": 1,
  "correction_type": "mmr_measure_span",
  "items": [
    {
      "op": "suppress",
      "page": 32,
      "system": 0,
      "measure": 0,
      "reason": "manual rejection of an unexpected MMR detection"
    },
    {
      "op": "set_measure_span",
      "page": 41,
      "system": 8,
      "measure": 0,
      "measure_span": 3,
      "reason": "manual confirmed visible multi-measure rest span"
    }
  ]
}
```

`set_measure_span` is normalized to the existing measure-numbering override shape by storing `skip = measure_span - 1`.

This conversion is valid only when measure construction has already created the target measure correctly. If a measure is missing because a barline was not detected, use barline-construction correction instead.

## Barline-construction correction

Barline-construction correction is for missing or extra detected barlines.

Supported operations:

```json
{
  "schema_version": 1,
  "correction_type": "barline_construction",
  "items": [
    {
      "op": "add_barline",
      "page": 12,
      "bbox": [100, 200, 104, 500],
      "reason": "manual missing barline"
    },
    {
      "op": "remove_barline",
      "page": 12,
      "bbox": [300, 200, 304, 500],
      "reason": "manual extra barline"
    }
  ]
}
```

These items are translated to the existing barline override operations `add` and `remove`.

## Measure-construction correction

Measure-construction correction is for exceptions that affect measure existence or interval-level numbering behavior.

The initial implementation supports only the already-existing `force_measure` behavior:

```json
{
  "schema_version": 1,
  "correction_type": "measure_construction",
  "items": [
    {
      "op": "force_measure",
      "page": 52,
      "system": 0,
      "interval": 0,
      "reason": "manual confirmed that the interval is a real measure"
    }
  ]
}
```

This becomes a `MeasureNumberer` override with:

```json
{
  "page": 52,
  "system": 0,
  "measure": 0,
  "force_measure": true
}
```

The `measure` value is the interval index for `force_measure`, matching the current numbering implementation.

## Future #197 / divisi grouping extension

#197 remains a grouping redesign issue. The current #201 implementation does not manually fix `page_021`, `page_022`, or `page_045`.

However, future divisi and staff grouping corrections may need a manual representation. The schema keeps that separate from MMR measure-span correction. A future operation may look like this:

```json
{
  "schema_version": 1,
  "correction_type": "measure_construction",
  "items": [
    {
      "op": "group_staves_as_system",
      "page": 20,
      "staff_indices": [0, 1],
      "reason": "manual divisi grouping correction"
    }
  ]
}
```

This operation is intentionally ignored by the current helper until grouping correction has a dedicated implementation and regression fixture.

## GUI requirement for this issue

The GUI phase should use the same JSON schema as this document. The intended workflow is:

1. Load a page image and the current detection/evaluation artifact.
2. Let the reviewer choose correction type: MMR span, add/remove barline, force measure, or future grouping.
3. Capture the required fields by click or form input.
4. Export a durable JSON correction file under `data/evaluation2/manual_corrections/`.
5. Re-run the relevant evaluation using the exported correction file.

The first GUI design pass should inspect the existing `tools/gt_relabel_gui` structure and decide whether to extend it or add a sibling manual-correction GUI.

## Lint cleanup boundary

Full-repository lint cleanup is outside #201 unless the warning was introduced by this branch.

If green `make lint` is required before merging #201, fix unrelated existing lint in a separate cleanup PR from `develop`, merge it first, then update #201 and rerun validation.

## Handling criteria

Use MMR measure-span correction when:

- the measure already exists;
- the visible multi-measure rest span is known;
- only numbering skip behavior needs adjustment.

Use barline-construction correction when:

- a measure is missing because a barline was not detected;
- an extra detected barline creates a false interval.

Use measure-construction correction when:

- interval-level behavior is wrong even after barline detection is correct;
- the case is an explicit exception such as `force_measure`.

Use automatic fixes or separate follow-up issues when:

- the behavior can be safely generalized as OCR/CNN heuristic logic;
- detector, GT, or evaluation accounting needs audit;
- the case requires #197-style grouping redesign;
- the correction would require full pipeline redesign.
