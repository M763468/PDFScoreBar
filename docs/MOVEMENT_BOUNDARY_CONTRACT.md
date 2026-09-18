# Resolved movement-boundary consumer contract

Issue #268 consumes resolved movement boundaries; it does not detect or infer
movements. Detection and resolution remain owned by Issue #333.

## Input

Set `inputs.movement_boundaries` to a JSON path or an inline mapping with this
shape:

```json
{
  "schema_version": "issue268.movement_boundaries.v1",
  "boundaries": [
    {
      "page": 1,
      "system": 2,
      "reset_number": 1,
      "source": "manual",
      "provenance": {"kind": "fixture"}
    }
  ]
}
```

`page` and `system` are zero-based indices in the ordered pipeline input. A
boundary resets the logical number immediately before that system. `page` is
not a page-break signal: an omitted boundary means ordinary page-to-page
continuation. `reset_number`, `source`, and `provenance` are explicit and are
retained in final artifacts. Duplicate page/system locations and out-of-range
pages are rejected.

## Numbering and artifacts

Phase A remains page-local because its absolute measure numbers and
`[page, system, measure]` indices are MMR input. MMR recognition and its
`skip` output are unchanged. Phase C applies the already-merged MMR/manual
overrides while carrying `next_number` from one page to the next. A boundary
reset is applied before `set_number`; an explicit existing `set_number` then
controls the number assigned to that measure.

Each `outputs/<page_id>/numbering_final.json` contains additive
`numbering_metadata` with the page start/next state and boundary records. The
combined `outputs/numbering_final.json` concatenates those page payloads and
retains the same page metadata and resolved boundary provenance; it does not
re-number the pages independently. `skip_existing` reuses a page only when
this metadata matches the current incoming state and boundaries. Older
page-local artifacts are rebuilt rather than guessed from their visible
maximum number, which would lose MMR skip state.

The final renderer continues to read the first valid measure number in each
system from final numbering JSON and draws one row-start label. Boundary
provenance and debug data are not rendered into the final PDF.
