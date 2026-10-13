# Issue #415: reviewed GT and semantic numbering audit

The auditor separates recognition quality, recognition-to-application correctness,
reviewed-GT-to-final local increments, page continuity, JSON/PDF consumer agreement,
and independently read row-start samples. Matching an older output is a separate
non-regression result; it does not establish musical correctness.

Run from the checkout root with the retained #409 inputs and #413 corrected outputs:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/issue415/audit_numbering.py \
  --retained-root logs/issue409/full68-numbering-20261009 \
  --final-root logs/issue413/review-refinement/phase-c-replay \
  --verify-pdf \
  --output logs/issue415/implementation/semantic-report.json
```

`--verify-pdf` requires the existing Pillow/PyMuPDF pipeline dependencies, available
in `.venv_pdf` on the audited host or `/opt/venv_pipeline/bin/python` in the maintained
pipeline environment. It reads embedded PDF pixels and compares them with expected
label rendering using the accepted #413 verifier; it does not regenerate saved PDFs.
Without this flag, PDF pixel verification is explicitly marked unperformed.
The basic CLI imports only the standard library. No models, inference, Docker calls,
GPU or upstream rerun are invoked. The retained files are ignored local artifacts,
not shipped in a fresh checkout. Missing files or identity drift fail explicitly.

Exit **0** means all checked correctness gates passed. Exit **1**, with a report,
means recognition/application/GT/continuity or reviewed row-start correctness has
an unresolved discrepancy (or an incoming reset masks an increment). An exception
means the audit itself could not establish valid evidence. The current retained
candidate deliberately returns **1**: its known recognition and semantic errors
must not be converted into a pass by excluding GT events. The auditor has no
"accept known failures" or threshold-retuning switch.

## Reviewed ground truth and provenance

`reviewed_gt.json` contains identity metadata for 68 pages, 177 physical rest
events and all 182 historical fixture mappings. Five divisi entries coalesce only
where their physical location and value agree. The tool checks that mappings and
reviewed event identities agree and that current base bboxes equal reviewed bboxes.
It scores every physical measure, including all ordinary and zero-fixture measures;
it rejects duplicate, missing and invalid override targets. Terminal increments use
that page's `numbering_metadata.next_number`, including at page boundaries and EOF.

The GT values come from image inspection recorded in
[#415's audit comment](https://github.com/M763468/PDFScoreBar/issues/415#issuecomment-6092071490),
not from recognition output. Historical bboxes come from retained #274 rebase
evidence and `candidate-mmr-gt.json`; missing historical numbering JSON was never
fabricated. The five coalesces are Sym5/page_013 (4 and 7) and page_014 (10, 2, 10).
All existing rest values/identities were reviewed; 16 zero-fixture pages were viewed
in full. Existing GT errors confirmed: **0**. Full-page missing-event completeness
on the other 52 pages is **not certified**. The report retains that limitation.

Before consumption the tool verifies the fixed #413 inventory of 629 canonical
inputs, and fixed hashes of the reviewed fixtures and historical mapping sources.
It supports retained Docker `/workspace` symlinks when running on the host. Expected
hashes are Git-reviewed metadata; they are never refreshed from a candidate run.
It rechecks input hashes and consumed final-numbering hashes after the audit.
`row_start_samples.json` also fixes source-image hashes and the first physical bbox
of each sampled row. Editing either manifest creates a new reviewed GT version;
rescore the same retained outputs and preserve the old result when doing so.

## Current evidence (2026-10-10)

Source inference commit: `a65d9541777ae492137c24b6ce0f5f5692881945`.
Original config SHA-256:
`0edfdfda89ed50be6d0dafbf28fccc80840ef6330f193d19823a94f934cb2209`.
Original image: `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`.
Corrected replay commit: `825be77f7e0e8bc699d686b02722d78ca8e7e124`, diff SHA-256
`34db093416c5704d14b4c489fc81d3bb4d44f6351cd467720dcacc6c75b3b6dc`.
Investigation started at `develop@9183de380591878b1a2751d5975373035f10079c`.
The current utility runs against those retained outputs; it is not new inference.

| Check | Original #409 output | Corrected #413 output |
| --- | ---: | ---: |
| Physical pages / measures | 68 / 3287 | 68 / 3287 |
| Recognition TP / FN / wrong skip / FP | 170 / 3 / 4 / 0 | 170 / 3 / 4 / 0 |
| Recognition-to-applied local errors | 104 | 0 |
| GT-to-final local increment errors | 110 | 7 |
| Page continuity errors | — | 0 |
| Per-page / combined / PDF label agreement | — | 68 pages / 637 rows |
| Embedded final PDF pixel verification | — | 68 pages pass |

The seven local GT discrepancies remain #414 recognition problems. #416 retains
barline FP11/FN32 under the original unchanged matcher; five old `FN_cnn` entries
are accepted predictions assigned to other double-line strokes, rather than CNN
rejections. Their diagnostic correction and full 43-position record are in
[#416's comment](https://github.com/M763468/PDFScoreBar/issues/416#issuecomment-6092072422).
No GT event, barline, runtime code, model, matcher or threshold was changed here.

## Independently adjudicated row-start / PDF-label samples

The 18 samples cover the first three musical rows in five score openings and the
Sym5 third-movement opening. Read original page contexts, including divisi braces,
actual barlines, rest numbers, movement headings and printed margin measure numbers.
Boxed rehearsal numbers are not measure numbers. The samples explicitly use
**movement-local** numbering. They do not silently redefine the original score-wide
non-regression contract or automatically insert production movement resets.

| Score / page | Expected row starts | Retained JSON / final PDF labels | Result |
| --- | --- | --- | --- |
| Festival Overture / 001 | 1, 13, 17 | 1, 41, 45 | 2 mismatches, #414 rest errors propagate |
| Shostakovich Sym5 / 002 | 1, 7, 11 | 1, 7, 11 | All 3 pass (printed margin numbers) |
| Sibelius Concerto / 001 | 1, 33, 48 | 1, 33, 48 | All 3 pass (26/11 rest counts; printed 27/28 anchors) |
| Prokofiev Sym1 / 001 | 1, 6, 11 | 1, 6, 11 | All 3 pass (counted ordinary measures) |
| Prokofiev Sym5 / 001 | 1, 10, 17 | 1, 10, 17 | All 3 pass (2-bar rests and ordinary measures) |
| Shostakovich Sym5 / 012, III | 1, 6, 11 | 567, 572, 577 | 3 mismatches, movement reset absent |

**13/18 samples agree; 5 differ.** Three differences at III are distinct from MMR
recognition: the printed margin numbers are 1/6/11 while the unchanged retained
configuration has no movement-boundary resets. The existing reviewed movement
boundary mechanism can request a reset to 1 at compact system 0 on page_012;
this audit records the discrepancy and does not change production inputs.
Two Festival samples propagate the known rest errors. These sample counts are not
an extrapolated count of all absolute-number errors.

Per-page/combined/PDF agreement proves consumers display the same values, including
incorrect values. It cannot substitute for these independent original-image checks.
Full absolute numbering and all movement boundaries remain uncertified. Synthetic
regressions exercise real manual suppress/set_measure_span precedence, empty systems,
multiple pages, explicit one-bar skips, terminal rest consumption and movement reset.
They establish those operations' numbering contracts; they do not certify a real
review GUI correction run on all 68 pages.

## Completion and release disposition

This work completes #415's existing-event audit, reusable rescoring, deterministic
controls and independently adjudicated sample/consumer evidence. It records the
limits explicitly rather than claiming zero errors. GT correction is N/A because
none was confirmed. The remaining recognition work belongs to #414; producer/
barline diagnosis and downstream fixes belong to #416. The reported lack of complete
absolute-number certification is an explicit limit, not a passed gate.

**Unattended, fully correct automatic numbering is not established by this evidence.**
For #410, release disposition must acknowledge #414's seven errors, #416's barline
residuals and reviewed movement-reset needs, and validate the candidate's real
review/correction flow. Promotion is not authorized by this audit, and #410 must not
interpret #415 closure as all retained final PDFs being musically correct. The old
68/68 non-regression result remains unchanged. Any release scope/acceptance change
requires an explicit decision in #410; this PR does not make that decision.

## Validation

- Focused audit, compact identity, retained replay/PDF, manual-correction, reviewed
  movement and one-bar-veto tests: 64 passed.
- `make test-fast`: 110 passed.
- Repository-surface checker and focused surface/distribution tests: pass / 23 passed.
  The new audit test is registered as `validation_harness`; runtime files are unchanged.
- Touched Python `ruff check` / `ruff format --check`, compile, CLI `--help` and
  `git diff --check`: pass.
- Full68 retained rescore: completed; correctness exit 1 for seven local GT errors
  and five independent row-start differences. Original 104/110 counts reproduced.
- Retained PDF verification: 68 pages / 637 labels; JSON consumer and pixel checks
  pass. No additional inference, no saved PDF regeneration.
- GPU smoke/full inference skipped: only CPU developer auditing and metadata changed;
  the tool never executes the production model/pipeline. Original metrics/contracts
  and inputs are fixed, so retained rescoring is the relevant check.

Local run evidence: `logs/issue415/implementation/semantic-report-final.json`,
`semantic-run-final.log`, `targeted-tests.log`, and `number-sample-01..06.png`.
The earlier visual audit records stay under `logs/issue415/`; they are not GitHub
attachments. The Git-retained manifests and this record retain adjudicated values,
source hashes, identities and the limitations without storing dataset/model bytes.
