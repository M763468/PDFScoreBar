# Issue #218: real 3div./4div. validation

## Materials and frozen contracts

Primary material: **Claude Debussy, La Mer, violoncello part**, IMSLP26369,
Durand & Fils (1909), plate D. & F. 6531, Kalmus reprint.
The already prepared PDF and images were recovered read-only from the main
worktree's `logs/issue218/materials/imslp_20261009/`.
[Source PDF](https://s9.imslp.org/files/imglnks/usimg/0/0f/IMSLP26369-PMLP06033-Debussy_-_La_Mer_(cello-part)a.pdf),
[IMSLP work page](https://imslp.org/wiki/La_Mer_(Debussy,_Claude)).

[The committed contract](../../tests/fixtures/system_grouping/issue218_la_mer.json)
keeps the pre-existing, visually reviewed full-page topology contract:

| PDF / printed page | Expected ordered staff counts per system |
| --- | --- |
| 3 / 4 | `2, 2, 2, 2, 4` |
| 4 / 5 | `4, 4, 2` |
| 9 / 10 | `1, 1, 1, 3, 3, 1` |

All three original 360-DPI, 3240×4320 images are required. Exact staff membership,
separation from neighboring systems/UNIS, no extra empty systems and full-height
shared measure boxes are checked. There is no annotated barline or MMR/OCR GT;
this is not an accuracy claim for every barline or musical measure number.
Verification centers are labels from original scan lines, never detector inputs.

Supplementary material: **Akshin Alizadeh, Fourth Symphony (alla Mugham)**,
2010 Baku scan, [source PDF](https://musakademiya.musigi-dunya.az/noti/alizade_sim4.pdf),
PDF page 4. Its complete page has `5, 5, 6` staves: two violin staves plus
three/four viola voices. The fixed input set contains the 3div. viola crop,
4div. viola crop and complete page, all at 360 DPI. Expected staff counts are
`[3]`, `[4]`, `[5, 5, 6]`; every system has two physical measures, spanning all
voices, and final shared numbering is `1..10` across those three inputs.
[The committed contract](../../tests/fixtures/system_grouping/issue218_real_score.json)
records PDF/image SHA-256 and crop coordinates. These criteria were fixed
before the first detector result was interpreted.

The PDF/model artifacts are retained locally under `logs/issue218/`, not in Git.
The compact [real-detection fixture](../../tests/fixtures/system_grouping/issue218_real_detection.json)
contains actual Alizadeh model-derived geometry, barlines and connector evidence
for reproducible lightweight regression, with source/runtime provenance.

## Production changes

The Alizadeh run reproduced two downstream failures:

- The complete page's bottom voice had an extracted staff and generated positive
  left connector, but no accepted barline candidates. Pairwise aligned-barline
  checks left it outside the six-staff system.
- The 3div. crop contained a short isolated note fragment accepted as a barline.
  Its X position introduced an extra shared measure for all three voices.

`ConnectorAwareSystemBuilder` now defers positive connector links to barline-free
voices, accepting them transitively only inside groups of at least three staves,
within the existing ordinary-distance limit. Explicit connector absence remains
a split; wider connector rescue retains aligned-barline support. The one/two-staff
alignment contract is preserved.

For systems with at least three staves, `MeasureNumberer` accepts shared boundaries
that span four staff spaces inside one staff or have X-aligned support on at least
two distinct staves. It uses existing staff-space/deduplication units and preserves
ghosts. Detector/CNN thresholds, routing, model bytes and accepted datasets were
not retuned. These fixes do not remove upstream false-positive model candidates.

See [the geometry contract](../NUMBERING_GEOMETRY_CONTRACT.md).
Current/future architecture documents were reviewed: process ownership, pipeline
phases, public surfaces and future service responsibilities are unchanged.

## Current result: conservative staff-fragment removal

The user authorized implementation and validation after reviewing two shape
experiments. Requiring five approximately equally spaced lines failed: it lost
52 measure intervals on four of the 68 existing corpus pages and regressed every
Alizadeh input. That failed candidate remains retained; its criterion was not
relaxed and relabeled a pass.

The accepted implementation rejects only components with at most two persistent
row runs **and** an undilated foreground span strictly below two staff spaces.
Unknown spacing, larger components and broken five-line masks remain accepted.
It applies automatically to numbering, connector semantics and MMR support;
there are no score-specific coordinates or manual overrides in production.

| Current gate | Result |
| --- | --- |
| La Mer PDF page 3, Phase A and final | `[2,2,2,2,4]`, no empty systems: PASS |
| La Mer PDF page 4, Phase A and final | `[4,4,2]`, no empty systems: PASS |
| La Mer PDF page 9, Phase A and final | `[1,1,1,3,3,1]`, no empty systems: PASS |
| Alizadeh 3div./4div./complete page, Phase A and final | `[3]`, `[4]`, `[5,5,6]`, two measures per system, final `1..10`: PASS |
| Existing 68 pages, numbered systems | Exact staff membership, measure counts, numbers and BBoxes: **68/68 PASS** |
| Existing 68 pages, MMR support | Numbered geometry for primary, implicit-start alternate and fallback views: **68/68 PASS** |
| Original 68-page JSON equality including empty systems | **43/68; FAIL under the old contract**. 56 empty systems removed on 25 pages |

The revised contract explicitly permits short non-staff components to disappear,
including empty systems, as authorized by the user's request to implement the
reviewed proposal. It still requires preservation of every numbered system in
the existing corpus and the unchanged complete-page La Mer contract. The old
JSON-equality failure is reported separately; no failing input is excluded.

The La Mer page-3 hairpin was a third staff inside a real two-voice system; page 9
had an independent empty hairpin system. Removing them preserves physical measure
counts `[5,1,7,8,4]` (25) and `[4,5,7,5,5,6]` (32), respectively, and Phase-A
numbers. Full-page final topology is checked after fresh production MMR/OCR.
These results do not claim musical barline/MMR correctness without GT.

Current evidence is retained under `logs/issue218/staff-fragments/`:

- `{la-mer,alizadeh}/{config.yaml,run.log,report.json}`: production MMR/OCR,
  final numbering and original frozen-contract verification, all exit 0.
- `validation/{contract.json,replay.py,replay.log,report.json}`: equivalent
  74-input comparison with baseline `9f0535f`; numbered-system gate exit 0,
  original empty-inclusive JSON failures recorded per page.
- `validation/{audit.py,audit.log,audit-report.json}`: all 68 fixed input hashes,
  staff/barline/connector/MMR mask hashes and three MMR views; candidate and
  baseline also match the previously frozen prototype outputs, exit 0.
- `validation/final-number-comparison.json`: all six actual inputs preserve
  final measure numbers/BBoxes and MMR overrides relative to `9f0535f`, exit 0.
- `validation/targeted-runtime.log`: **89 passed** in production Python, including
  staff extraction, all 61 Issue #218 cases and 14 MMR-support tests.
- `validation/{test-fast.log,test-fast-details.log}`: `make test-fast`, **112 passed**.
- `smoke/{config.yaml,run.log,output/candidate/detector_accuracy_smoke_summary.json}`:
  fresh canonical GPU/model/GT smoke, **85/85** matches, zero hard FP/FN/soft
  residuals, exit 0.
- Scoped Ruff lint/format, repository-surface inventory and `git diff --check`: PASS.
- `visual/la-mer-before-after.png`: original scans with before/after staff boxes;
  red hairpin components disappear while real green staff boxes remain.
- `visual/artifacts/visual_manifest.txt`: evidence collected and visually inspected
  using the repository `visual-diff-viewer` skill.

Initial test-launch attempts failed before testing: host Python lacked RapidOCR,
and the production image lacked pytest (then its `py` compatibility module).
The successful production test run supplies only pytest's helper packages from
an ignored temporary directory, preserving the image's numerical/model stack.
The initial verifier invocation lacked `PYTHONPATH=.`; its corrected invocation
passed. Failed logs remain retained and are not counted as test passes.

The immutable runtime image and unchanged source detector runs are those listed
below. The final `pipeline.py` SHA-256 is
`87b3688d2b36bbdf1321bde1793381fb189e622b4c05c4b0fbdc7e0e2ad74044`,
also recorded in `validation/audit-report.json`;
`validation/contract.json` also records its pre-format and final source hashes.
Fresh full-68 model inference and OCR are omitted because upstream inference is
unchanged and all numbered MMR input views are exactly preserved. Actual-score
MMR/OCR is run for all six target inputs. Complete musical MMR accuracy remains
unscored because annotated MMR GT is unavailable.

## Historical result at `9f0535f` (before staff-fragment removal)

| Gate | Original baseline | Candidate at `9f0535f` |
| --- | --- | --- |
| Alizadeh 3div. crop | Three voices, **3** measures: FAIL | Three voices, **2** measures: PASS |
| Alizadeh 4div. crop | Four voices, two measures: PASS | Four voices, two measures: PASS |
| Alizadeh entire page | `[5,5,5]`, sixth voice empty: FAIL | `[5,5,6]`, two measures each: PASS |
| Alizadeh final numbering | `1..11`: FAIL | `1..10`: PASS |
| La Mer PDF page 3 full-page topology | `[2,2,2,3,4]`: FAIL | Same topology: FAIL |
| La Mer PDF page 4 full-page topology | `[4,4,2]`: PASS | Same topology: PASS |
| La Mer PDF page 9 full-page topology | Expected visible systems plus an extra empty artifact: FAIL | Same topology: FAIL |
| Accepted corpus Phase A | Archived source reproduced on all 68 pages | Exact staff/empty-system/measure/number/BBox equality on all 68 pages: PASS |

La Mer's three four-staff systems and two three-staff systems have correct complete
membership, shared measure-height geometry and separation from the next musical
system. Final candidate Alizadeh overlays were also visually inspected. **The whole La Mer input contract fails**, because its staff masks also
produce a short false staff between the two voices of page 3's fourth system
(`[2045,2691,2467,2739]`) and an empty false staff on page 9
(`[1849,3758,2219,3812]`). Original-code and final-candidate Phase-A replays on
identical actual model outputs are byte-equivalent as JSON data for all three
pages. The failed full-page contract remains visible; selecting only the successful
divisi systems does not supersede it. Staff-mask false-positive handling is remaining
work outside these connector/measure-boundary changes.

The first connector-only implementation changed one accepted corpus page:
`Va__Prokofiev_Symphony5/page_005` gained an unwanted two-staff merge. That candidate
failed the 68-page gate. Restricting new connector-only links to established
three-or-more-staff groups resolved it. The failed report remains at
`logs/issue218/validation/full68-regression-v1-failed.json`; the final report is
`full68-regression-v2.json` (source-hash companion:
`full68-regression-v2-provenance.json`). No failing page was excluded.

Two Alizadeh replay attempts accidentally collected HOMR teaser PNGs through
`page_*.png` and failed. The corrected replay selects the original three fixed,
SHA-verified inputs using `page_[0-9][0-9][0-9].png`; both failed logs
(`candidate.log` and `candidate_v2.log`) are retained.
A smoke attempt with an incorrect reused output root was stopped (exit 137);
`smoke-current-02` uses a separate candidate root and is the authoritative run.

## Earlier runtime and provenance (`9f0535f`)

- Baseline source: `8340a808da7f70c316156791e709ba945fad88fe`.
- Actual-score fresh runs use the unchanged `configs/dense_full_pipeline.yaml`
  detector contract, x4 SR and verified selected CNN/OMR-DLN/MMR models.
- Immutable runtime image:
  `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`
  (`pdfscore_issue409_staff_mask104:latest`, built from `a65d9541777ae492137c24b6ce0f5f5692881945`).
- Image/checkout runtime compatibility fingerprint:
  `d73cfaa3096e662faca36d85f425553ebeb258f912a7bd424827425caaac2f97`.
  The stale canonical tag was not used. Maintained launcher preflight verified
  the bind-mounted code/environment contract and CUDA/model assets.
- Runs executed with the production `/opt/venv_pipeline/bin/python` environment.
- Final runtime source SHA-256:
  `connector_aware_builder.py`: `faea3c3b0fdf87db6752e21442cb74c588f6cfb9feeea169382a289fe8c29a8b`;
  `numbering.py`: `df5ef54760fa667bb3f96eac7848ad2972bc8319c932d244184d50dc1a464367`.
  Execution started at the baseline Git HEAD with these working-tree changes;
  source hashes identify the tested candidate independently of commit timing.

Fresh score detector outputs are retained in
`logs/issue218/real-score/baseline/real_scores` and
`logs/issue218/la-mer/candidate/la_mer`. Candidate downstream replays reuse those
same image/barline/staff/connector bytes instead of rerunning unchanged expensive
inference. The verifier checks their identities and canonical detector settings,
rejects manual overrides and forced single-system grouping, and requires a fresh
source-run manifest for a replay.

The 68-page gate reuses #409's retained complete production run at
`logs/issue409/full68-numbering-20261009` in the main worktree, mounted read-only.
Original-code replay first matches all archived Phase-A JSONs, then candidate
JSONs must match exactly. Input images and model output hashes are recorded per
page, including connector masks. The #409 and baseline production numbering code
are identical. This gate does not rerun full-68 inference or MMR/OCR; detector/model
code is unchanged, and equivalent retained outputs isolate the downstream change.
It is a topology/count/number/geometry regression gate, not fresh full-68 accuracy.

## Earlier reproduction and validation evidence (`9f0535f`)

Use the commands in the
[fixture README](../../tests/fixtures/system_grouping/README.md) to reproduce
hashed original inputs and score actual outputs.

Maintained fresh runtime validation and candidate replay commands:

```bash
DOCKER_IMAGE=sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc \
  bash scripts/docker_runtime_validation.sh --config <retained-config.yaml>
```

All fresh/candidate pipeline runs cited below exited 0. Alizadeh baseline
verification exited 1 and final verification exited 0. La Mer full-page
verification exited 1; the failed original contract remains unchanged. The
final 68-page replay, focused/fast tests and authoritative GPU smoke exited 0.

Retained configurations/logs/reports:

- `logs/issue218/real-score/{baseline_config.yaml,baseline.log,baseline_report.json}`.
- `logs/issue218/real-score/{candidate_final_config.yaml,candidate_final.log,candidate_final_report.json}`.
- `logs/issue218/la-mer/{candidate_config.yaml,candidate.log,candidate_v1_report.json}`.
- `logs/issue218/la-mer/{candidate_final_config.yaml,candidate_final.log,candidate_final_report.json}`.
- `logs/issue218/la-mer/target_divisi_diagnostics.json`: five exact target memberships
  matched; explicitly diagnostic, full-page status remains failed.
- `logs/issue218/la-mer/compare_grouping.py` and `compare_grouping.log`:
  original/candidate fixed-detector Phase-A comparison, all three JSONs identical.
- `logs/issue218/validation/{replay_full68.py,full68-regression-v2.log,full68-regression-v2.json}`.
- `logs/issue218/validation/smoke-current-02/{config.yaml,run.log,candidate/}`:
  canonical fresh PDF/model/GT accuracy smoke, PASS: 85/85 matches, zero hard FP/FN/soft residuals.
- `logs/issue218/validation/grouping-tests-runtime.log`: focused **93 passed**,
  including **61** Issue #218 cases and actual-model regression.
- `logs/issue218/validation/test-fast-runtime-details.log`: **110 passed**.
- Scoped Ruff lint/format, repository-surface classification and `git diff --check`: PASS.

Fresh full-68 model inference is omitted for the unchanged upstream detector;
all 68 retained inputs are replayed. Broad repository lint is omitted in favor
of checks on touched Python files. La Mer whole-page topology remains FAIL and
barline/MMR accuracy is unscored because no such GT was prepared.
