# Issue #274 first-pass causality — concise checkpoint

See `README_first_pass_causality.md` for the full interpretation. This companion
file exists only to keep the experiment branch history explicit after the crop
renderer report-writer fix.

- p013 / Sibelius: current-x4-supported A seeds alter PDFScoreBar dense context in
  two ways: row context and existing-box suppression. Suppression removal restores
  matching capacity, but not necessarily the physically correct second identity.
- p015: suppression and row-context changes do not restore capacity; the missing A
  hybrid seed is the direct deficit. Prior directional-support analysis can retain
  this A seed from current-x4 evidence.
- Therefore a single support threshold or a single suppression tweak cannot solve
  all focused regressions.
- The architecture under test separates A-derived structural rows, x4 evidence
  support, per-row suppression ownership, and supplemental thin evidence.
- The crop visual gate remains required before generalizing focused GT multiplicity
  into a physical barline identity rule.
