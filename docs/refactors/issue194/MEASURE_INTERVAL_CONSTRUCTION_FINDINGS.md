# Issue #194 Measure interval construction findings

This document records durable findings from the Issue #194 local inspection and experiments. Generated overlays, raw JSON summaries, and run artifacts remain local under `logs/` and must not be committed.

## Scope

Issue #194 investigates upstream measure interval construction failures observed after #94. It stays separate from MMR OCR/CNN tuning and full-pipeline detector contract validation.

## Case decisions

| page_id | source page | classification | decision |
|---|---|---|---|
| `page_021` | `Shostakovich-Sym5-Va_page_013` | divisi merge miss | follow-up |
| `page_022` | `Shostakovich-Sym5-Va_page_014` | divisi merge miss | follow-up |
| `page_045` | `Va_Prokofiev_Symphony1_page_004` | system false merge | follow-up |
| `page_053` | `Va__Prokofiev_Symphony5_page_007` | first non-measure region treated as measure | fix in #194 |
| `page_060` | `Va__Prokofiev_Symphony5_page_015` | over-split by barline false positive | follow-up |

## Accepted #194 fix

`page_053` has an indented first system where the clef/key-signature region is converted into a narrow first measure.

Observed failing-system values:

- first interval width: `179.0`
- median interval width: `415.0`
- staff height: `167.0`
- width / median: `0.43`
- width / staff height: `1.07`

Accepted implementation rule:

```text
i == 0
left_bar.is_ghost is True
interval_width < 0.5 * median_interval_width
interval_width < 1.2 * avg_staff_height
```

Use `and`, not `or`. Do not use an absolute pixel threshold. Apply only to the first interval created from an implicit ghost start.

## Deferred cases

`page_060` should not be handled by a geometry-only numbering rule. The x=580 candidate has barline-like geometry and high CNN confidence, so it requires a detector/GT audit follow-up.

`page_021`, `page_022`, and `page_045` should not be handled by a simple distance threshold. The false split and false merge cases require a layout/grouping redesign follow-up using bracket/brace or other system-start connector evidence.

## GT fixture cleanup

The inspection confirmed missing expected overrides for:

- `page_035`: `{ "page": 34, "system": 9, "measure": 4, "skip": 1 }`
- `page_037`: `{ "page": 36, "system": 11, "measure": 3, "skip": 5 }`

`page_033` remains an unexpected detection and should not be added to expected overrides.

## Commit hygiene

Only source changes, tests, small reusable tools, and durable docs belong in Git. Do not commit generated overlays, raw logs, or full run artifacts.
