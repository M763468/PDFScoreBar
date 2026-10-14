# Issue #414: corroborated selection when MMR staff votes tie

## Problem and resulting behavior

On Shostakovich Sym5/page_013, physical system 1 / measure 0, the upper-staff
masked crop loses most of the rest-count digit and OCR reads boxed rehearsal
number 79. The lower staff correctly reads 4 with a better existing spatial
score. Previously equal staff vote counts selected the first value, 79. The
validated candidate selects 4 and corroborates conflicting staff choices across
preprocessing variants. This is a generic aggregation rule, with no page/value
mapping, OCR backend addition, new crop geometry or threshold change.

Staff support remains primary. Only a tie between leading values, with CNN
probability above the existing threshold, uses spatial score to select a leader.
For a measure narrower than the existing
100px boundary, tied leaders rejected by the existing >20 count guard cannot
displace an admissible tied leader. This applies to masked and fallback OCR; an
unambiguous high-count majority retains the original rejection policy.
When any such staff ambiguity occurs, a strict majority supported by at least two
valid preprocessing results can select its best-scored representative. Otherwise
maximum-score variant selection remains authoritative. Low-CNN staff ordering,
one-bar evidence accumulation/veto, fallback and J2 policies remain in place.

This second step is necessary: score-only staff tie selection improves the nominal
page but changes a previously correct 4 to artifact 17 under a +2px X perturbation.
The ordinary global preprocessing-majority experiment is also unsafe. Its three
new errors occur on single-staff measures, so corroboration is limited to staff
ambiguity rather than replacing ordinary variant selection globally.

## Fixed evaluation contract

- Five scores / 68 retained fresh #409 pages; 3287 physical measures.
- Reviewed GT: 177 events, rebased from 182 historical fixtures; no GT edits/exclusions.
- Baseline: detected174 / TP170 / FN3 / wrong skip4 / FP0.
- Required: FN<=3, wrong skip<=4, FP=0, with a strict FN or wrong-skip improvement.
- Preserve zero-fixture16/0, one-bar, manual precedence and #277 focused controls.
- Retain failed candidates; investigate crop perturbations and printed rehearsal
  contamination separately without replacing the original Full68 criterion.
- No SR/HOMR/detector rerun for diagnosis/full68 MMR evaluation. Read the retained
  original images, base geometry and MMR support sidecars unchanged.

The source baseline is `28dc0bbabf9bb968155080d233f25e1ce92bcc9f`; its MMR module
is byte-identical to #409 inference source
`a65d9541777ae492137c24b6ce0f5f5692881945`.
Runtime image: `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`.
Classifier: `f163fa2a7679d12c0f4fe6fc2fadc7ed1f144035779a18b83a303bfa6d35903a`.
Threshold/rescue: 0.5 / 0.1; rotation TTA false. Torch CUDA and all inspected
RapidOCR components' CUDA providers were required and confirmed. The Docker
resolver verified runtime compatibility before reuse. The other worktree's
running container was not reused; transient containers mount this checkout.

The fixed #413 canonical inventory was verified (629 inputs), plus the 68 image,
base and support-sidecar identities frozen for MMR replay. Baseline per-page
semantic overrides matched the retained #409 outputs exactly. Current input/config
and candidate source hashes, runner hashes, provider records and commands are in
the issue-scoped retained reports; no fallback or unknown runtime was accepted.

## Seven original residuals: observed first loss

Indices are compact physical system/measure, zero-based. All seven CNN probabilities
exceed the rescue and main thresholds; these are OCR/aggregation failures.

| score/page | s/m | GT count | Baseline | Observation |
| --- | --- | ---: | ---: | --- |
| Festival/001 | 0/0 | 7 | 37 | Digit7 remains visible, raw OCR emits H37; no exact7 in 3 calls. Extraction accepts37. |
| Festival/001 | 0/2 | 4 | missing | Digit4 remains in crop; none of 24 calls reads4. Broad fallback reads adjacent2/3/7 but scores are rejected. |
| Festival/002 | 3/2 | 2 | 7 | None of 21 calls reads2; a nearby boxed7 is selected, even at negative spatial score because CNN is high. |
| Festival/004 | 2/2 | 3 | missing | Digit3 remains visible; none of 24 calls reads3 (non-numeric outputs include orci/二). |
| Festival/009 | 0/0 | 3 | missing | No correct3 in 22 calls; wide fallback emits31 but negative spatial score rejects it. No31→3 mapping. |
| Sym5/013 | 1/0 | 4 | 79 | Upper masking truncates4; lower OCR reads4. Equal staff support keeps first79, discarding higher spatial score4. |
| Sibelius/003 | 2/6 | 4 | 111 | Standard/heavy read4; no_dilate reads barline artifact111 with higher spatial score. Ordinary global voting is unsafe elsewhere. |

Raw image, masked/preprocessed images, raw OCR boxes/text/confidence, spatial
selection results, retry stages, classifier probabilities, hashes and output keys
are retained in `logs/issue414/diagnostic-20261013/trace-compact.json`,
`first-loss.json` and `target-01..07-*` images. Source/mask/preprocess observations
were inspected visually. A raw-output loss identifies the detector/recognizer
boundary; it does not prove an internal OCR model's precise mechanism.

#221's component/backend/mask-repair/window grids and strict-risk rejection, and
#277's accepted bounded native-geometry retry, were read before this work. No
broad OCR/backend/grid exploration was repeated. The three residual misses have
no correct raw candidate in the current bounded paths; forcing their numbers
would not be a justified generic improvement.

## Original-contract A/B results and dispositions

| Candidate | TP / FN / wrong / FP | OCR calls | Elapsed seconds | Disposition |
| --- | --- | ---: | ---: | --- |
| Baseline | 170 / 3 / 4 / 0 | 857 | 149.91 | Retained baseline exactly reproduced |
| Spatial score on staff ties | 171 / 3 / 3 / 0 | 829 | 142.92 | Reject: +2px X control changes correct4 to17 |
| Global preprocessing majority | 168 / 3 / 6 / 0 | 859 | 149.25 | Reject: 3 new errors despite111→4 recovery |
| Both unguarded policies | 169 / 3 / 5 / 0 | 831 | 147.21 | Reject: wrong-skip gate fails |
| Staff tie with scoped corroboration | 171 / 3 / 3 / 0 | 829 | 140.68 | Pass Full68 and bounded controls |
| Initial changed source | 171 / 3 / 3 / 0 | 829 | 134.71 | All pages semantically equal to validated candidate |
| Review revision: preserve admissible tied leaders | 171 / 3 / 3 / 0 | 829 | 142.13 | All68 pages semantically equal to initial changed source |

The global-majority regressions are Sym5/page_010 s9m1 (9→6),
ProkofievSym1/page_003 s0m2 (4→41), and page_005 s6m5 (3→98).
These failed results stay visible. No failing pages or GT events were removed.
The final candidate changes exactly one semantic override: Sym5/page_013 s1m0,
79→4. Other nominal-page outputs and zero-fixture16/0 remain unchanged.
OCR calls fall by28 because the correct initial aggregate avoids downstream retries.
Elapsed values are single-run observations, not a general speedup guarantee.

## Bounded controls and limitations

Thirteen targets (7 residuals, 5 #277 focused positives, 1 one-bar negative) were
checked at nominal, X±2px and staff-Y±2px geometry: 65 cases. The final candidate
introduces zero previously-correct→wrong cases; its corrected rest reads4 under
all five perturbations, including the original boxed79/80 contamination.
The five focused positives and one-bar negative pass at nominal geometry.
Ten shifted focused cases remain wrong in both baseline and candidate. Therefore
this is comparative non-regression under the tested perturbations, **not** a
claim that all perturbed measures are correctly recognized.

The first control candidate failed one case; the final control report retains it
in the earlier `controls.json`. The guarded runner completed all65 evaluations
but its final JSON assembly had a key-name typo. The complete stdout was rescored
with exact65-case identity/duplicate checks into `controls-guarded.json`; inference
was not rerun solely to repair reporting. Per-case new-candidate call counts were
not retained in that stdout; Full68 call counts above are measured separately.
A diagnostic subclass-generation indentation error also occurred before guarded
Full68 evaluation; its failed log is retained, then the corrected evaluation ran
fully. Neither harness error is represented as a passing execution.

Six nominal errors remain: Festival's three misses and 7→37 / 2→7 errors, plus
Sibelius4→111. Manual `set_measure_span` can supply the visually reviewed counts;
manual suppress/precedence tests pass. No manual corrections were inserted into
these metrics, and this work does not certify the real release-candidate GUI flow.

## PR review revision

[Review r4260666741](https://github.com/M763468/PDFScoreBar/pull/420#discussion_r4260666741)
identified an untested narrow-measure tie: a higher-score79 could reject the
whole variant despite an admissible4. The masked and fallback paths now select
among admissible tied leaders before spatial ranking. The original100px/>20
guard and non-tied majority rejection are unchanged. Unit/integration tests
cover both paths, all-rejected ties and the width boundary. The integration
test reproduces missing detections in both paths on pre-review source
`1d15641`, then passes on the corrected source.

The revision is evaluated separately in `full68/source_review_r4260666741/` and
`controls-review.json`, under the original contracts. Full68 semantic predictions
are identical to the initial changed source, with829 OCR calls. All65 controls
complete successfully with0 new regressions, the same10 shared focused failures,
and the corrected4 in all5 views. Earlier results and harness failures remain
visible; the review control runner completed its JSON normally.

## Downstream and validation

The actual new MMR predictions are applied through production final numbering
from the unchanged retained barlines/staff/connector geometry. All68 page measure
bboxes remain equal to base; application and page-continuity errors are0. GT local
increment errors decrease7→6. Per-page/combined/PDF consumers are checked, including
all68 embedded PDF page pixels and637 row labels. Original #415 results remain
unchanged; no movement reset is inserted, and absolute numbering is uncertified.

The downstream runner initially violated the package-relative source-image contract.
It was corrected by staging byte-identical images within its own package; no MMR
or upstream inference was repeated. Both attempted and completed logs are retained. The review revision preserves
all68 semantic override sets and all downstream inputs, so the completed final
numbering/PDF evidence is reused; equivalence is recorded in
`review-downstream-equivalence.json`.

- Initial focused tests:86 pass. Review-revision focused OCR aggregation/fallback/
  one-bar/support/manual/system-identity tests:91 pass (including narrow-measure
  masked/fallback regression tests and rejection-boundary checks).
- `make test-fast`:110 pass; touched Ruff/format/diff checks pass.
- Full68 MMR-only evaluation:171/3/3/0, zero-fixture16/0; frozen input hashes rechecked.
- Bounded comparative controls:65 cases, zero new regressions; shared failures above.
- Downstream:68 pages/3287 measures, application0, GT6, PDF68/637.
- Canonical Docker/GPU pipeline/accuracy smoke: PASS, detector85/85 with hardFP0/FN0/soft0, recorded under
  `logs/issue414/gpu-smoke-20261013/`, and repeated successfully for the review
  revision under `logs/issue414/gpu-smoke-review-20261014/`; numerical settings equal the maintained
  smoke, with only output destinations changed to keep artifacts issue-scoped.
- Full SR/HOMR/detector evaluation is not repeated: geometry/models are unchanged;
  the affected full68 MMR path and downstream final outputs are evaluated directly.

The case/dataset/model bytes and generated outputs remain outside Git under
`logs/issue414/`. Developer audit reports describe retained inference, not fresh
full-pipeline inference. Release acceptance and remaining OCR/barline/reset limits
still require explicit disposition in #410; one rest correction is not complete
automatic musical correctness.

## Residual disposition: manual discovery and correction before release

The six residuals remain **unresolved recognition errors**, not GT exclusions or
completed fixes. #414 can conclude its bounded improvement and first-loss diagnosis
after this PR is accepted; that does not accept those six errors for release. We do
not create another OCR investigation without a concrete new hypothesis. Their
product disposition belongs to #410: a visually reviewed, manually corrected
workflow, with promotion held if users cannot reliably find or correct the errors.

All six passed the classifier threshold. Neither a low-confidence filter nor the
absence of a warning is a sufficient discovery policy. The supported user route is
[the user guide's rest-review procedure](../../USER_GUIDE.md#check-and-correct-multi-measure-rests):
open the job's review handoff, use the always-visible **Inspect all measures**
entry, compare every printed multi-measure rest on every page, and include count-1
measures where recognition missed the rest. The entry opens the existing full
measure list and correction task; it does not silently insert known-case values or
claim to flag all errors. Source score images can be zoomed and overlays hidden.

The following is a developer acceptance inventory for the retained corpus. GUI
system/measure columns use **one-based physical locations**, not musical measure
numbers. JSON keys remain zero-based. Values must be visually rediscovered in the
actual candidate, rather than prefilled from this table during a discovery check.
These locations describe the frozen retained geometry. Re-identify the printed
rest after regenerating or editing barlines; do not blindly reuse old indices.

| score / page image | JSON s/m | GUI system/measure | Original displayed count | Printed count to record |
| --- | --- | --- | ---: | ---: |
| Festival / page_001 | 0/0 | 1/1 | 37 | 7 |
| Festival / page_001 | 0/2 | 1/3 | 1 (missed rest) | 4 |
| Festival / page_002 | 3/2 | 4/3 | 7 | 2 |
| Festival / page_004 | 2/2 | 3/3 | 1 (missed rest) | 3 |
| Festival / page_009 | 0/0 | 1/1 | 1 (missed rest) | 3 |
| Sibelius / page_003 | 2/6 | 3/7 | 111 | 4 |

For each location, select the actual physical measure, choose **Set rest measure
count**, enter the printed value, **Add change**, then **Save changes**. This same
operation handles both missed and misread rests. Record the page/location, observed
digit and reason. Generate and open the corrected PDF; inspect the corrected local
increment and later row/page starts, including the next page. Keep the job,
correction file and immutable application attempt/consumed-input provenance.
Saving an edit or displaying a current/successful PDF is not a musical acceptance
decision. Never retune thresholds, change GT, insert a movement reset or remove a
measure solely to hide an OCR counting discrepancy.

### #410 promotion gate and required evidence

This PR adds the visible route and durable policy. It does **not** supply a completed
clean release-candidate GUI acceptance run for the six locations. Before main
promotion, #410 must:

1. Materialize an isolated candidate from the then-accepted develop SHA and retain
   its manifest/config/model identities. Run the public review entrypoint from
   that distribution, without developer/GT tooling or undeclared develop files.
2. Demonstrate discovery in the real GUI for all six locations by reading the
   original score, including three count-1 misses and unflagged/high-confidence
   errors. Retain observations/screenshots, selected physical indices, original
   and corrected counts. Check the general per-page inspection instruction in
   English and Japanese; a prefilled correction JSON is not discovery evidence.
3. Record/save the six edits, apply them through the user application, and retain
   successful attempt IDs and consumed corrections. Verify local increments and
   downstream row/page starts in final JSON **and the actual corrected PDF**
   against independent score counting. Keep automatic and manually corrected
   results separate; automatic metrics remain TP171/FN3/wrong3/FP0.
4. Independently resolve movement/reset conventions and barline residuals. In
   particular, reconcile Festival's independently recorded13/17 row starts, and
   Sym5 III's1/6/11, with the corrected geometry and numbering; rest corrections
   alone do not certify those absolute anchors. Do not redefine an anchor merely
   to match generated output.
5. Record an explicit accept/hold decision for a product that requires human
   score review, including the risk of overlooked rests, uncertain digits,
   missing/extra barlines and unspecified movement resets. Confirm whether the
   inspection effort and remaining risk are acceptable for the supported use.

A concrete unresolved cross-check is Festival/page_001: retained geometry has
four physical boxes in its first row. Correcting its two rest counts alone gives
spans7,1,4,1 (sum13), hence row starts14/18 from start1. The #415 independent
samples currently record13/17; their written basis also lists7+1+4+1 but labels
the sum12. This arithmetic/anchor inconsistency must be adjudicated from the
score and numbering convention in #410 before accepting absolute numbering.
It is not resolved by changing a reset or excluding a measure to force13/17.
The existing sample data, GT and automatic results remain unchanged here; the
calculation is a retained-geometry cross-check, not a completed GUI/PDF run.

If any known rest cannot be found, selected or corrected safely, downstream
numbering fails independent checks, or review is impractical, **hold main
promotion**. State the observed obstacle and scope a concrete UX improvement or
new technical hypothesis with acceptance criteria. Closing #414, a successful
pipeline/smoke, CI success or a passing internal manual-precedence test cannot
substitute for this decision. #410 remains open until its own gate is satisfied.

### Validation of the manual-review route

Review-client/server, English/Japanese copy and isolated distribution checks:
46 tests pass; `make test-fast`:110 pass. JavaScript syntax, touched-test Ruff,
format, repository surface and whitespace checks pass. The route regression
includes a count-1 miss, an unflagged high-confidence misread and an existing
manual correction; all stay visible/selectable and other pending edits survive.
The guide and assets use existing shipped paths, with no GT/developer dependency.

The numerical MMR module, model, geometry and configuration are unchanged by this
UI/documentation revision. Prior Full68, bounded controls, downstream and GPU
evidence is retained without repeating inference. Real browser discovery and
correction of the six locations on a frozen clean release candidate, and the
independent absolute-number decision, remain required #410 work. Client contract
tests or packaged-asset checks are not substitutes for that user acceptance run.
Local command/log/hash records are under `logs/issue414/manual-review-20261014/`.
