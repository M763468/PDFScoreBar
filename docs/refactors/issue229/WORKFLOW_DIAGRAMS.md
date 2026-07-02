# Issue 229: Manual Correction Workflow Diagrams

## Status

- Parent epic: #225
- Task issue: #229
- Related design document: `ISSUE229_MANUAL_CORRECTION_WORKFLOW.md`
- Scope of this document: visual summaries of the review-package-to-GUI boundary and corrected-final regeneration workflow.

These diagrams are explanatory. They do not add implementation requirements beyond `ISSUE229_MANUAL_CORRECTION_WORKFLOW.md` and `MANUAL_CORRECTION_WORKFLOW_SPEC.yaml`.

## 1. End-to-end user workflow

```mermaid
flowchart TD
  A[User runs review profile<br/>pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR --profile review]
  B[Pipeline internal run_dir<br/>inputs / intermediate / outputs]
  C[Profile materializer]
  D[OUTPUT_DIR/review package<br/>manual_correction_input.json<br/>pages/* artifacts]
  E[Manual correction GUI<br/>or transitional adapter + current GUI]
  F[review/corrections staging files<br/>mmr_measure_spans.json<br/>barline_construction_overrides.json<br/>measure_construction_overrides.json]
  G[Correction canonicalizer]
  H[Canonical correction inputs<br/>measure_overrides.json<br/>barline_overrides.json]
  I[Corrected pipeline/rerun step]
  J[Corrected final applied numbering<br/>review/score_numbering.json<br/>review/pages/*/numbering_final.json]
  K[#228 final renderer]
  L[final/&lt;output-name&gt;_score_numbered.pdf<br/>row-start labels only]

  A --> B
  B --> C
  C --> D
  D --> E
  E --> F
  F --> G
  G --> H
  H --> I
  I --> J
  J --> K
  K --> L
```

Key point: the GUI does not search arbitrary `logs/` directories. It starts from a review package produced for one score/run/coordinate space.

## 2. Artifact boundary: current internal output to review package

```mermaid
flowchart LR
  subgraph Internal[Current implementation-oriented run_dir]
    I1[inputs/images]
    I2[intermediate/&lt;page_id&gt;/overrides_mmr.json]
    I3[intermediate/&lt;page_id&gt;/barlines_corrected.json<br/>or resolved raw barlines]
    I4[outputs/&lt;page_id&gt;/numbering_final.json]
    I5[outputs/&lt;page_id&gt;/numbering_overlay.png]
    I6[outputs/numbering_final.json]
    I7[manifest.json / filters.json / pipeline.log]
  end

  M[Profile materializer<br/>normalizes, copies/references,<br/>adds metadata]

  subgraph Review[OUTPUT_DIR/review]
    R1[pages/&lt;page_id&gt;/source.png]
    R2[pages/&lt;page_id&gt;/mmr_overrides.json]
    R3[pages/&lt;page_id&gt;/barlines_review.json]
    R4[pages/&lt;page_id&gt;/numbering_final.json]
    R5[pages/&lt;page_id&gt;/review_overlay.png]
    R6[score_numbering.json]
    R7[run_summary.json / warnings.json]
    R8[manual_correction_input.json]
  end

  I1 --> M --> R1
  I2 --> M --> R2
  I3 --> M --> R3
  I4 --> M --> R4
  I5 --> M --> R5
  I6 --> M --> R6
  I7 --> M --> R7
  R1 --> R8
  R2 --> R8
  R3 --> R8
  R4 --> R8
  R5 --> R8
  R6 --> R8
```

Key point: `manual_correction_input.json` is a curated handoff, not a raw dump of the internal run directory.

## 3. Same-coordinate-space requirement

```mermaid
flowchart TD
  P[One page entry in<br/>review/manual_correction_input.json]
  S[source.png<br/>rendered page image]
  N[numbering_final.json<br/>measure boxes]
  M[mmr_overrides.json<br/>MMR span evidence]
  B[barlines_review.json<br/>barline geometry]
  O[review_overlay.png<br/>visual inspection layer]
  C[coordinate_space metadata<br/>origin=top_left, units=pixels,<br/>image size / dpi when available]
  G[GUI editable view]

  P --> S
  P --> N
  P --> M
  P --> B
  P --> O
  P --> C
  S --> G
  N --> G
  M --> G
  B --> G
  O --> G
  C --> G

  X[Reject normal workflow if artifacts come from<br/>different score / different run / different page / different image scale]
  P -. validation .-> X
```

Key point: the first #215 attempt failed this boundary because image, numbering, MMR, and barline artifacts came from mismatched roots.

## 4. Correction output levels

```mermaid
flowchart TD
  subgraph GUI[GUI save output under review/corrections]
    A[mmr_measure_spans.json<br/>set_measure_span / suppress]
    B[measure_construction_overrides.json<br/>force_measure]
    C[barline_construction_overrides.json<br/>add_barline / remove_barline]
  end

  D[Correction canonicalizer]

  subgraph Canonical[Canonical pipeline correction inputs]
    E[measure_overrides.json<br/>consumed during final numbering]
    F[barline_overrides.json<br/>consumed before base measure construction]
  end

  A --> D
  B --> D
  C --> D
  D --> E
  D --> F
```

Key point: GUI staging files mirror the current #201 GUI/helper categories. The pipeline rerun should consume canonical correction inputs.

## 5. Corrected final regeneration order

```mermaid
sequenceDiagram
  participant U as User
  participant G as Manual GUI
  participant C as review/corrections
  participant P as Pipeline correction step
  participant R as Review outputs
  participant F as Final renderer

  U->>G: Stage MMR / barline / measure corrections
  G->>C: Save staging JSON
  C->>P: Canonicalize to measure_overrides.json and barline_overrides.json
  P->>P: Apply barline_overrides before base measure construction
  P->>P: Apply measure_overrides before final applied numbering
  P->>R: Write corrected score_numbering.json and page numbering_final.json
  R->>F: Provide corrected final applied numbering
  F->>U: Write final/&lt;output-name&gt;_score_numbered.pdf
```

Key point: final rendering happens after corrections are applied semantically. The final PDF does not display correction provenance.

## 6. #215 retry gate

```mermaid
flowchart TD
  A[Review package exists]
  B{Same score / run / page / coordinate space?}
  C{manual_correction_input.json or adapter config present?}
  D{GUI save targets under review/corrections?}
  E{MMR base/effective rows load?}
  F{Can save MMR correction?}
  G{Can save barline correction?}
  H{Saved JSON can reach helper/pipeline input?}
  I[Proceed with #215 real-artifact smoke retry]
  Z[Do not proceed;<br/>fix package/materializer/adapter first]

  A --> B
  B -- yes --> C
  B -- no --> Z
  C -- yes --> D
  C -- no --> Z
  D -- yes --> E
  D -- no --> Z
  E -- yes --> F
  E -- no --> Z
  F -- yes --> G
  F -- no --> Z
  G -- yes --> H
  G -- no --> Z
  H -- yes --> I
  H -- no --> Z
```

Key point: #229 does not replace #215. It defines the prerequisites for a meaningful #215 retry.
