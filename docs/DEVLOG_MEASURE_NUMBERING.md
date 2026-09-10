# Legacy Measure Numbering / MMR Milestone Ledger

> [!IMPORTANT]
> This is a **historical ledger**, not the current MMR specification.
> For maintained behavior, use `docs/refactors/issue94/MMR_CURRENT_STATE.md`, current source/tests,
> and the relevant Issue/PR lineage.

## Why this file is compact

The former `feature/measure_numbering` development log mixed draft questions, branch/worktree state,
local output paths, dated implementation notes, and experimental metrics. Under Issue #308 its
reusable historical core was distilled to Issue #94 and this short navigation ledger.

Exact former commands, local paths, and chronology remain recoverable through Git history.

## Early numbering milestones — Jan 2026

- Linear numbering introduced barline deduplication and interval-based measure construction.
- Historical implementations used a 15 px dedup threshold and inserted an implicit/ghost start
  when the first barline was more than 50 px from the staff start; later code also guarded against
  tiny end intervals with a minimum measure width.
- Real-data verification exposed a coordinate-scale mismatch between staff masks and original
  images, establishing the need for explicit coordinate conversion.
- Staff/system grouping evolved from unsafe gap/alignment-only clustering toward physical ink
  connectivity checks for adjacent staves, motivated by divisi failure cases.

These values describe the historical implementation path; current constants and grouping behavior
must be read from current source/tests.

## Multi-measure-rest (MMR) milestones

- Manual rest-count overrides used `skip = N - 1` for a printed `N`-measure rest.
- The investigated HOMR/OEMER paths did not provide rest-count digits, which motivated a RapidOCR
  path.
- The experimental pipeline evolved through empty-measure ROI extraction, H-bar detection,
  expanded OCR margins, geometric candidate scoring, split-digit merging, rehearsal/tempo text
  filtering, and H-bar masking.
- A CNN classifier was later inserted before OCR to identify likely MMR crops.

The maintained architecture and failure taxonomy are now documented in
`docs/refactors/issue94/MMR_CURRENT_STATE.md`.

## Historical checkpoints

The following values are retained only to identify the old experiment lineage:

- early Prokofiev-5 MMR CNN evaluation: precision 93.8%, recall 90.0%, F1 91.8% (45/48, 45/50);
- refreshed historical MMR dataset v2: 183 positive / 4045 negative samples;
- historical text-noise model validation: F1 0.9737, precision 0.9487, recall 1.0000,
  accuracy 0.9973;
- Jan-14 then-current global evaluation: Stage 1 P=0.9872 / R=0.8750 and Stage 2
  P=0.9359 / R=0.8295, which identified OCR as the main recall bottleneck at that point;
- H-bar masking improved the recorded Sibelius Stage-2 result, while rotation TTA produced no
  useful gain and was not adopted.

These are **not current production metrics**. The later 68-page MMR evaluation and maintained
current-state analysis live in `docs/refactors/issue94/MMR_CURRENT_STATE.md`.

## Durable recovery locations

- Issue #94 historical distillation:
  https://github.com/M763468/PDFScoreBar/issues/94#issuecomment-5616903014
- Maintained/scoped current-state note:
  `docs/refactors/issue94/MMR_CURRENT_STATE.md`
- Later numbering/MMR lineage:
  Issues #194 / #197 / #200 / #208 / #212 / #213 / #221 / #223 / #224 / #244 / #257 / #264 / #276 / #277
- Present behavior:
  current `src/measure_numbering/`, pipeline orchestration, tests, and active config

## Historical-state rule

Old branch names, worktrees, local log directories, provisional tool inventories, "next step"
sections, and old production labels from the former diary are archaeology only. Revalidate against
current source and the active Issue before acting on them.
