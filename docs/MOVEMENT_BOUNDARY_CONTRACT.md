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
Candidate absence does not establish `no_boundary`; only an explicitly
reviewed/rejected record may use that state (apart from the initial-input-system
bookkeeping record). If no boundary is resolved, numbering continues; an
operator can review evidence and add the same zero-based page/system location
deterministically. No current
automatic producer is approved as the production default. The geometry
producer below is approved only for candidate/review use and is not wired into
default pipeline routing.

## Candidate and evidence artifact

A producer that proposes movement starts should write a separate
`issue333.movement_boundary_evidence.v1` artifact. This is a review/provenance
contract, not a numbering input. Its top-level shape is:

```json
{
  "schema_version": "issue333.movement_boundary_evidence.v1",
  "source_document": {
    "sha256": "...",
    "page_order": "ordered_pipeline_input",
    "input_manifest": "runs/example/manifest.json",
    "input_manifest_sha256": "..."
  },
  "input_artifacts": {
    "numbering_base": {
      "path": "runs/example/intermediate/numbering_base.json",
      "sha256": "..."
    }
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
      "references": {
        "page_id": "page_004",
        "source_page": 3,
        "image": "runs/example/inputs/images/page_004.png"
      },
      "provenance": {"review": null}
    }
  ]
}
```

`page` and `system` use the same zero-based ordered-input coordinates as the
resolved contract. They must be derived from the actual input manifest;
`source_page` is separate provenance and is not a consumer coordinate when
pages were selected, omitted, or reordered. A verified direct-PDF render may
retain an explicit physical source-page mapping even for a selected subset;
external, pre-rendered, or reordered inputs omit it unless an independent
verified mapping exists. `state` is one of:

- `confirmed_automatic` — a validated policy may export a resolved boundary;
- `explicit_manual_configured` — an operator/config supplied the resolution;
- `ambiguous_review_required` — candidate only; never reset silently;
- `no_boundary` — reviewed/rejected evidence retained to prevent re-proposal.

Signals retain raw observations and their source artifact. The evidence also
binds the complete geometry input through
`input_artifacts.numbering_base.path` + `sha256`, so the candidate locations
remain auditable even if the original file is later overwritten or the evidence
artifact is moved. This top-level geometry identity is retained even when no
layout candidate is emitted. Numeric confidence is optional and must not be
emitted without calibration evidence. A producer must retain its parameters
and source/runtime provenance; thresholds or unreviewed evidence are not hidden
in the resolved consumer payload.

After review, export a new `issue268.movement_boundaries.v1` payload containing
only resolved records. Use `source` such as `manual`, `configured`,
`reviewed_candidate`, or a specific validated automatic producer, and retain
the evidence artifact identity in `provenance`.

## Geometry review producer

`src.pipeline.movement_boundary_candidates.build_movement_boundary_evidence`
and `tools/generate_movement_boundary_candidates.py` implement the validated
review-only producer (version 2). The explainable candidate rule uses the
reconstructed union across all staff bboxes: it begins at least 2% of page
width to the right of the page median, or its preceding gap is at least 1.75
times the page median gap. First-staff-only geometry was rejected after the
multi-staff audit because it creates false whitespace/indent signals. The
first non-empty input system is retained as `no_boundary` because an initial
reset is unnecessary. Other matched locations are always
`ambiguous_review_required`; the producer never emits numeric confidence or a
resolved reset.

From the repository root:

```bash
python -m tools.generate_movement_boundary_candidates \
  --numbering-base runs/example/intermediate/numbering_base.json \
  --manifest runs/example/manifest.json \
  --source-pdf-sha256 <sha256> \
  --producer-source-commit <commit> \
  --output runs/example/movement_boundary_evidence.json
```

The manifest and numbering artifact must have the same ordered page count.
The CLI hashes the exact `numbering_base.json` bytes and records that SHA-256
beside the artifact path at the top level of the evidence. Raw normalized layout
values, matched rules, image references, source hash, manifest hash, numbering
artifact hash, parameters, and producer commit are retained for GUI or manual
review. Export to `issue268.movement_boundaries.v1` remains a separate explicit
review/configuration action.

The representative Issue #333 fixture is
`tests/fixtures/movement_boundaries/issue333_representative.json`; the complete
seven-source inventory and full-document ground truth are retained under
`experiments/issue333/phase25_ground_truth.json`. Both fix source-PDF hashes
and exact zero-based page/system locations without retaining copyrighted PDF or
image bytes.

`source_page` is emitted only when the manifest contains a verified direct-PDF
render reference with source digest and physical page. A selected direct-PDF
render can therefore retain explicit physical mappings. External, pre-rendered,
or reordered image inputs retain ordered `page` and `page_id` but omit
`source_page` unless an independent verified mapping exists; a `page_NNN` stem
is never interpreted as a physical PDF page. The core evidence API applies the
same rule: a direct-PDF reference must have a valid nonnegative `source_page`,
a valid source-document SHA-256, and a digest matching top-level
`source_document.sha256`; contradictory verified references fail fast.

The producer is assistive only: Phase 2.5 all-staff-union replay found 14/16
transitions and one false candidate. Its 15/917 candidate rate is generation
burden, not total correctness review burden. Candidate absence never means
`no_boundary`.
