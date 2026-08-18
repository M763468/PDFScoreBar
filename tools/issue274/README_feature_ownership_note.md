# Feature-ownership note for Issue #274

When reporting Issue #274 results, use `HOMR_FEATURE_OWNERSHIP.md` as the canonical
classification.  In particular:

- preprocessing, SegNet, HOMR symbol/staff/bar-line primitives, and clef/key mask
  generation are upstream HOMR behavior for the selected HOMR revision;
- PDFScoreBar's outer proxy, API compatibility, persistent predictor/artifact
  publication, and semantic-mask handoff are PDFScoreBar orchestration around
  upstream behavior;
- thin-barline recovery/replacement, hybrid consensus, dense probe/suppression,
  candidate filters, the barline CNN, and MMR support mapping are PDFScoreBar
  extensions.

Do not use a generic label such as "HOMR post-processing" for PDFScoreBar's thin,
hybrid, or dense stages.  Conversely, do not describe differences in upstream
`homr.resize`, `homr.color_adjust`, or SegNet generation as PDFScoreBar refactor
behavior merely because they are observed through a PDFScoreBar wrapper.
