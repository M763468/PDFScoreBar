# User correction acceptance (#397)

The user review application consumes a retained review package, records corrections,
and applies them through the authoritative review engine. It does not edit canonical
GT or select arbitrary input/output paths from browser requests.

Run the repeatable real-artifact gates in a fresh directory:

```bash
python -m tools.review_correction.acceptance \
  --source-run /absolute/retained/single-page/run \
  --movement-review /absolute/retained/movement/package \
  --evidence-root logs/issue397/acceptance/<run> \
  --runtime-identity <immutable-image-id>
```

The currently fixed cases use the Issue #354 production page and Issue #346
Shostakovich movement evidence. The runner freezes paths, original artifact hashes,
model identity, runtime, corrections and expected effects before starting HTTP
requests. Only copied manifests receive path adaptations; geometry, tolerances and
model thresholds are preserved. The movement gate deliberately selects page_008
while preserving its persisted page index 6. The historical multi-page run does not
contain the metadata needed for a continuous numbering regression baseline.

Set `PDFSCOREBAR_SOURCE_COMMIT` to the candidate commit when executing in a container
without Git metadata. Mount only the retained runs and model directories required
by the manifests, read-only, plus the isolated candidate worktree for output. Do not
mount the main workspace or its Git metadata. `--prepare-only` freezes and copies
inputs without applying corrections; it is not a passing acceptance result.

Gates cover MMR numbering (second measure 2 → 3, next row 6 → 7), deletion of the
fixed internal barline (78 → 77 physical measures, later row 84 → 83), reviewed
movement reset (24 → 1), unresolved movement (24 preserved), correction removal,
stale result identity, later failed apply, and GT route isolation. Final PDF gates
check the frozen row-start number and compare its embedded raster with the rendered
corrected numbering, retaining a PDF preview. Application status must be current
for the exact correction identity, while package status may remain mixed.

Keep every failed/blocked report. Corrected harness rescoring should reuse valid
retained outputs where possible. Full detector-quality evaluation is outside these
integration gates because detector algorithms, models and thresholds do not change.
Browser workflow and local focused tests complement these API and artifact gates.
