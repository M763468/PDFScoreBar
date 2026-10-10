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
shared measure boxes are checked. The original topology contract had no
barline/MMR GT; the manual reference added later is a separate stronger gate.
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

## Clipped last-interval correction (2026-10-10)

The user authorized correcting the deficit found by the manual reference within
Issue #218. It is a pre-existing one-staff boundary problem, rather than a divisi
merge failure, but it invalidates final numbering in the original required La Mer
input set. The reference, all six inputs and scoring tolerances remain fixed.
The contract was recorded before implementation at
`logs/issue218/trailing-interval/validation/contract.json`; baseline is
`15779cd1061c86f3451182907d8c75bc936479f7`.

`ClippedSystemEndDetector` reads the original page ink after system grouping.
It requires five thin, regularly spaced lines continuing through the final
staff-space strip and the preceding four spaces, together with musical ink
inside the staff in a tail at least four spaces wide. Only then does it append
one shared logical end boundary at the image edge. See the
[geometry contract](../NUMBERING_GEOMETRY_CONTRACT.md) for all normalized limits.
Blank margins, empty staff continuations, short post-bar regions, uncertain
spacing and incomplete line evidence abstain. Staff extraction still accepts
broken lines; this positive clipping check does not impose a five-line staff
acceptance rule. The logical end is added after grouping and reconstructed in
both Phase A and Phase C. Detector/CNN/MMR thresholds, models and routing remain
unchanged.

Fresh production MMR/OCR and final-numbering runs on the fixed six inputs now
pass every gate of the unchanged GT v2:

| Input | Output / GT intervals | Correct final numbers / GT | Exact multi-bar rests |
| --- | --- | --- | --- |
| La Mer PDF page 3 | 25 / 25 | 25 / 25 | `2` |
| La Mer PDF page 4 | 12 / 12 | 12 / 12 | None; no false positive |
| La Mer PDF page 9 | **33 / 33** | **33 / 33** | `5`, `7` |
| Alizadeh 3div. crop | 2 / 2 | 2 / 2 | None; no false positive |
| Alizadeh 4div. crop | 2 / 2 | 2 / 2 | None; no false positive |
| Alizadeh complete page | 6 / 6 | 6 / 6 | None; no false positive |

All **80/80** intervals match spatially and have correct final and page-local
numbers; counts match **19/19** systems and MMR events match **3/3** with exact
durations. Internal boundaries match **61 TP, 0 FP, 0 FN**. All six original
topology gates also pass at Phase A and final output.
Page 9 first system now has five intervals, including selected-input number 43;
the next system starts at 44. The original scan and before/after output are shown
in `logs/issue218/trailing-interval/visual/la-mer-page009-before-after.png`.
The prior 79/80 interval and 51/80 number failure remains recorded below.

The full68 replay used identical retained images, barlines, staff and connector
masks with the baseline and candidate pipelines. Baseline output was also checked
against the already frozen `421f3496` runtime outputs. All **68/68 complete page
JSONs**, including numbered systems and empty systems, are identical to baseline
`15779cd1`; all three numbered MMR input views are identical on **68/68**.
All 68 source image SHA identities and supporting mask/barline hashes are
recorded in `validation/report.json`. This new correction changes only the
La Mer page-9 first-system interval in the targeted replay. It does not supersede
the old 43/68 empty-inclusive failure of the preceding staff-fragment change.

Reproduction (immutable production image for every runtime command):

```bash
DOCKER_IMAGE=sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc \
  bash scripts/docker_runtime_validation.sh \
  --config logs/issue218/trailing-interval/la-mer/config.yaml
DOCKER_IMAGE=sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc \
  bash scripts/docker_runtime_validation.sh \
  --config logs/issue218/trailing-interval/alizadeh/config.yaml
PYTHONPATH=. .venv_pdf/bin/python tools/verification/evaluate_issue218_measure_gt.py \
  --run la-mer=logs/issue218/trailing-interval/la-mer/output/la_mer \
  --run alizadeh=logs/issue218/trailing-interval/alizadeh/output/real_scores \
  --report logs/issue218/trailing-interval/validation/measure-gt-report.json
```

Runtime preflight verifies compatibility and model assets. The source SHA hashes
and baseline/image identity in the reports distinguish the candidate working
tree from the pre-fix checkout commit recorded by the evaluator. Replay preceded
a whitespace-only Ruff formatting step; its original source hashes remain
retained, and fresh production runs/tests used the formatted implementation.
Focused tests, including clipping recovery, two scales, one/three/four staves,
MMR index preservation and negative controls: **98 passed** on host Python and
**98 passed** in the production Python/OpenCV runtime. `make test-fast`:
**112 passed**. Fresh canonical GPU smoke **PASS: 85/85, zero hard FP/FN/soft
residuals** is recorded in `logs/issue218/trailing-interval/smoke/`. Reproduce with
the same immutable image and `--config logs/issue218/trailing-interval/smoke/config.yaml`.

The explicit distribution manifest includes the new runtime module and classifies
its develop-only regression test. Surface/engine boundary checks pass **18 tests**;
scoped Ruff lint/format, repository-surface inventory and `git diff --check` pass.
The replay and its full68 input/support hashes are retained under
`logs/issue218/trailing-interval/validation/`. Its command is:

```bash
docker run --rm -v "$PWD":/workspace \
  -v /home/masaki_muramatsu/ws_PDFScoreBar:/retained:ro -w /workspace \
  -e PYTHONPATH=/workspace \
  sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc \
  /opt/venv_pipeline/bin/python logs/issue218/trailing-interval/validation/replay.py
```

Fresh full68 detector inference and OCR were not rerun: upstream inference is
unchanged and every numbered MMR input view is exactly equal. Actual MMR/OCR was
rerun on all six target inputs. Independent adjudication and original-score
absolute numbering remain outside the claimed results. This is conservative
clipping recovery, not a guarantee for other scans with damaged right-edge lines.
Current and future architecture documents were reviewed; process ownership,
public artifact schema and service responsibilities are unchanged, so structural
architecture updates are N/A.

## Historical manual measure/MMR reference and evaluation at `15779cd1` (2026-10-10)

The user requested source-reviewed ground truth and evaluation after the grouping
fix. [The manual annotation](../../tests/fixtures/system_grouping/issue218_measure_gt.json)
now records every displayed measure interval, shared staff membership, numeric
rest length and expected selected-input number for all six original inputs.
The final revision is **v2**, SHA-256
`61166bdd81636aea5e326ecc17913277efccd1b08b20f44cf385612b6c315967`.

Labels were authored by visually reading unannotated original 360-DPI images and
system crops with coordinate rulers. Printed stroke centers were refined only
from source ink in manually selected windows; detector outputs did not create
labels. Existing manually reviewed staff centers were reused. GT contains 70
La Mer displayed intervals representing 81 musical bars, plus 10 Alizadeh
intervals/bars. Numeric rests of `2`, `5`, `7` are each one shared interval;
three numeric `1` rests consume one bar each. Tied whole notes and tremolo/slash
notation are negative controls. Crop/full-page Alizadeh inputs overlap and must
not be presented as independent corpus samples.

Numbering follows the existing run: start at 1 for each work and continue through
its selected inputs. La Mer PDF pages 3, 4 and 9 are noncontiguous and span
movements, so these labels **are not the original score's absolute bar numbers**.
The evaluator also reports page-local numbers to distinguish incoming offsets.
Right-edge clipped intervals remain in counting/numbering GT when their start and
musical content are visible. They are not dropped to make a detector result pass.

This is a new, stronger evaluation contract; earlier topology/regression results
remain valid under their original contracts. Primary gates require exact system
interval counts, all numeric multi-bar rest counts without false positives, and
correct final numbers with complete spatial coverage. Intervals match one-to-one,
in order, using horizontal IoU >=0.8 and vertical overlap >=0.5. Internal shared
boundary diagnostics use the existing 0.5 staff-space tolerance. There is no
best-index-shift search or compensating threshold change.

| Input | Output / GT intervals | Correct final numbers / GT | Multi-bar rests with exact count |
| --- | --- | --- | --- |
| La Mer PDF page 3 | 25 / 25 | 25 / 25 | `2`: correct |
| La Mer PDF page 4 | 12 / 12 | 12 / 12 | No MMR; no false positive |
| La Mer PDF page 9 | **32 / 33** | **4 / 33** | `5` and `7`: both correct |
| Alizadeh 3div. crop | 2 / 2 | 2 / 2 | No MMR; no false positive |
| Alizadeh 4div. crop | 2 / 2 | 2 / 2 | No MMR; no false positive |
| Alizadeh complete page | 6 / 6 | 6 / 6 | No MMR; no false positive |

**The `15779cd1` output FAILS the complete measure/numbering contract.** Of 80 GT
intervals, 79 are spatially matched (no extra interval); counts match 18/19
systems. MMR count recall/precision are 3/3 on this small reference. Final numbers
are correct for 51/80 GT intervals; the unmatched interval remains in the
denominator. Internal shared boundaries match 60/61, with zero false positives.

The identified error is La Mer PDF page 9, first system: the final visible interval
`[2732,3240]` has notes/rests but no final printed bar within the cropped image.
The output stops at the preceding bar around x2732. GT requires five intervals,
output has four, so the rest of that page is numbered one bar early. Selected-input
number 43 is missing; the next system starts at 43 instead of 44. Rest lengths
are correct, so later MMR skips preserve rather than repair the one-bar offset.
The same deficit and number errors occur in the pre-fragment-filter `9f0535f`
outputs; this is a pre-existing boundary/count issue, not a regression caused by
removing false staff fragments. Production code was not changed for this
annotation/evaluation request.

### Annotation review and retained corrections

This is single-annotator GT authored by Codex and remains open to user review;
it is not independently adjudicated ground truth. Original review crops,
full-page GT overlays and the missing-interval comparison are retained under
`logs/issue218/ground-truth/{source-review,visual}/`.

Initial GT v1 mistakenly used x1565 for one page-9 boundary: the magnified source
shows that this is a triplet note stem with a beam and notehead; the un-beamed
full-height barline is x1615. The boundary diagnostic prompted a second raw-source
review. Only that geometric coordinate was corrected, including its two adjacent
interval edges; counts, durations, numbering and matching tolerances were fixed.
Both versions fail the primary count/numbering gates with the same totals.
The original annotation hash
`b8a12c4f5f97069676dcd5fbf476c5ee0dde185ae1830629c56c176678ddb050`,
`source-review/frozen_measure_gt.json` and
`evaluation/annotation-v1-report.json` are retained. Revision history is also in
the committed GT. The old diagnostic was 59 TP, 1 FP, 2 FN; corrected geometry
is 60 TP, 0 FP, 1 FN. No failed production case was excluded.

### Reproduction and checks

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/verification/evaluate_issue218_measure_gt.py \
  --run la-mer=logs/issue218/staff-fragments/la-mer/output/la_mer \
  --run alizadeh=logs/issue218/staff-fragments/alizadeh/output/real_scores \
  --report logs/issue218/ground-truth/evaluation/current-report.json
```

The command exits **1** for the observed quality failure and writes all six
per-page results, unpaired intervals, count/number differences, MMR errors,
annotation/evaluator/input/output SHA-256 and run-manifest SHA-256.
`evaluation/pre-fragment-filter-report.json` scores the preceding candidate on
the same GT and confirms identical counts/MMR/numbers, with the old staff
membership failures. Source runtime candidate: `421f3496`; immutable image and
model outputs are the production runs documented below. Neither upstream
inference nor MMR/OCR is rerun solely to rescore retained, valid final outputs.

Validation: targeted **78 passed** (including three new evaluator guards),
`make test-fast` **112 passed**, scoped Ruff lint/format, repository-surface
inventory and `git diff --check` PASS. Logs are under
`logs/issue218/ground-truth/`. The first evaluator invocation failed before
scoring because it assumed every MMR override's page index was 0; this was
corrected to the production zero-based input index and tested explicitly.
The failed pre-score log remains at `source-review/evaluation.log`.

Fresh GPU smoke/full68 inference are not applicable to this reference/rescoring
change: production numerical code/config/models are unchanged. Previous GPU
smoke and 68-page correctness evidence remain recorded below. Independent human
adjudication and original-score absolute numbering are not claimed.

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

## Staff-fragment result under the original topology contract

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
MMR/OCR is run for all six target inputs. At this earlier stage musical MMR accuracy was unscored; the new manual
reference and stronger evaluation are reported above.

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
