# Issue 333 phase 2 experiments

This directory contains small, reviewable experiment definitions and durable
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

