# Issue #218: 3div./4div. connector grouping fixtures

The `issue218_3div_*` and `issue218_4div_*` assets are original synthetic score excerpts, authored for
[Issue #218](https://github.com/M763468/PDFScoreBar/issues/218). They contain
five-line staves, simple notes, aligned barlines, a left/system-start connector
chain for three or four divisi staves, and a separate following system. They
are not scans of published music or retained detector/model outputs.

| Fixture | Expected staff membership (top-to-bottom, zero-based) | Measure numbers |
| --- | --- | --- |
| [3div. score](issue218_3div_score.png) | `[[0, 1, 2], [3]]` | `[[1, 2], [3, 4]]` |
| [4div. score](issue218_4div_score.png) | `[[0, 1, 2, 3], [4]]` | `[[1, 2], [3, 4]]` |

Each excerpt has a JSON file with page coordinates, staff-line spacing,
barline boxes, expected connector presence, system membership, and numbering.
The `*_staff.png` masks contain only the five staff lines; `*_symbols.png`
contains only the left connectors, as a controlled semantic-mask input.
The score PNG includes a deliberate non-left ink bridge at the rightmost
barline between the last divisi staff and the independent following system.
That bridge tests the false-merge guard; it is not a musical connector.

The original staff height is 80 pixels (`unit_size=20`). Adjacent gaps within
the divisi chain are 72, 123, and (for 4div.) 72 pixels. The 123-pixel gap
lies above the ordinary `1.5 * height` grouping limit and below the
`1.56 * height` connector-rescue limit. Three aligned barlines provide the
required rescue support. The independent following system has a 72-pixel
gap and no left connector, so proximity and aligned ink alone cannot explain
the expected split.

Regenerate the committed assets from the repository root:

```bash
python3 tests/fixtures/system_grouping/generate_issue218.py
```

Run the regression tests:

```bash
python3 -m pytest -q tests/test_issue218_multistaff_system_grouping.py
```

The tests use the current connector extractor and `ConnectorAwareSystemBuilder`
without explicit system indices. They verify complete staff membership,
transitive merging, independent-neighbor separation, each missing chain link,
half/normal/double resolution, reversed staff input, and score/blank/no image
paths. They also exercise `MeasureNumberingPipeline.process_page` using the
retained staff mask and either the symbols or brace-dot semantic-mask input,
then verify shared measure progression. The builder tests exercise connector
rescue with the original boxes; staff extraction expands boxes, so the
pipeline test establishes integration rather than the exact rescue-distance
boundary.

These fixtures establish grouping and numbering regression behavior under
controlled inputs. They do not establish real-score 3div./4div. detector
accuracy, mask-production quality, or full-pipeline/GPU performance. Detector settings and accepted evaluation inputs remain fixed. The real-score
validation below covers the production grouping/numbering changes.


## Published-score inputs and retained detections

The primary material is **Claude Debussy, La Mer, violoncello part**,
IMSLP26369 (Durand & Fils, 1909, plate D. & F. 6531, Kalmus reprint).
The already prepared PDF and full-page 360-DPI images were recovered from the
main worktree's `logs/issue218/materials/imslp_20261009/`.
[The frozen contract](issue218_la_mer.json) preserves all three selected pages:

| PDF / printed page | Expected system staff counts | Landmark |
| --- | --- | --- |
| 3 / 4 | `2, 2, 2, 2, 4` | Four cello groups near rehearsal 9 |
| 4 / 5 | `4, 4, 2` | Four voices, then return to 2div. near rehearsal 10 |
| 9 / 10 | `1, 1, 1, 3, 3, 1` | DIV. en 3, then UNIS near rehearsal 45 |

Source: [IMSLP work page](https://imslp.org/wiki/La_Mer_(Debussy,_Claude)),
[PDF](https://s9.imslp.org/files/imglnks/usimg/0/0f/IMSLP26369-PMLP06033-Debussy_-_La_Mer_(cello-part)a.pdf).
This contract checks all staff membership and separation plus shared full-height
measure geometry. It has no annotated barline-accuracy or MMR/OCR ground truth;
passing grouping is not a claim of perfect detector accuracy or musical numbering.

Supplementary material is **Akshin Alizadeh, Fourth Symphony (alla Mugham)**,
Baku, 2010 scan, [PDF](https://musakademiya.musigi-dunya.az/noti/alizade_sim4.pdf),
PDF page 4. It contains three full-score systems with `5, 5, 6` staves
(two violin staves and three/four viola voices). The selected 3div./4div.
viola crops and the entire page are all required inputs, with two physical
measures per system and final numbering `1..10` across the three inputs.
[The frozen scan contract](issue218_real_score.json) records the source/image
hashes and crop rectangles; [the actual-detection fixture](issue218_real_detection.json)
records geometry, staff spacing, barlines and connector evidence produced by
the fresh production-model run. These are model outputs, not manual inputs to
the real-score detector. The lightweight test checks those retained outputs
without loading GPU models.

Prepare either material from its original PDF (large scans/masks stay ignored):

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/verification/verify_issue218_divisi.py prepare \
  --contract tests/fixtures/system_grouping/issue218_la_mer.json \
  --source-pdf logs/issue218/la-mer/source/la_mer_cello.pdf \
  --output-root logs/issue218/la-mer/reproduction
```

Omit `--contract` for the supplementary Alizadeh contract. Run the generated
`config.yaml` with the maintained GPU validation launcher and verify the run:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/verification/verify_issue218_divisi.py verify \
  --contract tests/fixtures/system_grouping/issue218_la_mer.json \
  --run-dir logs/issue218/la-mer/candidate/la_mer \
  --report logs/issue218/la-mer/candidate_report.json
```

The verifier requires canonical detector settings, the complete ordered input
set and unchanged input hashes. It rejects forced single-system grouping and
manual overrides. A replay must provide `--detector-run-dir` identifying the
fresh source run and preserve the image/barline/staff-mask bytes. Expected
staff centers are verification labels and are never passed to the pipeline.
See `docs/refactors/issue218_real_divisi_validation.md` for outcomes, failed
attempts, runtime identity and regression checks.

The final implementation also rejects short non-staff fragments in the original
mask: at most two persistent row runs and a foreground span below two staff
spaces. It preserves uncertain/broken staff masks instead of requiring five
visible lines. The complete La Mer and Alizadeh contracts now pass after MMR/OCR
and final numbering. The 68-page corpus preserves all numbered systems and MMR
crop geometry; removal of 56 empty systems is separately reported as failure
under the original empty-inclusive JSON-equality contract.

To verify the retained final La Mer replay:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/verification/verify_issue218_divisi.py verify \
  --contract tests/fixtures/system_grouping/issue218_la_mer.json \
  --run-dir logs/issue218/staff-fragments/la-mer/output/la_mer \
  --detector-run-dir logs/issue218/la-mer/candidate/la_mer \
  --report logs/issue218/staff-fragments/la-mer/report.json
```

## Manual measure and MMR ground truth

[issue218_measure_gt.json](issue218_measure_gt.json) independently annotates all
six original scans/crops, including shared measure intervals, numeric rest lengths
and selected-input numbering. It records source hashes, the fixed scoring
contract, single-annotator status and a documented geometric correction.
La Mer has 70 displayed intervals / 81 musical bars; Alizadeh has 10 / 10.
Numeric rest labels `2`, `5`, `7` are shared events, while `1` does not add a skip.
Numbers start at 1 per selected-input run; they are not original-score absolute
bar numbers. Alizadeh crop/full-page overlap is explicit.

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/verification/evaluate_issue218_measure_gt.py \
  --run la-mer=logs/issue218/staff-fragments/la-mer/output/la_mer \
  --run alizadeh=logs/issue218/staff-fragments/alizadeh/output/real_scores \
  --report logs/issue218/ground-truth/evaluation/current-report.json
```

The current result exits **1**: MMR counts are correct on 3/3 rests, but La Mer
PDF page 9 loses the last visible interval of its first system (5 GT vs 4 output),
shifting later numbers by one. All 80 GT intervals remain in evaluation; 79 match
spatially and 51 have correct final numbers. No index-shift search is used.
See the durable validation report for revision history and the original topology
contract's separate results. Review overlays are retained under
`logs/issue218/ground-truth/visual/annotations/`.
