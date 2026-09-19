# Issue 333 phase 2 experiments

This directory contains the retained experiment definitions and durable
results for the movement-boundary investigation. Copyrighted source PDFs and
generated images/artifacts stay outside Git under `logs/issue333/`.

The Phase 2 protocol is locked before evaluating the two newly discovered
scores:

- development: the five Phase 1 evaluation2 scores;
- model/rule fitting: Prokofiev 1, Prokofiev 5, and Festival Overture;
- validation/cutoff selection: Shostakovich 5 and Sibelius;
- final source-level holdout: Beethoven 9 and Toy Symphony.

The holdout labels are established by visual review of the source pages, but
their current-pipeline system indices and metrics are not used to select
features or cutoffs. A later hypothesis prompted by holdout errors must be
reported as exploratory and may not replace the locked result.

Run definitions are under `configs/`. Generated output is written below
`logs/issue333/phase2/`.

Experiment-only Python harnesses were committed before their results and then
removed from the final tree. This preserves the required audit trail without
shipping investigation helpers as production code:

| Experiment | Harness commit | Result commit |
| --- | --- | --- |
| frozen geometry holdout | `27d747e3` / `6f542646` | `bb612a78` |
| OCR hybrid + learned ranker selection | `0e55d0a8` | `5dec308a` |
| one-shot frozen holdout | `1d7a95a9` | `3db552d4` |
| post-holdout fuzzy verifier | `bc9b6e23` | `7ca75932` |
| source-level LOSO ablation | `0ab19671` | `7b37f277` |
| production producer replay | `2bcd5144` / `8fc8d867` | `f90ad016` |

The supported implementation is now
`src/pipeline/movement_boundary_candidates.py`; the removed harnesses must not
be mistaken for production entry points.
