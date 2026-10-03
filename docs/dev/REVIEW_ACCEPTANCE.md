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


### Browser workflow

With an installed Playwright module and Chromium, open a fresh writable copied package using
`tools.review_correction.server`, then run:

```bash
PLAYWRIGHT_MODULE=/path/to/playwright CHROMIUM_PATH=/path/to/chromium \
  node tools/review_correction/browser_acceptance.cjs \
  http://127.0.0.1:8010 logs/issue397/acceptance/<run>/browser
```

The script selects the retained first measure and uses actual form controls to save, apply,
retrieve the PDF, and remove the correction. It checks pending/recorded/current/stale transitions
and retains screenshots, state snapshots and the downloaded PDF. Use a fresh copied package
whose original first-measure span is one.

### Validation evidence (2026-10-03)

The GPU run at `logs/issue397/acceptance/gpu01` passed all fixed gates with candidate
`36964070dcdec8dc03f26c234c2ba36343f28a1e`, image
`sha256:3eaccf844d6d18b6212e8aed4551bc0fb4a424fc776568058d465f8335aef3ab`, and model SHA256
`f163fa2a7679d12c0f4fe6fc2fadc7ed1f144035779a18b83a303bfa6d35903a`.
The browser workflow passed in `gpu01/browser02`. Supplemental isolation and final-cleanliness
checks are in `gpu01/isolation-and-provenance.json`. Focused tests passed (44), existing UI/payload/index regression tests passed (46),
and fast tests passed (110). Final-cleanliness and PDF-content checks were also rescored
from retained outputs with the final harness, without rerunning inference. Source manifests do not record their historical generating commits; the frozen plan
records this limitation and hashes the retained inputs. These retained inputs establish correction
integration behavior, not a fresh production detector-quality comparison.

The first browser attempt applied successfully but its harness used a relative PDF URL with
Playwright's unconfigured request client. Its log and outputs remain retained; `browser02`
corrects that harness error. No production thresholds or acceptance expectations were changed.


### Review responsibility correction (2026-10-03)

Failed-apply error counting is owned and tested by #394. Retention of the consumed reviewed
movement payload in corrected config is owned and tested by #395. These fixes have been moved
into their dependency PRs; #397 contains acceptance tooling, evidence documentation and the
localization handoff. All correction recording now uses the #394 common recording operation;
explicit Save versus movement confirmation remains only a UI trigger distinction.

After restacking, the state/server/application/movement/UI/final/preparation suites passed
(51 tests), with `make lint`, repository-surface checks and fast tests (110) passing. The actual
apply engine, movement helper and application adapter are unchanged from the retained GPU
candidate. Its numbering/PDF results remain valid evidence; no expensive inference was repeated
solely for moving commits between PRs. The updated pending/recorded axes and failure/retry
transitions are covered by focused tests for all four correction types.
