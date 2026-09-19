# Issue #333 movement-boundary investigation

This document records the Phase 1 and Phase 2 evidence and the current
production disposition. The resolved numbering consumer remains
[`MOVEMENT_BOUNDARY_CONTRACT.md`](MOVEMENT_BOUNDARY_CONTRACT.md).

## Evidence gap and corpus

The current numbering artifact contains page/system/measure geometry, but not
general heading OCR or semantic final/double/repeat barline types. MMR OCR is
limited to printed measure numbers and was not changed or reused. Six of seven
local PDFs have neither useful native outlines nor extractable text. Toy
Symphony has scanner page-label bookmarks, not movement structure.

Fresh current-pipeline runs at 360 dpi cover 26 selected pages from seven
scores. They contain 275 reconstructed system starts: 14 visually verified
movement boundaries and 261 negatives. Phase 2 added Beethoven 9 and Toy
Symphony as a source-level holdout after the Phase 1 conditions were recorded.

| Split | Scores | Systems | Boundaries | Negatives |
| --- | ---: | ---: | ---: | ---: |
| fit | 3 | 94 | 6 | 88 |
| validation | 2 | 74 | 3 | 71 |
| locked holdout | 2 | 107 | 5 | 102 |
| total | 7 | 275 | 14 | 261 |

The exact source hashes, selected pages, and ground truth are in
`tests/fixtures/movement_boundaries/issue333_representative.json`. The five new
holdout boundaries are Beethoven page/system `5/0`, `10/2`, `13/0` and Toy
Symphony `2/8`, `2/12`. Toy Symphony supplies two starts on one dense page and
the `Trio` at `2/10` is a reviewed subsection negative.

All 14 starts align with reconstructed system starts. No observed example
starts inside a system, so extending the Issue #268 consumer to measure
granularity remains unjustified.

## Page coordinate contract

Issue #268 `page` is the zero-based position in the ordered pipeline input. It
is not intrinsically a source-PDF page number. The representative fixture uses
the explicit `full_document_no_omissions` profile, where `page` happens to equal
`source_page`. It separately records `fresh_run_input_page` because bounded
runs contain only selected pages.

Candidate evidence follows the same ordered-input `page` coordinate and keeps
`page_id` and zero-based physical `source_page` as references when a manifest
provides them. Consumers must not copy a source page number into `page` when
pages were reordered or omitted.

## Strategy results

False reset and missed boundary are reported separately. A candidate's false
location is review work; the same location would be a damaging numbering reset
if candidates were exported without review.

| Strategy / evaluation | TP | False reset/candidate | Missed | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| native PDF structure, Phase 1 | 0 | 0 | 9 | n/a | 0.000 |
| frozen Phase 1 geometry, development | 9 | 2 | 0 | 0.818 | 1.000 |
| frozen Phase 1 geometry, locked holdout | 5 | 1 | 0 | 0.833 | 1.000 |
| exact OCR + geometry, locked holdout | 3 | 1 | 2 | 0.750 | 0.600 |
| frozen learned ranker, locked holdout | 1 | 1 | 4 | 0.500 | 0.200 |
| learned ranker automatic, seven-score LOSO | 8 | 1 | 6 | 0.889 | 0.571 |
| learned ranker candidate, seven-score LOSO | 12 | 1 | 2 | 0.923 | 0.857 |
| production geometry review producer, development | 9 | 2 | 0 | 0.818 | 1.000 |
| production geometry review producer, locked holdout | 5 | 0 | 0 | 1.000 | 1.000 |
| production geometry review producer, all | 14 | 2 | 0 | 0.875 | 1.000 |

The production producer excludes the initial musical system under the
full-document profile because numbering already starts at one. Its all-corpus
review burden is 16/275 system starts (5.82%); the two retained false candidates
are large-whitespace continuations. It emits them as
`ambiguous_review_required`, never as resets.

### Learned model and error analysis

The lightweight model uses standardized layout/semantic numeric features plus
character TF-IDF OCR features and a class-balanced logistic regression
(`C=0.1`, `liblinear`, seed 333). It was fit on 94 systems/6 positives; cutoff
selection used 74 systems/3 positives. The ignored checkpoint is
`logs/issue333/phase2/models/hybrid_ranker_v1.joblib`, SHA-256
`7381d789e4ae50bad1aa7283cfbe677e8e035f447c32da6f8c3bea3d6a7b9059`.
Runtime versions and every trial are in
`experiments/issue333/results/hybrid_model_selection_v1.json`.

Validation was perfect, but the locked holdout invalidated it. The model missed
all three Beethoven boundaries. Exact OCR consensus also missed `Presto` read
as `prestoxd` and `Menuetto` read as `meuuetto`. Adding OCR character TF-IDF in
leave-one-score-out evaluation did not change a single selected location over
the numeric model. The small fit set and publisher-specific scale/layout
features dominate; numeric scores are not calibrated confidence.

An explicitly post-holdout fuzzy verifier repairs those two OCR variants. With
the universal initial-system invariant it scores 14/14 with no false location.
That rule was designed after viewing the holdout failures, so it is recorded as
an exploratory hypothesis, not independent evidence and not an automatic
production result. Even if its 0/261 observed false-reset count were treated as
independent, the one-sided 95% binomial upper bound is about 1.14% per negative
system start; that is not adequate evidence for silent resets in long scores.

## Production disposition

Silent automatic resolution remains disabled. The locked learned result failed
both false-reset and recall requirements, while the only zero-error combined
rule is post-holdout. A bounded zero-error result from seven orchestral parts is
not sufficient source-general safety evidence.

The geometry producer is production-worthy as a semi-automatic review stage:

- it preserves 100% candidate recall on the locked holdout and full corpus;
- holdout review burden is 5/107 (4.67%), total burden is 16/275 (5.82%);
- it uses normalized, explainable layout signals and retains raw observations;
- every proposal is `ambiguous_review_required` and cannot be consumed as an
  Issue #268 reset;
- manual/configured resolution remains deterministic, and reviewed candidates
  can be exported to the unchanged Issue #268 contract.

The producer is `src.pipeline.movement_boundary_candidates`, with the CLI
`tools/generate_movement_boundary_candidates.py`. It is intentionally not
wired into default pipeline routing. OCR evidence may be added by a future GUI
or producer revision, but OCR is not required for the current high-recall
candidate stage.

## Reproduction and retained artifacts

Small protocols, configs, results, model hashes, FP/FN locations, and commands
are under `experiments/issue333/`. Large generated artifacts remain ignored:

- `logs/issue333/fresh/` — Phase 1 manifests, geometry, OCR, and comparison;
- `logs/issue333/phase2/runs/` — Beethoven and Toy fresh current-pipeline runs;
- `logs/issue333/phase2/holdout_ocr.json` — versioned RapidOCR evidence;
- `logs/issue333/phase2/models/` — selected and LOSO checkpoints;
- `logs/issue333/phase2_corpus/` — contact sheets used for visual verification.

Source PDFs/images are local-only and are not committed. No detector or
barline threshold, MMR OCR/CNN, HOMR recognition, grouping behavior, or Issue
#268 consumer semantics changed.

## Remaining evidence needed for automatic reset

Reopen automatic resolution only with a preregistered, untouched corpus that
substantially expands composers, publishers, scan quality, multi-staff layout,
heading languages/styles, heading-free starts, internal tempo/form headings,
and long ordinary continuations. It must preserve separate false-reset and
missed-boundary reporting, source-level splits, raw failure locations, and a
calibrated policy if numeric confidence is exposed. Thousands rather than
hundreds of representative negative system starts are needed before a zero-FP
observation can support a sub-per-mille false-reset claim.
