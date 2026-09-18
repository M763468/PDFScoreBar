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

## Resolution policy

The resolved payload above remains deliberately separate from detection
evidence. Production numbering may consume a boundary only when it is either:

- explicit/manual/configured; or
- confirmed automatic under a separately validated producer policy.

An ambiguous candidate must not be copied into `inputs.movement_boundaries`.
Omitting it means numbering continues; an operator can review the evidence and
then add the same zero-based page/system location deterministically. No current
automatic producer is approved as the production default.

## Candidate and evidence artifact

A producer that proposes movement starts should write a separate
`issue333.movement_boundary_evidence.v1` artifact. This is a review/provenance
contract, not a numbering input. Its top-level shape is:

```json
{
  "schema_version": "issue333.movement_boundary_evidence.v1",
  "source_document": {
    "sha256": "...",
    "page_order": "source_pdf"
  },
  "producer": {
    "name": "...",
    "version": "...",
    "source_commit": "...",
    "parameters": {}
  },
  "candidates": [
    {
      "page": 3,
      "system": 8,
      "state": "ambiguous_review_required",
      "signals": [
        {
          "kind": "heading_ocr",
          "artifact": "heading_ocr.json",
          "raw": {"text": "IV", "box": [[0, 0], [1, 1]]}
        },
        {
          "kind": "system_layout",
          "artifact": "numbering_base.json",
          "raw": {"preceding_gap_px": 200, "left_x_px": 525}
        }
      ],
      "provenance": {"review": null}
    }
  ]
}
```

`page` and `system` use the same zero-based ordered-input coordinates as the
resolved contract. `state` is one of:

- `confirmed_automatic` — a validated policy may export a resolved boundary;
- `explicit_manual_configured` — an operator/config supplied the resolution;
- `ambiguous_review_required` — candidate only; never reset silently;
- `no_boundary` — reviewed/rejected evidence retained to prevent re-proposal.

Signals retain raw observations and their source artifact. Numeric confidence
is optional and must not be emitted without calibration evidence. A producer
must retain its parameters and source/runtime provenance; thresholds or
unreviewed evidence are not hidden in the resolved consumer payload.

After review, export a new `issue268.movement_boundaries.v1` payload containing
only resolved records. Use `source` such as `manual`, `configured`,
`reviewed_candidate`, or a specific validated automatic producer, and retain
the evidence artifact identity in `provenance`.

The representative Issue #333 fixture is
`tests/fixtures/movement_boundaries/issue333_representative.json`. It fixes
source-PDF hashes and exact zero-based page/system locations without retaining
copyrighted PDF or image bytes.
